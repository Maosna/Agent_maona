"""命令执行 + 网络搜索工具"""
import asyncio
import re
import ipaddress
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
import httpx


def _get_http_client(timeout: int = 15) -> httpx.AsyncClient:
    """创建带系统代理支持的 httpx 客户端"""
    proxies = None
    # 读取环境变量代理
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        proxy = os.environ.get(var)
        if proxy:
            proxies = proxy
            break
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, proxy=proxies, trust_env=True)

# 敏感信息模式（命令输出中自动脱敏）
SECRET_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{20,}', '[API_KEY_REDACTED]'),
    (r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}', 'Bearer [TOKEN_REDACTED]'),
    (r'password[=:]\s*\S+', 'password=[REDACTED]'),
    (r'--token\s+\S+', '--token [REDACTED]'),
    (r'([A-Z_]+_API_KEY)\s*=\s*\S+', r'\1=[REDACTED]'),
    (r'([A-Z_]+_SECRET)\s*=\s*\S+', r'\1=[REDACTED]'),
    (r'([A-Z_]+_TOKEN)\s*=\s*\S+', r'\1=[REDACTED]'),
    (r'export\s+(\w+)\s*=\s*\S+', r'export \1=[REDACTED]'),
]

# 危险命令黑名单（仅拦截极端危险操作，其余警告即可）
# 使用 \s* 匹配任意空白绕过，包括换行、制表符
BLOCK_COMMANDS = [
    # 格式化/磁盘/分区破坏（不可逆）
    r"\bformat\b", r"\bdiskpart\b", r"\bcleardisk\b",
    # 系统关机/重启（无警告的）
    r"\bshutdown\s*/[srf]+\b",  # 匹配 shutdown /s /r /f 及各种空格变体
    r"\brestart-computer\b\s*-Force\b", r"\bstop-computer\b\s*-Force\b",
    # 远程下载执行管道（常见攻击链）- 允许任意中间空白和管道前缀
    r"(curl|wget|iex)\s+.+\|\s*(sh|cmd|powershell|bash)\b",
    # 进程注入
    r"\binject\b", r"\bdllinject\b",
    # 用户目录破坏
    r"\brm\s+.*-rf\s+/(\s|$)",  # rm -rf /
    r"\brd\s+/s\s+/q\s+C:\\\\",  # rd C:\
    r"\bdel\s+/f\s+/s\s+/q\s+C:\\\\",
]

# 警告命令（危险但可能有合理用途，警告后放行）
WARN_COMMANDS = [
    r"\brm\s+.*-[rf]+\b",
    r"\bdel\s+/[fF]\b",
    r"\bdeltree\b",
    r"Remove-Item\b.*-Recurse.*-Force",
    r"\breg\s+delete\b",
    r"\bchmod\s+777\b",
    r"\bicacls\b",
    r"\bdocker\s+(rm|rmi|prune)",
    r"\bnpm\s+uninstall\b",
    r"\bpip\s+uninstall\b",
    r"\bnmap\b",
    r"\bdd\b",
    r"\bgpupdate\s+/force\b",
    r"\bnet\s+user\b",
]


def _check_command(command: str) -> tuple[str | None, str | None]:
    """检查命令危险等级，返回 ('block'|'warn'|None, 匹配规则)"""
    for pattern in BLOCK_COMMANDS:
        if re.search(pattern, command, re.IGNORECASE):
            return ("block", pattern)
    for pattern in WARN_COMMANDS:
        if re.search(pattern, command, re.IGNORECASE):
            return ("warn", pattern)
    return (None, None)


async def run_command(command: str, __confirmed: bool = False, timeout: int = None, **kw) -> str:
    """执行 shell 命令（带安全检查）"""
    action, pattern = _check_command(command)
    if action == "block" and not __confirmed:
        return f"__CONFIRM_{pattern}::{command}"
    prefix = ""
    if action == "warn":
        prefix = f"⚠️ 安全提示：此命令可能危险（匹配: {pattern}），已执行但请注意\n\n"

    # === 幂等性预检查：先确认操作的必要性 ===
    idem_hint = _check_idempotent(command)
    if idem_hint:
        # 如果是幂等跳过后的消息，不执行
        if idem_hint.startswith("⏭️"):
            return prefix + idem_hint
        # 非幂等提示（如命令修正），继续执行
        prefix += idem_hint

    # 自动修正：检测 PowerShell 语法（变量、cmdlet、管道等）并包装
    _ps_patterns = [
        r'\$\w+\s*=',            # $var = ...（变量赋值）
        r'\$\{env:',             # ${env:VAR}
        r'\$env:',               # $env:VAR
        r'\bGet-\w+',           # Get-ChildItem 等
        r'\bNew-\w+',           # New-Item 等
        r'\bSet-\w+',           # Set-Content 等
        r'\bRemove-\w+',        # Remove-Item 等
        r'\bJoin-Path\b',       # Join-Path
        r'\bCopy-Item\b',       # Copy-Item
        r'\bTest-Path\b',       # Test-Path
        r'\bOut-Null\b',        # Out-Null
        r'\bWrite-Host\b',      # Write-Host
        r'\bForEach-Object\b',  # ForEach-Object
        r'\bSelect-Object\b',   # Select-Object
        r'\bWhere-Object\b',    # Where-Object
        r'\bStart-Process\b',   # Start-Process
    ]
    _is_ps = any(re.search(p, command, re.IGNORECASE) for p in _ps_patterns)
    if _is_ps and 'powershell' not in command.lower() and 'pwsh' not in command.lower():
        # 转义内部双引号避免 cmd.exe 解析冲突
        safe = command.replace('"', "'")
        command = f'powershell -Command "{safe}"'
        prefix += "[自动包装为 PowerShell 命令]\n"

    # 显式传递环境变量（确保 MAONA_PLUGIN_ROOT 等被继承）
    _subproc_env = os.environ.copy()
    try:
        # GUI 程序（Start-Process）需用 DETACHED_PROCESS 让窗口正常显示
        is_gui = bool(re.search(r'Start-Process', command, re.IGNORECASE))
        if is_gui:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=_subproc_env,
                creationflags=0x00000008 if sys.platform == "win32" else 0,  # DETACHED_PROCESS
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=_subproc_env,
            )
        timeout_sec = timeout or 120  # 默认 120s 超时，避免 Godot 启动等长时间命令卡死
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        output = stdout.decode("utf-8", errors="replace")
        # 脱敏：过滤 API Key / Token / 密码
        for pattern, replacement in SECRET_PATTERNS:
            output = re.sub(pattern, replacement, output)
        # 超大输出标注
        if len(output) > 50000:
            output = output[:50000] + f"\n... (输出共 {len(output)} 字符，已截断前 50K)"
        return f"{prefix}命令: {command}\n退出码: {proc.returncode}\n{output or '(无输出)'}"
    except Exception as e:
        return f"命令执行失败: {e}"


async def web_search(query: str) -> str:
    """联网搜索（使用 DuckDuckGo Lite，防反爬）"""
    import re
    from urllib.parse import unquote
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with _get_http_client(timeout=15) as client:
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers=headers
            )
            text = resp.text

            # DuckDuckGo Lite 结构：每结果两行 <tr>
            # <a rel="nofollow" href="..." class='result-link'>Title</a>
            # <td class='result-snippet'>Description</td>
            result_snippets = re.findall(
                r"class='result-snippet'>(.*?)</td>",
                text, re.DOTALL
            )
            # href 在 class 之前
            result_links = re.findall(
                r"<a[^>]*href=\"([^\"]+)\"[^>]*class='result-link'[^>]*>(.*?)</a>",
                text, re.DOTALL
            )

            if not result_links:
                return f"搜索「{query}」未找到结果"

            lines = [f"搜索「{query}」结果:"]
            idx = 0
            for href, title in result_links[:15]:
                title_clean = re.sub(r"<[^>]+>", "", title).strip()
                if "Sponsored" in title_clean or "sponsored" in title_clean.lower():
                    continue
                idx += 1
                if idx > 10:
                    break
                    
                url = href
                if "uddg=" in url:
                    url = unquote(url.split("uddg=")[1].split("&")[0])
                elif url.startswith("//"):
                    url = "https:" + url

                # 匹配对应的 snippet（按原始顺序）
                orig_idx = list(result_links).index((href, title))
                snippet = result_snippets[orig_idx] if orig_idx < len(result_snippets) else ""
                snippet_clean = re.sub(r"<[^>]+>", "", snippet).strip()
                snippet_clean = re.sub(r"&nbsp;", " ", snippet_clean)
                snippet_clean = re.sub(r"&amp;", "&", snippet_clean)
                snippet_clean = re.sub(r"\s+", " ", snippet_clean)

                lines.append(f"{idx}. {title_clean}")
                if snippet_clean:
                    lines.append(f"   {snippet_clean[:200]}")
            return "\n".join(lines)
    except Exception as e:
        return f"搜索失败: {e}"


async def web_fetch(url: str) -> str:
    """抓取网页内容（连接级 SSRF 防护，TUN/代理自动信任）"""
    import re, ipaddress
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if hostname in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return "❌ 安全限制：禁止访问本地回环地址"
        if hostname.startswith("169.254."):
            return "❌ 安全限制：禁止访问云元数据地址"
        # 阻止所有私有 IP 范围（10.x, 172.16-31, 192.168.x）
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private:
                return f"❌ 安全限制：禁止访问私有地址 {hostname}"
        except ValueError:
            pass  # 非 IP 地址（域名），放行
    except Exception:
        pass

    try:
        async with _get_http_client(timeout=15) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            # 简单提取文本
            text = resp.text
            # 移除 script/style 标签
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # 移除 HTML 标签
            text = re.sub(r'<[^>]+>', ' ', text)
            # 压缩空白
            text = re.sub(r'\s+', ' ', text).strip()

            if len(text) > 50000:
                text = text[:50000] + f"\n... (原文共 {len(text)} 字符，已截断前 50K)"
            return f"网页内容 ({url}):\n---\n{text}"
    except Exception as e:
        return f"抓取失败: {e}"


async def download_file(url: str, path: str) -> str:
    """下载远程文件到本地（带 SSRF 防护和大小限制）"""
    from urllib.parse import urlparse
    import os
    # 仅拦截直接回环和云元数据
    try:
        parsed = urlparse(url)
        if parsed.hostname in ("127.0.0.1", "localhost", "::1"):
            return "❌ 安全限制：禁止下载本地地址"
        if parsed.hostname.startswith("169.254."):
            return "❌ 安全限制：禁止下载云元数据"
    except:
        pass
    dest = Path(path).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with _get_http_client(timeout=30) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return f"下载失败: HTTP {resp.status_code}"
                total = 0
                max_size = 1024 * 1024 * 1024  # 1GB
                with open(str(dest), "wb") as f:
                    async for chunk in resp.aiter_bytes(8192):
                        total += len(chunk)
                        if total > max_size:
                            f.close()
                            os.unlink(str(dest))
                            return f"❌ 文件过大（>{max_size/1024/1024:.0f}MB），拒绝下载"
                        f.write(chunk)
                return f"✅ 已下载 {url} -> {dest} ({total:,} bytes)"
    except Exception as e:
        return f"下载失败: {e}"


async def web_search_api(query: str, engine: str = "duckduckgo") -> str:
    """使用搜索引擎 API 搜索（支持 duckduckgo/google/bing）"""
    if engine == "duckduckgo":
        return await web_search(query)
    # Google/Bing 需要 API Key，暂时引导用户配置
    return f"搜索引擎 '{engine}' 需要 API Key 配置。请在设置中配置搜索引擎 API Key，或使用默认的 duckduckgo 引擎。"


async def run_python(code: str, timeout: int = 30, __confirmed: bool = False, **kw) -> str:
    """执行 Python 代码片段并返回结果（线程隔离，带超时）

    危险操作不阻止，仅在界面提醒用户确认。
    """
    import io, sys, concurrent.futures, re

    # 检测潜在危险模式（不阻止，仅提醒）
    DANGER_PATTERNS = [
        (r'\bos\.system\b', "执行系统命令 (os.system)"),
        (r'\bsubprocess\b', "启动子进程 (subprocess)"),
        (r'\beval\s*\(', "动态代码执行 (eval)"),
        (r'\bexec\s*\(', "动态代码执行 (exec)"),
        (r'\bcompile\s*\(', "动态编译 (compile)"),
        (r'\b__import__\s*\(', "动态导入 (__import__)"),
        (r'\bshutil\.rmtree\b', "递归删除目录 (shutil.rmtree)"),
        (r'\bos\.remove\b', "删除文件 (os.remove)"),
        (r'\bos\.rmdir\b', "删除目录 (os.rmdir)"),
        (r'\bsocket\b', "网络连接 (socket)"),
        (r'\brequests?\b', "网络请求 (requests)"),
        (r'\burllib\b', "网络请求 (urllib)"),
    ]

    if not __confirmed:
        dangers = []
        for pattern, desc in DANGER_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                dangers.append(desc)
        if dangers:
            short_code = code.strip()[:200].replace('\n', '\\n')
            return f"__CONFIRM_Python 代码包含以下潜在风险操作：\n" + \
                   "\n".join(f"  • {d}" for d in dangers) + \
                   f"\n\n代码: {short_code}\n\n是否继续执行？"

    def _exec():
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exec(code, {"__builtins__": __builtins__})
            return ("ok", sys.stdout.getvalue())
        except Exception as e:
            return ("err", str(e))
        finally:
            sys.stdout = old_stdout

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(pool, _exec)
            status, output = await asyncio.wait_for(future, timeout=timeout)
            if status == "err":
                return f"Python 错误: {output}"
            return f"Python 输出:\n{output or '(无输出)'}"
        except asyncio.TimeoutError:
            return f"Python 执行超时（>{timeout}秒），代码可能陷入死循环或阻塞操作"
        except Exception as e:
            return f"Python 执行失败: {e}"


async def read_csv(path: str, n: int = 20) -> str:
    """读取 CSV 文件并展示表格预览"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误：文件不存在 - {path}"
    try:
        import csv
        with open(str(p), "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return "CSV 文件为空"
        header = rows[0]
        data = rows[1:]
        lines = [f"CSV: {p.name} ({len(data)} 行, {len(header)} 列)"]
        lines.append(" | ".join(header))
        lines.append("-" * 50)
        for row in data[:n]:
            lines.append(" | ".join(row))
        if len(data) > n:
            lines.append(f"... (还有 {len(data) - n} 行)")
        return "\n".join(lines)
    except Exception as e:
        return f"CSV 读取失败: {e}"


async def system_info() -> str:
    """获取系统资源信息（CPU/内存/磁盘）"""
    import psutil, asyncio
    # 用线程池避免阻塞事件循环
    cpu = await asyncio.to_thread(psutil.cpu_percent, interval=0.3)
    mem = await asyncio.to_thread(psutil.virtual_memory)
    disk = await asyncio.to_thread(psutil.disk_usage, str(Path.home()))
    return (
        f"CPU: {cpu}%\n"
        f"内存: {mem.used / 1024**3:.1f}G / {mem.total / 1024**3:.1f}G ({mem.percent}%)\n"
        f"磁盘: {disk.used / 1024**3:.1f}G / {disk.total / 1024**3:.1f}G ({disk.percent}%)\n"
        f"Python: {__import__('sys').version.split()[0]}"
    )


async def image_info(path: str) -> str:
    """获取图片文件信息（尺寸、格式、EXIF）"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误：文件不存在 - {path}"
    try:
        from PIL import Image
        img = Image.open(str(p))
        info = f"图片: {p.name}\n尺寸: {img.size[0]}x{img.size[1]}\n格式: {img.format}\n模式: {img.mode}"
        try:
            exif = img._getexif()
            if exif:
                import datetime
                for tag, val in exif.items():
                    if tag == 36867:  # DateTimeOriginal
                        info += f"\n拍摄时间: {val}"
                    elif tag == 271:  # Make
                        info += f"\n设备: {val}"
        except Exception:
            pass
        return info
    except ImportError:
        return "错误：未安装 Pillow。pip install Pillow"
    except Exception as e:
        return f"图片读取失败: {e}"


async def screenshot() -> str:
    """截取当前主屏幕并保存为临时文件"""
    import tempfile, os
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        path = os.path.join(tempfile.gettempdir(), f"maona_screenshot_{__import__('time').strftime('%Y%m%d_%H%M%S')}.png")
        img.save(path)
        return f"截图已保存: {path} ({img.size[0]}x{img.size[1]})"
    except ImportError:
        return "错误：未安装 Pillow。pip install Pillow"
    except Exception as e:
        return f"截图失败: {e}"


async def open_browser(url: str) -> str:
    """用系统默认浏览器打开 URL"""
    import webbrowser, asyncio
    await asyncio.to_thread(webbrowser.open, url)
    return f"已在浏览器中打开: {url}"


async def install_pip(package: str) -> str:
    """安装 Python 包（pip install）"""
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        __import__('sys').executable, "-m", "pip", "install", package,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    if proc.returncode == 0:
        return f"pip install {package}: 成功\n{out[:500]}"
    return f"pip install {package}: 失败 (code={proc.returncode})\n{out[:500]}"


async def compress_image(path: str, width: int = None, quality: int = 85, output: str = None) -> str:
    """压缩或调整图片大小"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误：文件不存在 - {path}"
    try:
        from PIL import Image
        img = Image.open(str(p))
        out_path = output or str(p.parent / (p.stem + "_compressed" + p.suffix))
        if width:
            ratio = width / img.size[0]
            img = img.resize((width, int(img.size[1] * ratio)), Image.LANCZOS)
        img.save(out_path, quality=quality, optimize=True)
        size = Path(out_path).stat().st_size
        return f"图片已保存: {out_path} ({img.size[0]}x{img.size[1]}, {size/1024:.0f}KB)"
    except ImportError:
        return "错误：未安装 Pillow。pip install Pillow"
    except Exception as e:
        return f"压缩失败: {e}"


async def clipboard(action: str = "read", text: str = "") -> str:
    """读/写系统剪贴板"""
    try:
        import pyperclip
        if action == "read":
            return pyperclip.paste() or "(剪贴板为空)"
        else:
            pyperclip.copy(text)
            return f"已复制到剪贴板: {text[:50]}"
    except ImportError:
        return "错误：未安装 pyperclip。pip install pyperclip"
    except Exception as e:
        return f"剪贴板操作失败: {e}"


async def zip_archive(action: str, path: str, dest: str = None) -> str:
    """创建或解压 ZIP 压缩包"""
    import zipfile, os
    p = Path(path).expanduser().resolve()
    try:
        if action == "create":
            if not p.exists():
                return f"错误：路径不存在 - {path}"
            dest = dest or str(p) + ".zip"
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                if p.is_dir():
                    for root, _, files in os.walk(str(p)):
                        for f in files:
                            fp = Path(root) / f
                            zf.write(str(fp), str(fp.relative_to(p.parent)))
                else:
                    zf.write(str(p), p.name)
            return f"已创建: {dest} ({Path(dest).stat().st_size/1024:.0f}KB)"
        else:
            dest = dest or str(p.parent)
            with zipfile.ZipFile(str(p), "r") as zf:
                zf.extractall(dest)
            return f"已解压到: {dest}"
    except Exception as e:
        return f"ZIP 操作失败: {e}"


async def notify(title: str = "Maona", message: str = "") -> str:
    """发送桌面通知"""
    try:
        import plyer
        plyer.notification.notify(title=title, message=message, app_name="Maona", timeout=5)
        return f"通知已发送: {title}"
    except ImportError:
        try:
            import subprocess
            # 转义 title 和 message 中的双引号，防止 PowerShell 注入
            safe_title = title.replace('"', '`"').replace('$', '`$').replace('`', '``')
            safe_message = message.replace('"', '`"').replace('$', '`$').replace('`', '``')
            subprocess.run(["powershell", "-Command",
                "$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime];"
                "$null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime];"
                f'$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);'
                f'$t.GetElementsByTagName("text")[0].AppendChild($t.CreateTextNode("{safe_title}"))|Out-Null;'
                f'$t.GetElementsByTagName("text")[1].AppendChild($t.CreateTextNode("{safe_message}"))|Out-Null;'
                f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Maona").Show($t)'
            ], timeout=5)  # 移除 shell=True
            return f"通知已发送: {title}"
        except:
            return "通知发送失败"
    except Exception as e:
        return f"通知失败: {e}"


async def encode_decode(action: str, text: str) -> str:
    """编解码：base64/url/hex/md5/sha256"""
    import base64, hashlib, urllib.parse
    try:
        if action == "base64_encode":
            return base64.b64encode(text.encode()).decode()
        elif action == "base64_decode":
            return base64.b64decode(text).decode("utf-8", errors="replace")
        elif action == "url_encode":
            return urllib.parse.quote(text)
        elif action == "url_decode":
            return urllib.parse.unquote(text)
        elif action == "md5":
            return hashlib.md5(text.encode()).hexdigest()
        elif action == "sha256":
            return hashlib.sha256(text.encode()).hexdigest()
        elif action == "hex":
            return text.encode().hex()
        return f"不支持的操作: {action}。支持: base64_encode/decode, url_encode/decode, md5, sha256, hex"
    except Exception as e:
        return f"编解码失败: {e}"


async def text_to_speech(text: str, lang: str = "zh") -> str:
    """将文字转换为语音并播放"""
    import asyncio
    try:
        import pyttsx3
        def _speak():
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        await asyncio.to_thread(_speak)
        return f"已朗读: {text[:50]}"
    except ImportError:
        try:
            import subprocess, tempfile, os, asyncio
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
                f.write(text)
                tmp = f.name
            try:
                # 用 run_in_executor 避免阻塞
                await asyncio.to_thread(subprocess.run,
                    ["powershell", "-Command",
                     f'Add-Type -AssemblyName System.Speech;'
                     f'$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;'
                     f'$s.Speak([IO.File]::ReadAllText("{tmp}"))'
                    ], timeout=30)
            finally:
                # 确保临时文件被删除
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            return f"已朗读: {text[:50]}"
        except Exception as e2:
            return f"TTS 失败: {e2}"
    except Exception as e:
        return f"TTS 失败: {e}"


async def count_tokens(text: str) -> str:
    """估算文本的 token 数量"""
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    en = len(text) - cn
    tokens = cn + int(en * 0.35)
    return f"字符: {len(text)} | 中文: {cn} | 英文: {en} | 估算 Token: ~{tokens}"

# 会话 token 成本追踪
_cost_records: list[dict] = []

def track_cost(model: str, prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0):
    """记录一次 API 调用的 token 消耗"""
    _cost_records.append({
        "model": model, "prompt": prompt_tokens, "completion": completion_tokens,
        "total": prompt_tokens + completion_tokens, "cost": cost,
        "time": __import__('time').strftime("%H:%M:%S")
    })


async def cost_summary() -> str:
    """查看当前会话的 token 消耗和费用统计（如果 API 返回了 usage 信息）"""
    if not _cost_records:
        return "本会话暂未记录到 token 用量。可能 API 未返回 usage 信息。"
    total_prompt = sum(r["prompt"] for r in _cost_records)
    total_comp = sum(r["completion"] for r in _cost_records)
    total_cost = sum(r["cost"] for r in _cost_records)
    lines = [f"会话成本统计 ({len(_cost_records)} 次调用)",
             f"输入 Token: {total_prompt:,}",
             f"输出 Token: {total_comp:,}",
             f"总计 Token: {total_prompt + total_comp:,}",
             f"估算费用: ¥{total_cost:.4f}"]
    return "\n".join(lines)


# === 幂等性预检查 ===

def _check_idempotent(command: str) -> str | None:
    """在执行命令前检查是否需要（幂等性），不需要则返回提示文本"""
    cmd_lower = command.lower()

    # 1. Start-Process / 启动 GUI 程序 → 检查是否已在运行
    start_match = re.search(r'start-process.*-filepath\s+[\'"]?([^\'"\s;]+\.exe)', cmd_lower)
    if start_match:
        exe_name = Path(start_match.group(1)).name
        import subprocess
        try:
            result = subprocess.run(
                f'tasklist /FI "IMAGENAME eq {exe_name}" 2>nul',
                shell=True, capture_output=True, text=True, timeout=5
            )
            if exe_name.lower() in result.stdout.lower():
                return f"⏭️ 跳过启动 {exe_name}：进程已在运行中。无需重复启动。"
        except Exception:
            pass
        return None  # 进程不存在或无权限查询，允许执行

    # 2. mkdir / New-Item -ItemType Directory → 检查目录是否存在
    mkdir_match = re.search(r'(?:mkdir|New-Item.*-ItemType\s+Directory)\s+[\'"]?([^\'"\s;]+)', command, re.IGNORECASE)
    if mkdir_match:
        dir_path = Path(mkdir_match.group(1).strip('\'"'))
        if dir_path.exists() and dir_path.is_dir():
            return f"⏭️ 跳过创建目录 {dir_path}：目录已存在。无需重复创建。"

    # 3. curl / wget / Invoke-WebRequest 下载 → 检查目标文件是否存在
    dl_match = re.search(r'(?:curl|wget|Invoke-WebRequest|iwr).*?(?:-o|--output|-OutFile)\s+[\'"]?([^\'"\s;]+)', command, re.IGNORECASE)
    if dl_match:
        file_path = Path(dl_match.group(1).strip('\'"'))
        if file_path.exists() and file_path.stat().st_size > 0:
            return f"⏭️ 跳过下载 {file_path}：文件已存在（{file_path.stat().st_size} 字节）。无需重复下载。若需重新下载，请先删除此文件。"

    # 4. npm install / pip install → 检查 node_modules/ 或 site-packages
    if re.search(r'npm\s+install\b', cmd_lower):
        cwd = re.search(r'cd\s+([^\s&;]+)', cmd_lower)
        if cwd:
            node_mod = Path(cwd.group(1)) / "node_modules"
            if node_mod.exists():
                return f"⏭️ 跳过 npm install：{node_mod} 已存在。如需重新安装，请先删除此目录。"

    # 5. git clone → 检查目标目录是否已是 git 仓库
    clone_match = re.search(r'git\s+clone\s+\S+\s+[\'"]?([^\'"\s;]+)', cmd_lower)
    if clone_match:
        target = Path(clone_match.group(1).strip('\'"'))
        if target.exists() and (target / ".git").exists():
            return f"⏭️ 跳过 git clone：{target} 已是 Git 仓库。使用 git pull 更新。"

    return None


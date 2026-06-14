"""部署能力 — 静态站点本地预览 + 打包"""
import subprocess, http.server, socketserver, threading, os
from pathlib import Path


def deploy_preview(directory: str = "", port: int = 8080, **kw) -> str:
    """在本地启动 HTTP 服务器预览静态站点"""
    d = Path(directory).resolve() if directory else Path.cwd()
    if not d.exists():
        return f"目录不存在: {d}"

    # 找入口文件
    index = d / "index.html"
    if not index.exists():
        return f"目录 {d} 中未找到 index.html"

    # 启动简单 HTTP 服务
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(d), **kwargs)

    try:
        server = socketserver.TCPServer(("", port), Handler)
        server.allow_reuse_address = True  # 允许端口 TIME_WAIT 后快速重用
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://localhost:{port}"
        # 尝试打开浏览器
        try:
            import os as _os; _os.startfile(url)
        except:
            pass
        return f"预览已启动: {url}\n目录: {d}\n按 Ctrl+C 停止服务"
    except OSError as e:
        if "Address already in use" in str(e):
            return f"端口 {port} 已被占用，尝试: deploy_preview(directory='{d}', port={port+1})"
        return f"启动失败: {e}"


def deploy_package(directory: str = "", output: str = "", **kw) -> str:
    """打包目录为 ZIP"""
    import zipfile
    d = Path(directory).resolve() if directory else Path.cwd()
    if not d.exists():
        return f"目录不存在: {d}"

    out = Path(output) if output else d.parent / f"{d.name}.zip"
    try:
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fpath in d.rglob("*"):
                if fpath.is_file() and '.git' not in fpath.parts and 'node_modules' not in fpath.parts:
                    zf.write(fpath, fpath.relative_to(d.parent))
        size_mb = out.stat().st_size / 1048576
        return f"打包完成: {out}\n大小: {size_mb:.1f} MB"
    except Exception as e:
        return f"打包失败: {e}"


# 工具映射
DEPLOY_TOOLS = {
    "deploy_preview": deploy_preview,
    "deploy_package": deploy_package,
}

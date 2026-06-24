"""Godot 项目操作 — 初始化、模板、addon 复制"""
import json
import shutil
import asyncio
from pathlib import Path

# 模板目录（空项目骨架）
TEMPLATES = Path(__file__).resolve().parent.parent.parent / "data" / "godot-mcp" / "templates"
ADDONS_SRC = Path(__file__).resolve().parent.parent.parent / "data" / "godot-mcp" / "addons"


def _create_minimal_project(game_dir: Path) -> str:
    """创建最小可运行的 Godot 4 项目"""
    game_dir.mkdir(parents=True, exist_ok=True)

    # project.godot
    cfg = (
        '; Engine configuration file.\n'
        '; It\'s best edited using the editor UI and not directly,\n'
        '; since the parameters that go here are supplied by the editor plugins.\n'
        '[application]\n'
        '\n'
        'config/name="Maona Game"\n'
        'config/features=PackedStringArray("4.5")\n'
        'config/icon="res://icon.svg"\n'
    )
    (game_dir / "project.godot").write_text(cfg, encoding='utf-8-sig')

    # 最小默认场景
    main_scene = (
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" path="res://main.gd" id="1"]\n\n'
        '[node name="Main" type="Node2D"]\n'
        'script = ExtResource("1")\n'
    )
    (game_dir / "main.tscn").write_text(main_scene, encoding='utf-8-sig')

    main_script = (
        'extends Node2D\n\n'
        'func _ready():\n'
        '    print("Hello from Maona!")\n'
    )
    (game_dir / "main.gd").write_text(main_script, encoding='utf-8-sig')

    return f"Godot 项目已创建: {game_dir}"


def godot_setup(game_dir: str = "", **kw) -> str:
    """【已弃用】在目标目录初始化最小 Godot 项目并安装 godot-mcp 插件。
    
    警告：此工具创建的项目结构与 godot-dev Skill 体系不兼容。
    请优先使用 load_skill("godot-dev") 并通过 godot-deploy/godot-new 创建项目。
    """
    if not game_dir:
        return "请提供项目目录路径 (game_dir)"
    
    result = "⚠️ godot_setup 已弃用。推荐使用 load_skill(\"godot-dev\") 进行 Godot 项目创建。\n\n"

    gd = Path(game_dir).resolve()
    if not gd.exists():
        gd.mkdir(parents=True)

    # 如果目录为空，创建骨架
    has_project = (gd / "project.godot").exists()
    if not has_project:
        result = _create_minimal_project(gd)
    else:
        result = f"项目已存在: {gd}"

    # 复制 addon
    addon_dst = gd / "addons" / "godot_mcp"
    if addon_dst.exists():
        shutil.rmtree(str(addon_dst))
    shutil.copytree(str(ADDONS_SRC / "godot_mcp"), str(addon_dst))

    result += f"\ngodot-mcp 插件已安装到 {addon_dst}"
    result += "\n\n下一步:\n1. 用 Godot 编辑器打开该项目\n2. 项目设置 → 插件 → 启用 godot_mcp\n3. 重启 Maona 即可通过 AI 操作 Godot"
    return result


def check_godot_project(project_dir: str = "", **kw) -> str:
    """Godot 项目完整性检查：project.godot / TSCN / 目录结构 / 4.23 合规"""
    import re as _re
    if not project_dir:
        return "请提供项目目录路径 (project_dir)"
    pd = Path(project_dir).resolve()
    if not pd.exists():
        return f"目录不存在: {pd}"
    if not (pd / "project.godot").exists():
        return f"❌ {pd} 不是 Godot 项目（缺少 project.godot）"
    # 前置：文件实际大小检查（防止 write_file 写入空文件/损坏）
    pg_size = (pd / "project.godot").stat().st_size
    if pg_size < 10:
        return f"❌ project.godot 文件异常（仅 {pg_size} 字节），内容不完整"

    issues = []
    ok_count = 0

    # 1. project.godot 完整校验
    content = (pd / "project.godot").read_text(encoding="utf-8-sig")
    # 基础格式：必须以 godot 引擎标识开头
    if not content.strip().startswith(";") and not content.strip().startswith("config_version"):
        issues.append("❌ project.godot 格式异常：不以注释或 config_version 开头，Godot 无法识别")
    else:
        if 'config_version=5' in content: ok_count += 1
        else: issues.append("❌ project.godot 缺少 config_version=5（非 Godot 4 项目）")
    if 'config/name=' in content: ok_count += 1
    else: issues.append("❌ project.godot 缺少 config/name（Godot 项目必须有名��）")
    # 验证默认总线布局引用（新版 Godot 4 可能需要）
    if 'run/main_scene' in content:
        main_scene = _re.search(r'run/main_scene\s*=\s*"([^"]+)"', content)
        if main_scene:
            ms_path = main_scene.group(1).replace("res://", "")
            if not (pd / ms_path).exists():
                issues.append(f"❌ project.godot run/main_scene 指向不存在的场景: {ms_path}")
    if '[rendering]' in content: ok_count += 1
    else: issues.append("⚠️ project.godot 缺少 [rendering] 段")

    # 2. TSCN 格式检查
    tscn_files = list(pd.rglob("*.tscn"))
    if tscn_files:
        for tf in sorted(tscn_files):
            tf_content = tf.read_text(encoding="utf-8-sig")
            rel = tf.relative_to(pd)
            bad_exprs = _re.findall(r'= *(\w+\.\w+\.new\(\))', tf_content)
            for expr in bad_exprs:
                issues.append(f"❌ {rel}: TSCN 含非法 GDScript 表达式 {expr}")
            for m in _re.finditer(r'path="res://([^"]+)"', tf_content):
                rp = m.group(1)
                if rp.endswith(".gd") and not (pd / rp).exists():
                    issues.append(f"❌ {rel}: 引用不存在的脚本 res://{rp}")
        ok_count += 1

    # 3. Autoload 脚本存在性
    if '[autoload]' in content:
        for m in _re.finditer(r'(\w+)="\*res://([^"]+)"', content):
            if (pd / m.group(2)).exists(): ok_count += 1
            else: issues.append(f"❌ Autoload '{m.group(1)}' 脚本不存在: {m.group(2)}")

    # 4. 4.23 合规（active-game.json + godot-editor 位置）
    parent = pd.parent
    ag_p = parent / "active-game.json"
    if ag_p.exists():
        try:
            ag = json.loads(ag_p.read_text(encoding="utf-8-sig"))
            if Path(ag.get("gameDir", "")).resolve() == pd: ok_count += 1
            else: issues.append(f"❌ active-game.json gameDir 与当前目录不一致")
        except Exception: issues.append("⚠️ active-game.json 无法解析")
    else: issues.append("⚠️ 根目录缺少 active-game.json")
    if (parent / "godot-editor").exists(): ok_count += 1
    else: issues.append("⚠️ 根目录缺少 godot-editor/")

    # 5. 关键目录
    for d in ["scenes", "scripts", "data"]:
        if (pd / d).is_dir(): ok_count += 1
        else: issues.append(f"⚠️ 缺少 {d}/ 目录")

    if not issues:
        return f"✅ Godot 项目完整性通过（{ok_count} 项 OK）"
    return f"## Godot 项目完整性报告\n{ok_count} 通过 / {len(issues)} 问题\n" + "\n".join(issues)


async def verify_scene(project_dir: str = "", scene_path: str = "", **kw) -> str:
    """在 Godot 编辑器中加载场景并做运行时诊断：节点树、脚本附加、信号连接、push_error 捕获。
    加载场景后运行一帧，捕获所有 push_error/push_warning 输出。需要 Godot 编辑器运行中。"""
    if not project_dir:
        return "请提供项目目录 (project_dir)"
    if not scene_path:
        return "请提供场景路径 (scene_path, 如 res://scenes/main.tscn)"

    pd = Path(project_dir).resolve()
    if not (pd / "project.godot").exists():
        return f"❌ {pd} 不是 Godot 项目"

    code = f'''
var _errors = []
var _warnings = []

func _handle_error(msg):
    _errors.append(msg)

func _handle_warning(msg):
    _warnings.append(msg)

# 捕获错误
var _old_err = ProjectSettings.get_setting("debug/file_logging/enable_file_logging")
push_error.connect(_handle_error, CONNECT_ONE_SHOT) if push_error.is_connected(_handle_error) else push_error.connect(_handle_error)
push_warning.connect(_handle_warning, CONNECT_ONE_SHOT) if push_warning.is_connected(_handle_warning) else push_warning.connect(_handle_warning)

# 加载场景
var _s = load("{scene_path}")
if _s:
    var _n = _s.instantiate()
    print("VERIFY: 场景加载成功 - " + _n.name + " (" + _n.get_class() + ")")
    var _children = _n.get_children()
    print("VERIFY: 子节点数: " + str(len(_children)))
    for _c in _children:
        var _script = ""
        if _c.get_script():
            _script = " [脚本: " + _c.get_script().resource_path + "]"
        print("VERIFY:   " + _c.name + " (" + _c.get_class() + ")" + _script)
    _n.queue_free()
    if _errors:
        print("VERIFY ERRORS:")
        for _e in _errors:
            print("  🔴 " + str(_e))
    if _warnings:
        print("VERIFY WARNINGS:")
        for _w in _warnings:
            print("  🟡 " + str(_w))
else:
    push_error("VERIFY FAIL: 无法加载场景 " + "{scene_path}")
'''
    try:
        from tools.mcp_client import call_mcp_tool
        result = await call_mcp_tool("execute_editor_script", {"code": code})
        if "错误" in result:
            return f"⚠️ MCP 不可用，跳过运行时验证。错误: {result}"
        return result
    except Exception as e:
        return f"⚠️ MCP 调用失败: {e}"


async def get_godot_errors(project_dir: str = "", **kw) -> str:
    """获取 Godot 项目最近的错误和警告日志，包括 F5 运行时的崩溃信息。"""
    pd = Path(project_dir).resolve() if project_dir else None
    results = []

    # 1. 读取 Godot 编辑器日志（%APPDATA%/Godot/）
    import os as _os
    appdata = _os.environ.get("APPDATA", "")
    log_paths = [
        Path(appdata) / "Godot" / "app_userdata" / (pd.name if pd else "galgame") / "logs",
        Path(appdata) / "Godot" / "logs",
    ]
    for log_dir in log_paths:
        if log_dir.exists():
            for log_file in sorted(log_dir.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)[:1]:
                content = log_file.read_text(encoding="utf-8-sig", errors="replace")
                # 提取最近 50 行的 ERROR/WARNING
                lines = content.split("\n")
                errors = [l for l in lines[-200:] if "ERROR" in l.upper() or "SCRIPT ERROR" in l.upper()]
                if errors:
                    results.append(f"\n📄 {log_file.name} ({len(errors)} 条错误):")
                    for e in errors[-20:]:
                        results.append(f"  {e.strip()[:200]}")
                else:
                    results.append(f"\n📄 {log_file.name}: 无错误")
                break

    if not results:
        results.append("未找到 Godot 日志文件。尝试通过编辑器脚本获取...")

    # 2. 尝试通过 MCP 获取编辑器输出面板
    try:
        from tools.mcp_client import call_mcp_tool
        code = '''
var _output = ""
for _m in EditorInterface.get_editor_toaster().get_version():
    pass
# 使用简单方式读取输出
var _editor_log = EditorInterface.get_editor_paths().get_project_settings_dir()
print("LOG DIR: " + _editor_log)
'''
        r = await call_mcp_tool("execute_editor_script", {"code": code})
        if "错误" not in r:
            results.append(f"\n编辑器信息: {r[:300]}")
    except Exception:
        pass

    return "\n".join(results) if results else "未找到任何错误日志"


GODOT_TOOLS = {
    "godot_setup": godot_setup,
    "check_godot_project": check_godot_project,
    "verify_scene": verify_scene,
    "get_godot_errors": get_godot_errors,
}


# ===== 通用项目验证器 =====

def validate_project(project_dir: str = "", **kw) -> str:
    """通用项目验证器 — 自动检测项目类型并运行对应检查。
    支持: python (pytest+pylint), web (HTML/JS 语法), godot (现有验证链), generic (文件结构)。
    
    Args:
        project_dir: 项目根目录路径
    """
    if not project_dir:
        return "请提供项目目录 (project_dir)"
    pd = Path(project_dir).resolve()
    if not pd.exists():
        return f"目录不存在: {pd}"

    results = []
    detections = []

    # 检测项目类型
    if (pd / "project.godot").exists():
        detections.append("godot")
    if list(pd.glob("*.py")) or (pd / "requirements.txt").exists() or (pd / "pyproject.toml").exists():
        detections.append("python")
    if list(pd.glob("*.html")) or (pd / "package.json").exists():
        detections.append("web")

    if not detections:
        # 基础文件结构检查
        files = list(pd.rglob("*"))
        gd = len([f for f in files if f.suffix == ".gd"])
        py = len([f for f in files if f.suffix == ".py"])
        html = len([f for f in files if f.suffix == ".html"])
        results.append(f"📂 项目概览: {gd} .gd, {py} .py, {html} .html, {len(files)} 总文件")
        return "\n".join(results) if results else "未检测到可识别的项目类型"

    for dt in detections:
        results.append(f"\n## {dt.upper()} 检查")

        if dt == "python":
            results.extend(_check_python(pd))
        elif dt == "web":
            results.extend(_check_web(pd))
        elif dt == "godot":
            results.extend(_check_godot(pd))

    return "\n".join(results) if results else "验证完成，未发现问题"


def _check_python(pd: Path) -> list:
    lines = []
    py_files = list(pd.rglob("*.py"))
    if not py_files:
        lines.append("  未找到 .py 文件")
        return lines

    lines.append(f"  📄 {len(py_files)} 个 Python 文件")

    # 语法检查
    syntax_errors = 0
    for f in py_files:
        try:
            compile(f.read_text(encoding="utf-8-sig"), str(f), "exec")
        except SyntaxError as e:
            lines.append(f"  🔴 语法错误: {f.name}:{e.lineno} - {e.msg}")
            syntax_errors += 1
    if syntax_errors == 0:
        lines.append("  ✓ 语法检查: 全部通过")

    # 依赖检查（标准库白名单）
    import re as _re
    STDLIB = frozenset({"os","sys","re","json","time","pathlib","datetime","asyncio","subprocess",
        "collections","typing","io","math","random","hashlib","base64","uuid","functools",
        "itertools","logging","argparse","shutil","tempfile","concurrent","threading","multiprocessing",
        "ast","inspect","unittest","warnings","traceback","copy","textwrap","dataclasses","enum","statistics"})
    missing = set()
    for f in py_files:
        for m in _re.finditer(r'(?:from\s+(\S+)\s+import|import\s+(\S+))', f.read_text(encoding="utf-8-sig"), _re.MULTILINE):
            mod = (m.group(1) or m.group(2) or "").split(".")[0]
            if mod and mod not in STDLIB and not mod.startswith("."):
                missing.add(mod)
    if missing:
        lines.append(f"  🟡 可能需要安装: {', '.join(sorted(missing)[:5])}")
    else:
        lines.append("  ✓ 依赖检查: 全部标准库或已安装")

    return lines


def _check_web(pd: Path) -> list:
    lines = []
    html_files = list(pd.rglob("*.html"))
    js_files = list(pd.rglob("*.js"))
    lines.append(f"  📄 {len(html_files)} HTML, {len(js_files)} JS")

    # HTML 基本结构检查
    for f in html_files[:10]:  # 只检查前10个
        content = f.read_text(encoding="utf-8-sig", errors="replace")
        if "<!DOCTYPE html>" not in content and "<!doctype html>" not in content.lower():
            lines.append(f"  🟡 {f.name}: 缺少 DOCTYPE 声明")
        if "<title>" not in content:
            lines.append(f"  🟡 {f.name}: 缺少 <title>")

    if not lines[1:]:  # 只有标题行
        lines.append("  ✓ 基本结构检查: 通过")

    # package.json 检查
    pkg = pd / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8-sig"))
            deps = data.get("dependencies", {})
            dev = data.get("devDependencies", {})
            lines.append(f"  📦 package.json: {len(deps)} deps + {len(dev)} devDeps")
        except Exception:
            lines.append("  🔴 package.json 格式错误")

    return lines


def _check_godot(pd: Path) -> list:
    """回退到现有 Godot 验证链"""
    lines = []
    from tools.gdscript_lint import validate_gdscript
    result = validate_gdscript(str(pd))
    reds = [l for l in result.split("\n") if "🔴" in l]
    lines.append(f"  GDScript: {len(reds)} 个 🔴 错误")
    for r in reds[:5]:
        lines.append(f"    {r.strip()}")


def verify_project_opens(project_dir: str = "", **kw) -> str:
    """用 Godot CLI 实际加载项目做全量校验。比静态检查更可靠，能捕获 TSCN/脚本/资源加载错误。"""
    import subprocess, glob as _glob, os
    if not project_dir:
        return "请提供 project_dir"
    pd = Path(project_dir).resolve()
    if not pd.exists():
        return f"❌ 目录不存在: {pd}"
    if not (pd / "project.godot").exists():
        return f"❌ 不是 Godot 项目（无 project.godot）"
    # 找 Godot 编辑器（先查工作空间，再查系统）
    parent = pd.parent
    editors = _glob.glob(str(parent / "godot-editor" / "Godot_v*.exe"))
    if not editors:
        editors = _glob.glob(str(parent / "godot-editor" / "Godot*.exe"))
    if not editors:
        return "❌ 找不到 Godot 编辑器（godot-editor/ 下无 Godot_v*.exe），无法做运行时验证"
    editor = editors[0]
    try:
        r = subprocess.run(
            [editor, "--headless", "--check-only", "--path", str(pd)],
            capture_output=True, text=True, timeout=30, cwd=str(pd)
        )
        output = (r.stdout + r.stderr).strip()
        if r.returncode == 0 and ("ERROR" not in output.upper() or "0 errors" in output.lower()):
            return f"✅ Godot 项目加载验证通过\n{output[:500]}"
        else:
            # 提取错误
            errors = [l for l in output.split("\n") if "ERROR" in l.upper() or "error" in l.lower()]
            if not errors:
                errors = [l for l in output.split("\n") if l.strip()][-10:]
            return f"❌ Godot 加载失败 (exit={r.returncode})\n{chr(10).join(errors[:10])}\n\n完整输出:\n{output[-1000:]}"
    except subprocess.TimeoutExpired:
        return "❌ Godot 验证超时（30秒）"
    except Exception as e:
        return f"❌ 运行 Godot 失败: {e}"
    return lines

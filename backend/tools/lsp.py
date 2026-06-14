"""LSP 集成 — 代码智能（补全、诊断、跳转定义）"""
import subprocess, json
from pathlib import Path


def _find_python_file(filepath: str) -> Path:
    """解析文件路径"""
    p = Path(filepath)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def lsp_diagnose(filepath: str = "", **kw) -> str:
    """Python 语法/类型检查（使用 py_compile + mypy 回退）"""
    p = _find_python_file(filepath) if filepath else None
    if not p or not p.exists():
        return "请提供有效的 Python 文件路径"

    results = []
    try:
        # Python compile 检查
        src = p.read_text(encoding='utf-8')
        compile(src, str(p), 'exec')
        results.append("[compile] 语法检查通过")
    except SyntaxError as e:
        results.append(f"[compile] 语法错误: {e.msg} (行 {e.lineno}, 列 {e.offset})")

    # mypy 类型检查
    try:
        r = subprocess.run(
            ["mypy", "--no-error-summary", str(p)],
            capture_output=True, text=True, timeout=30, cwd=str(p.parent)
        )
        if r.stdout.strip():
            results.append(f"[mypy]\n{r.stdout.strip()[:2000]}")
        else:
            results.append("[mypy] 类型检查通过")
    except FileNotFoundError:
        results.append("[mypy] 未安装，跳过类型检查")
    except subprocess.TimeoutExpired:
        results.append("[mypy] 超时")

    return "\n\n".join(results)


def lsp_references(filepath: str = "", symbol: str = "", **kw) -> str:
    """搜索符号引用（grep 实现）"""
    p = _find_python_file(filepath) if filepath else None
    base = p.parent if p else Path.cwd()
    if not symbol:
        return "请提供要搜索的符号名称"

    try:
        r = subprocess.run(
            ["rg", "--no-heading", "-n", "-w", symbol, "--", str(base)],
            capture_output=True, text=True, timeout=10
        )
        lines = r.stdout.strip().split('\n')[:50]
        return '\n'.join(lines) if lines[0] else f"未找到 '{symbol}' 的引用"
    except FileNotFoundError:
        # rg 不可用，回退 grep
        try:
            r = subprocess.run(
                ["grep", "-rn", "-w", symbol, "--include=*.py", str(base)],
                capture_output=True, text=True, timeout=10
            )
            lines = r.stdout.strip().split('\n')[:50]
            return '\n'.join(lines) if lines[0] else f"未找到 '{symbol}' 的引用"
        except FileNotFoundError:
            return "grep 不可用"


def lsp_hover(filepath: str = "", line: int = 0, **kw) -> str:
    """查看指定行的上下文（前后各 3 行）"""
    p = _find_python_file(filepath) if filepath else None
    if not p or not p.exists():
        return "请提供有效的文件路径"

    lines = p.read_text(encoding='utf-8').split('\n')
    if line <= 0 or line > len(lines):
        return f"行号 {line} 超出范围 (1-{len(lines)})"

    start = max(0, line - 4)
    end = min(len(lines), line + 3)
    result = []
    for i in range(start, end):
        marker = ">>>" if i == line - 1 else "   "
        result.append(f"{marker} {i+1:4d}| {lines[i]}")
    return '\n'.join(result)


def lsp_outline(filepath: str = "", **kw) -> str:
    """提取文件大纲（类/函数定义）"""
    p = _find_python_file(filepath) if filepath else None
    if not p or not p.exists():
        return "请提供有效的文件路径"

    import re
    lines = p.read_text(encoding='utf-8').split('\n')
    outline = []
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if re.match(r'^(def |class |async def )', stripped):
            indent = len(line) - len(stripped)
            outline.append(f"{'  ' * (indent // 4)}{stripped[:120]}  (行 {i})")
    return '\n'.join(outline) if outline else "未找到函数或类定义"


def lsp_format(filepath: str = "", **kw) -> str:
    """格式化代码（black）"""
    p = _find_python_file(filepath) if filepath else None
    if not p or not p.exists():
        return "请提供有效的 Python 文件路径"

    try:
        r = subprocess.run(
            ["black", "--diff", str(p)],
            capture_output=True, text=True, timeout=30, cwd=str(p.parent)
        )
        if r.returncode == 0:
            return "代码格式已符合 black 规范"
        return f"建议格式修改:\n{r.stdout[:3000]}"
    except FileNotFoundError:
        return "black 未安装，跳过格式化检查"


# 工具映射
LSP_TOOLS = {
    "lsp_diagnose": lsp_diagnose,
    "lsp_references": lsp_references,
    "lsp_hover": lsp_hover,
    "lsp_outline": lsp_outline,
    "lsp_format": lsp_format,
}

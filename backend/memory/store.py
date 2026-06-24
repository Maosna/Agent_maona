"""记忆存储层 - 按项目隔离，支持工作空间本地存储"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# 默认记忆根目录（无工作空间时使用）
DEFAULT_ROOT = Path.home() / ".agent_maona" / "memory"
try:
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
except (OSError, PermissionError):
    # 沙箱/托管环境回退到用户临时目录
    import tempfile
    DEFAULT_ROOT = Path(tempfile.gettempdir()) / "agent_maona" / "memory"
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, content: str):
    """原子写入：先写临时文件再替换，防止并发损坏"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

# 全局用户偏好文件（始终在默认目录）
PREFS_FILE = DEFAULT_ROOT / "global" / "user_prefs.json"


def _memory_dir(project: str, workspace: str = None) -> Path:
    """
    获取记忆目录。
    - 有 workspace → {workspace}/.maona/
    - 无 workspace → ~/.agent_maona/memory/{project}/
    """
    if workspace:
        d = Path(workspace) / ".maona"
    else:
        d = DEFAULT_ROOT / project
    d.mkdir(parents=True, exist_ok=True)
    return d


# ========== 项目记忆 ==========

def read_daily(project: str, date_str: str = None, workspace: str = None) -> str:
    """读取某天的记忆"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    f = _memory_dir(project, workspace) / f"{date_str}.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def append_daily(project: str, content: str, date_str: str = None, workspace: str = None) -> None:
    """追加每日记忆（超 8000 字符时归档旧内容，防止数据丢失）"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    f = _memory_dir(project, workspace) / f"{date_str}.md"
    existing = f.read_text(encoding="utf-8") if f.exists() else ""
    new = (existing + "\n" + content if existing else content)
    if len(new) > 8000:
        old_path = f.with_suffix(".old.md")
        old_path.write_text(existing, encoding="utf-8")
        new = "...(旧内容已归档到 " + old_path.name + ")\n\n" + content[-8000:]
    _atomic_write(f, new)


def read_longterm(project: str, workspace: str = None) -> str:
    """读取项目长期记忆"""
    f = _memory_dir(project, workspace) / "MEMORY.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def write_longterm(project: str, content: str, workspace: str = None) -> None:
    """写入项目长期记忆"""
    f = _memory_dir(project, workspace) / "MEMORY.md"
    _atomic_write(f, content) if content else f.write_text(content, encoding="utf-8")


# ========== 全局用户偏好（跨项目共享，始终在默认目录） ==========

def read_prefs() -> dict:
    """读取全局用户偏好"""
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def update_prefs(key: str, value) -> None:
    """更新全局偏好"""
    prefs = read_prefs()
    prefs[key] = value
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(PREFS_FILE, json.dumps(prefs, ensure_ascii=False, indent=2))


def get_pref(key: str, default=None):
    """获取单个偏好值"""
    return read_prefs().get(key, default)


# ========== 项目列表 ==========

def list_projects() -> list[str]:
    """列出所有项目（默认目录下的）"""
    if not DEFAULT_ROOT.exists():
        return []
    return sorted([
        d.name for d in DEFAULT_ROOT.iterdir()
        if d.is_dir() and d.name != "global"
    ])


def list_daily_logs(project: str, workspace: str = None) -> list[dict]:
    """列出工作空间或项目的每日日志（按日期倒序）"""
    d = _memory_dir(project, workspace)
    logs = []
    for f in sorted(d.glob("*.md"), reverse=True):
        name = f.stem  # e.g. "2026-05-26"
        # 读取第一段作为预览
        text = f.read_text(encoding="utf-8")[:300]
        preview = text.split("\n")[0] if text else ""
        logs.append({"date": name, "preview": preview, "file": f.name})
    return logs

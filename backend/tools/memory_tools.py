"""记忆操作工具 - AI 可以读写项目记忆"""
import json
from datetime import datetime
from pathlib import Path
from memory import store as mem_store


async def save_memory(content: str, category: str = "general", **kw) -> str:
    """保存一条长期记忆到 MEMORY.md"""
    if not content.strip():
        return "错误：内容为空"
    entry = f"- [{category}] {content.strip()}"
    existing = mem_store.read_longterm("agent_maona")
    # 精确行匹配，避免子串误判
    existing_lines = [l.strip() for l in existing.split("\n") if l.strip()]
    if entry.strip() in existing_lines:
        return "已存在相同记忆，跳过"
    new_content = (existing + "\n" + entry).strip() if existing.strip() else entry
    mem_store.write_longterm("agent_maona", new_content)
    return f"已保存记忆 [{category}]: {content[:100]}"


async def read_memory(query: str = "") -> str:
    """读取长期记忆，可选关键词过滤"""
    content = mem_store.read_longterm("agent_maona")
    if not content.strip():
        return "暂无长期记忆"
    if query:
        lines = content.split("\n")
        matches = [l for l in lines if query.lower() in l.lower()]
        if not matches:
            return f"记忆中未找到与「{query}」相关的内容"
        return f"搜索记忆「{query}」结果:\n" + "\n".join(matches[:20])
    return f"长期记忆:\n{content[:2000]}"


async def save_daily_log(content: str, **kw) -> str:
    """追加一条今天的日志"""
    today = datetime.now().strftime("%Y-%m-%d")
    mem_store.append_daily("agent_maona", content.strip(), today)
    return f"已追加今日日志: {content[:100]}"


def save_bug_fix(error_pattern: str, fix_description: str, file_path: str = "", **kw) -> str:
    """记录一个错误及其修复方案，供未来同类问题自动参考。
    
    Args:
        error_pattern: 错误关键词或正则片段（如 'TSCN load_steps 不一致'）
        fix_description: 修复步骤（如 '手动更新 load_steps=N，使其匹配文件中的 ext_resource 数量'）
        file_path: 出错文件的路径
    """
    workspace = os.environ.get("MAONA_WORKSPACE", "")
    bugs_file = Path(workspace) / ".maona" / "known_bugs.json" if workspace else Path("known_bugs.json")
    bugs_file.parent.mkdir(parents=True, exist_ok=True)
    
    bugs = []
    if bugs_file.exists():
        try:
            bugs = json.loads(bugs_file.read_text(encoding="utf-8"))
        except Exception:
            bugs = []
    
    entry = {
        "error": error_pattern.strip(),
        "fix": fix_description.strip(),
        "file": file_path,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    # 去重
    for b in bugs:
        if b["error"] == entry["error"]:
            b["fix"] = entry["fix"]
            b["time"] = entry["time"]
            break
    else:
        bugs.append(entry)
    
    bugs_file.write_text(json.dumps(bugs, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"已记录错误修复: {error_pattern[:80]}"


# 在上下文注入中暴露已知错误
def get_known_bugs(workspace: str = "") -> str:
    """读取工作空间的已知错误列表，注入到 prompt 中"""
    bugs_file = Path(workspace) / ".maona" / "known_bugs.json" if workspace else Path("known_bugs.json")
    if not bugs_file.exists():
        return ""
    try:
        bugs = json.loads(bugs_file.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not bugs:
        return ""
    lines = ["\n## ⚠️ 已知错误及修复方案（来自 previous sessions）"]
    for b in bugs[-10:]:  # 最近 10 条
        lines.append(f"- 错误: {b['error']}")
        lines.append(f"  修复: {b['fix']}")
        if b.get("file"):
            lines.append(f"  文件: {b['file']}")
    return "\n".join(lines)


import os

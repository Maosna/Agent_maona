"""上下文构建 - 把记忆组装成 LLM 可用的上下文"""
from datetime import datetime, timedelta
from pathlib import Path
from . import store

MAX_CONTEXT_CHARS = 4000  # 上下文总上限


def build_context(project: str, workspace: str = None, include_today: bool = True) -> str:
    """为 LLM 构建当前项目的记忆上下文。会注入最近 3 天的工作日志，总计不超过 {MAX_CONTEXT_CHARS} 字符。"""
    parts = []

    # 0. 工作空间自定义规则 (.maona/rules.md)
    if workspace:
        rules_path = Path(workspace) / ".maona" / "rules.md"
        if rules_path.exists():
            rules = rules_path.read_text(encoding="utf-8").strip()
            if rules:
                parts.append(f"## 工作空间规则（必须遵守）\n{rules[:1500]}")

    # 1. 长期记忆
    longterm = store.read_longterm(project, workspace)
    if longterm.strip():
        parts.append(f"## 项目长期记忆\n{longterm[:2000]}")

    # 2. 最近 3 天工作日志（今天 + 前 2 天）
    if include_today:
        today = datetime.now()
        recent_days = []
        for i in range(3):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            content = store.read_daily(project, date_str, workspace)
            if content.strip():
                label = "今天的工作日志" if i == 0 else f"{date_str} 的工作日志"
                # 每天日志取最后部分（最新内容优先），每天最多 1500 字符
                recent_days.append(f"## {label}\n{content[-1500:]}")
        if recent_days:
            parts.append("\n\n".join(recent_days))

    # 3. 全局用户偏好（过滤无关字段）
    prefs = store.read_prefs()
    relevant_prefs = {k: v for k, v in prefs.items()
                      if k not in ("last_model", "workspaces", "default_workspace") and v}
    if relevant_prefs:
        pref_lines = [f"- {k}: {v}" for k, v in relevant_prefs.items()]
        parts.append(f"## 用户偏好\n" + "\n".join(pref_lines))

    result = "\n\n".join(parts) if parts else ""
    # 智能截断：优先保留用户偏好+规则（头部），截断工作日志（尾部）
    if len(result) > MAX_CONTEXT_CHARS:
        # 找到工作日志开始位置
        log_start = result.find("## 工作日志")
        if log_start > 0:
            keep_head = result[:log_start]
            head_len = len(keep_head)
            remaining = MAX_CONTEXT_CHARS - head_len - 50
            if remaining > 200:
                result = keep_head + "\n\n...(工作日志已截断)\n\n" + result[-(remaining):]
            else:
                result = keep_head[:MAX_CONTEXT_CHARS - 50] + "\n\n...(内容已截断)"
        else:
            result = "...(早期内容已截断)\n\n" + result[-(MAX_CONTEXT_CHARS - 50):]
    return result


def get_recent_context(project: str, days: int = 3, workspace: str = None) -> str:
    """获取最近 N 天的记忆"""
    parts = []
    today = datetime.now()
    for i in range(days):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        content = store.read_daily(project, date_str, workspace)
        if content.strip():
            parts.append(f"## {date_str}\n{content}")

    return "\n\n".join(parts) if parts else ""

"""工作流记忆（程序记忆）—— 记住用户的操作模式

存储格式: {
  "pattern": ["数据分析", "csv"],
  "pipeline": [
    {"tool": "read_csv", "params": {"path": "..."}},
    {"tool": "run_python", "params": {"code": "..."}},
  ],
  "success_count": 5,
  "last_used": "2026-06-13T16:00:00",
}
"""

import json
import time
from pathlib import Path
from datetime import datetime

WORKFLOW_PATH = Path.home() / ".agent_maona" / "procedural_memory.json"


def _load() -> list[dict]:
    if WORKFLOW_PATH.exists():
        try:
            return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass
    return []


def _save(workflows: list[dict]):
    WORKFLOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = WORKFLOW_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(workflows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(WORKFLOW_PATH)


def record_workflow(pattern_keywords: list[str], tool_sequence: list[dict]):
    """记录一次成功的工作流"""
    workflows = _load()
    key = json.dumps(sorted(pattern_keywords))

    for w in workflows:
        if json.dumps(sorted(w.get("pattern", []))) == key:
            w["success_count"] = w.get("success_count", 0) + 1
            w["last_used"] = datetime.now().isoformat()
            w["pipeline"] = tool_sequence  # 更新为最新成功的管道
            _save(workflows)
            return

    workflows.append({
        "pattern": pattern_keywords,
        "pipeline": tool_sequence,
        "success_count": 1,
        "last_used": datetime.now().isoformat(),
    })
    # 保留最近 50 条
    if len(workflows) > 50:
        workflows.sort(key=lambda x: x.get("success_count", 0), reverse=True)
        workflows = workflows[:50]
    _save(workflows)


def suggest_workflow(user_intent: str, top_k: int = 3) -> list[dict]:
    """根据用户意图匹配最佳工作流"""
    workflows = _load()
    if not workflows:
        return []

    # 简单关键词匹配打分
    scored = []
    intent_lower = user_intent.lower()
    for w in workflows:
        pattern = w.get("pattern", [])
        matches = 0
        for kw in pattern:
            kw_lower = kw.lower()
            # 精确或子串匹配
            if kw_lower in intent_lower or any(
                p in kw_lower for p in intent_lower.split()
                if len(p) >= 2
            ):
                matches += 1
        if matches > 0:
            score = matches + w.get("success_count", 0) * 0.1
            scored.append((score, w))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [w for _, w in scored[:top_k]]


def get_system_prompt_hint(user_intent: str) -> str:
    """生成系统提示词注入：推荐的执行管道"""
    workflows = suggest_workflow(user_intent, top_k=2)
    if not workflows:
        return ""

    lines = ["\n## 历史工作流参考（你曾经成功执行过以下模式）"]
    for w in workflows:
        pattern = "、".join(w.get("pattern", []))
        steps = " → ".join(
            f"{s.get('tool', '?')}({str(s.get('params', {}))[:50]})"
            for s in w.get("pipeline", [])[:5]
        )
        lines.append(
            f"- 场景[{pattern}]: {steps}"
            f"（{w.get('success_count', 0)}次成功）"
        )
    return "\n".join(lines)

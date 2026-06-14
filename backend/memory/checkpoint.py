"""检查点恢复 —— 长任务中断后从断点续跑

存储完整的 Agent 执行状态：
- 对话历史 (messages)
- 任务列表 (task_registry)
- 环境缓存 (env_cache)
- 执行进度 (plan_state)
"""

import json
import time
import asyncio
from pathlib import Path
from datetime import datetime

CHECKPOINT_DIR = Path.home() / ".agent_maona" / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def create_checkpoint(conv_id: str, state: dict) -> str:
    """创建检查点，返回检查点 ID"""
    ts = int(time.time())
    cid = f"{conv_id}_{ts}"
    path = CHECKPOINT_DIR / f"{cid}.json"

    checkpoint = {
        "id": cid,
        "conv_id": conv_id,
        "created_at": datetime.now().isoformat(),
        "state": state,
    }

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return cid


def load_checkpoint(checkpoint_id: str) -> dict | None:
    """加载检查点"""
    path = CHECKPOINT_DIR / f"{checkpoint_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return None


def list_checkpoints(conv_id: str = None) -> list[dict]:
    """列出检查点"""
    results = []
    for f in sorted(CHECKPOINT_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if conv_id and data.get("conv_id") != conv_id:
                continue
            results.append({
                "id": data["id"],
                "conv_id": data.get("conv_id", ""),
                "created_at": data.get("created_at", ""),
                "summary": str(data.get("state", {}).get("summary", ""))[:80],
            })
        except Exception:
            continue
    return results[:20]


def delete_checkpoint(checkpoint_id: str):
    """删除检查点"""
    path = CHECKPOINT_DIR / f"{checkpoint_id}.json"
    if path.exists():
        path.unlink()


def cleanup_old(max_age_days: int = 7, keep_min: int = 10):
    """清理过期检查点"""
    cutoff = time.time() - max_age_days * 86400
    all_checks = sorted(
        [(f, f.stat().st_mtime) for f in CHECKPOINT_DIR.glob("*.json")],
        key=lambda x: x[1], reverse=True
    )
    for f, mtime in all_checks[keep_min:]:
        if mtime < cutoff:
            try:
                f.unlink()
            except Exception:
                pass


async def auto_checkpoint(conv_id: str, messages: list, tasks: dict = None,
                          summary: str = "", interval: int = 60) -> str | None:
    """异步自动保存检查点（每 interval 秒）"""
    last_save = 0
    while True:
        await asyncio.sleep(interval)
        if not messages:
            continue
        now = time.time()
        if now - last_save < interval:
            continue
        last_save = now
        state = {
            "messages": [{"role": m.get("role", ""), "content": str(m.get("content", ""))[:500]}
                         for m in messages[-10:]],
            "message_count": len(messages),
            "tasks": tasks or {},
            "summary": summary,
            "saved_at": datetime.now().isoformat(),
        }
        cid = create_checkpoint(conv_id, state)
        return cid

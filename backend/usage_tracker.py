"""用量追踪 — 记录每请求的 token 消耗和成本"""
import os
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".agent_maona" / "usage.db"
_db_initialized = False

# 模型定价表（每百万 token，美元）
PRICING = {
    "deepseek-v4-flash":    {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro":      {"input": 0.14, "output": 0.28},
    "deepseek-chat":        {"input": 0.14, "output": 0.28},
    "deepseek-reasoner":    {"input": 0.55, "output": 2.19},
    "deepseek":             {"input": 0.14, "output": 0.28},
    "glm-4-flash":          {"input": 0.00, "output": 0.00},
    "glm-4":                {"input": 0.014, "output": 0.014},
    "glm":                  {"input": 0.014, "output": 0.014},
    "qwen":                 {"input": 0.00, "output": 0.00},
}


def _get_db() -> sqlite3.Connection:
    global _db_initialized
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    if not _db_initialized:
        db.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                timestamp TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT DEFAULT '',
                conversation_id TEXT DEFAULT '',
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                tokens_total INTEGER DEFAULT 0,
                cost REAL DEFAULT 0.0,
                prompt_preview TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_logs(timestamp)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_logs(model)")
        db.commit()
        _db_initialized = True
    return db


def calc_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """计算请求成本（美元）"""
    for key, price in PRICING.items():
        if key in model.lower():
            return (tokens_input / 1_000_000) * price["input"] + (tokens_output / 1_000_000) * price["output"]
    return 0.0


def record_usage(
    model: str = "",
    provider: str = "",
    conversation_id: str = "",
    tokens_input: int = 0,
    tokens_output: int = 0,
    prompt_preview: str = "",
    duration_ms: int = 0,
):
    """记录一次请求的用量（同步，每 100 次插入自动清理 90 天前的旧数据）"""
    import uuid
    try:
        tokens_total = tokens_input + tokens_output
        cost = calc_cost(model, tokens_input, tokens_output)
        request_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().isoformat()
        db = _get_db()
        db.execute(
            "INSERT INTO usage_logs (request_id, timestamp, model, provider, conversation_id, tokens_input, tokens_output, tokens_total, cost, prompt_preview, duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, timestamp, model, provider, conversation_id, tokens_input, tokens_output, tokens_total, round(cost, 6), prompt_preview[:200], duration_ms)
        )
        db.commit()
        # 每 100 次插入清理一次 90 天前的旧数据
        record_usage._count = getattr(record_usage, '_count', 0) + 1
        if record_usage._count % 100 == 0:
            cutoff = (datetime.now() - timedelta(days=90)).isoformat()
            deleted = db.execute("DELETE FROM usage_logs WHERE timestamp < ?", (cutoff,)).rowcount
            if deleted:
                db.commit()
                db.execute("PRAGMA optimize")
        db.close()
    except Exception as e:
        print(f"[UsageTracker] 记录失败: {e}")


def query_usage(
    days: int = 7,
    model: str = "",
    conversation_id: str = "",
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """查询用量日志"""
    db = _get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    conditions = ["timestamp >= ?"]
    params = [since]
    if model:
        conditions.append("model = ?")
        params.append(model)
    if conversation_id:
        conditions.append("conversation_id = ?")
        params.append(conversation_id)
    where = " AND ".join(conditions)

    rows = db.execute(
        f"SELECT * FROM usage_logs WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()
    total_count = db.execute(
        f"SELECT COUNT(*) FROM usage_logs WHERE {where}", params
    ).fetchone()[0]

    summary = db.execute(
        f"SELECT COUNT(*) as count, SUM(tokens_input) as input, SUM(tokens_output) as output, SUM(tokens_total) as total_tk, SUM(cost) as total_cost FROM usage_logs WHERE {where}",
        params
    ).fetchone()

    db.close()
    return {
        "rows": [dict(r) for r in rows],
        "total": total_count,
        "summary": {
            "requests": summary["count"] or 0,
            "tokens_input": summary["input"] or 0,
            "tokens_output": summary["output"] or 0,
            "tokens_total": summary["total_tk"] or 0,
            "cost": round(summary["total_cost"] or 0, 6),
        }
    }


def get_usage_stats() -> dict:
    """获取用量统计概览（今日/本周/本月）"""
    db = _get_db()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")

    def _query(since):
        r = db.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(tokens_total),0) as tk, COALESCE(SUM(cost),0) as cost FROM usage_logs WHERE timestamp >= ?",
            (since,)
        ).fetchone()
        return {"requests": r["cnt"], "tokens": r["tk"], "cost": round(r["cost"], 6)}

    stats = {
        "today": _query(today),
        "week": _query(week_start),
        "month": _query(month_start),
    }
    db.close()
    return stats

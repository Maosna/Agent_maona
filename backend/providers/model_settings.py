"""模型参数设置持久化"""
import json
from pathlib import Path

SETTINGS_PATH = Path.home() / ".agent_maona" / "model_settings.json"

DEFAULTS = {
    "temperature": 0.7,
    "max_tokens": 4096,
    "top_p": 0.9,
    "thinking_enabled": False,
    "reasoning_effort": "high",
    "thinking_budget": 4096,
    "budget_cap": 500000,  # 单次对话 Token 预算上限
    # 向量检索配置
    "embedding_model": "text-embedding-3-small",  # OpenAI 兼容的 embedding 模型
    "embedding_url": "",  # 留空则用默认 Provider；填了则用独立 API
    "embedding_api_key": "",  # 独立 API key（留空用 Provider 的 key）
    "embedding_dim": 1536,  # 向量维度
    "use_embeddings": True,  # 是否用向量检索（关闭则回退 TF-IDF）
}


def _load() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except:
            pass
    return dict(DEFAULTS)


def _save(data: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_settings() -> dict:
    """获取全局模型设置"""
    return _load()


def update_settings(**kwargs) -> dict:
    """更新设置（含值域验证）"""
    current = _load()
    ALLOWED = set(DEFAULTS.keys())
    RANGES = {
        "temperature": (0.0, 2.0),
        "top_p": (0.0, 2.0),
        "max_tokens": (1, 1000000),
        "reasoning_effort": (None, None),  # 枚举，不验证数值
    }
    updates = {}
    for k, v in kwargs.items():
        if k not in ALLOWED:
            continue
        if k in RANGES and v is not None:
            lo, hi = RANGES[k]
            if lo is not None and hi is not None:
                try:
                    v = float(v) if k != "max_tokens" else int(v)
                    if not (lo <= v <= hi):
                        v = DEFAULTS[k]  # 超出范围用默认值
                except (ValueError, TypeError):
                    v = DEFAULTS[k]
        updates[k] = v
    current.update(updates)
    _save(current)
    return current

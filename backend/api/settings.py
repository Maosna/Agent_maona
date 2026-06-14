"""设置 API - Provider 管理"""
import time
from fastapi import APIRouter, Query
from models.schemas import ProviderConfig
from providers import store, manager
from providers.openai_provider import OpenAIProvider

# 模型列表缓存: {name: (timestamp, models)}
_model_cache: dict[str, tuple[float, list[str]]] = {}
CACHE_TTL = 300  # 5 分钟

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/providers")
async def list_providers():
    return {"providers": store.list_providers()}


@router.post("/providers")
async def add_provider(cfg: ProviderConfig):
    store.add_provider(cfg.name, cfg.api_url, cfg.api_key)
    manager.clear_cache()
    return {"status": "ok", "name": cfg.name}


@router.put("/providers/{name}")
async def update_provider(name: str, cfg: ProviderConfig):
    """更新 API 配置，Key 为空时保留原 Key"""
    old = store.get_provider(name)
    key = cfg.api_key if cfg.api_key else (old.get("api_key", "") if old else "")
    url = cfg.api_url or (old.get("api_url", "") if old else "")
    models = cfg.models if cfg.models else (old.get("models", []) if old else [])

    if old and cfg.name != name:
        store.remove_provider(name)
        store.add_provider(cfg.name, url, key, models)
    else:
        store.add_provider(cfg.name or name, url, key, models)
    manager.clear_cache()
    _model_cache.pop(name, None)
    return {"status": "ok"}


@router.delete("/providers/{name}")
async def remove_provider(name: str):
    store.remove_provider(name)
    manager.clear_cache()
    _model_cache.pop(name, None)
    return {"status": "ok"}


@router.post("/providers/{name}/fetch-models")
async def fetch_models(name: str, force: bool = Query(False)):
    """从 API URL 拉取可用模型列表（5 分钟缓存）"""
    cfg = store.get_provider(name)
    if not cfg:
        return {"error": "Provider 不存在"}, 404

    # 缓存命中
    if not force and name in _model_cache:
        ts, models = _model_cache[name]
        if time.time() - ts < CACHE_TTL:
            return {"name": name, "models": models, "cached": True}

    p = OpenAIProvider(name, cfg["api_url"], cfg["api_key"], "ping")
    models = await p.fetch_models()
    if models:
        store.update_models(name, models)
        _model_cache[name] = (time.time(), models)

    return {"name": name, "models": models, "cached": False}


@router.get("/providers/{name}/models")
async def get_models(name: str):
    """获取 Provider 的模型列表"""
    cfg = store.get_provider(name)
    if not cfg:
        return {"error": "Provider 不存在"}, 404
    return {"name": name, "models": cfg.get("models", [])}


@router.get("/providers/{name}/balance")
async def get_balance(name: str, model: str = "default"):
    """查询 Provider 余额（目前支持 DeepSeek）"""
    cfg = store.get_provider(name)
    if not cfg:
        return {"error": "Provider 不存在"}, 404
    if not cfg.get("api_key"):
        return {"error": "未配置 API Key"}
    from providers.openai_provider import OpenAIProvider
    p = OpenAIProvider(name, cfg["api_url"], cfg["api_key"], model)
    balance = await p.check_balance()
    return {"name": name, "balance": balance}

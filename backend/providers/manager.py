"""Provider 管理器 - 统一管理所有 API 实例"""
from typing import Optional
from .openai_provider import OpenAIProvider
from . import store


# 缓存已创建的 provider 实例: {(name, model): instance}
_instances: dict[str, OpenAIProvider] = {}


def get_provider(provider_name: str, model: str = None) -> OpenAIProvider:
    """获取或创建 Provider 实例"""
    # 获取配置
    cfg = store.get_provider(provider_name)
    if not cfg:
        raise ValueError(f"未找到 Provider: {provider_name}")

    model = model or (cfg.get("models", [None])[0] if cfg.get("models") else "default")
    cache_key = f"{provider_name}:{model}"

    if cache_key not in _instances:
        _instances[cache_key] = OpenAIProvider(
            name=provider_name,
            api_url=cfg["api_url"],
            api_key=cfg["api_key"],
            model=model,
        )
    return _instances[cache_key]


def clear_cache():
    """清除所有缓存（配置变更后调用）"""
    _instances.clear()


def list_available() -> list[dict]:
    """列出所有可用的 Provider 及其模型"""
    providers = store.list_providers()
    return [p for p in providers if p.get("models")]


def get_provider_config(name: str) -> Optional[dict]:
    """获取 Provider 配置（不含 Key）"""
    for p in store.list_providers():
        if p["name"] == name:
            return p
    return None

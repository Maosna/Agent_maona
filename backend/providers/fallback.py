"""Provider 降级管理器 - 多 LLM 故障转移"""
from typing import Optional
from .openai_provider import OpenAIProvider
from . import store


def get_fallback_chain(primary_name: str, model: str = None) -> list[tuple[str, OpenAIProvider]]:
    """获取降级链: [(name, provider), ...]
    
    优先级: primary → fallback1 → fallback2 → ...
    """
    chain = []
    
    # 主 provider
    try:
        cfg = store.get_provider(primary_name)
        if cfg:
            m = model or (cfg.get("models", [None])[0] if cfg.get("models") else "default")
            chain.append((primary_name, OpenAIProvider(
                name=primary_name,
                api_url=cfg["api_url"],
                api_key=cfg["api_key"],
                model=m,
            )))
    except Exception:
        pass
    
    # 备用 providers（从全局 prefs 读取）
    try:
        from memory.store import read_prefs
        prefs = read_prefs()
        fallback_names = prefs.get("fallback_providers", [])
        for fb_name in fallback_names:
            if fb_name == primary_name:
                continue
            try:
                fb_cfg = store.get_provider(fb_name)
                if fb_cfg and fb_cfg.get("api_key"):
                    m = fb_cfg.get("models", ["default"])[0]
                    chain.append((fb_name, OpenAIProvider(
                        name=fb_name,
                        api_url=fb_cfg["api_url"],
                        api_key=fb_cfg["api_key"],
                        model=m if m != "default" else None,
                    )))
            except Exception:
                continue
    except Exception:
        pass
    
    if not chain:
        raise ValueError(f"无可用 Provider（primary={primary_name}）")
    return chain

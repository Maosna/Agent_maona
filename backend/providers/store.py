"""Provider 配置持久化存储（API Key 加密存储）"""
import json
import base64
import hashlib
import os
import threading
from pathlib import Path
from typing import Optional

STORE_PATH = Path.home() / ".agent_maona" / "providers.json"
MASTER_KEY_PATH = Path.home() / ".agent_maona" / ".master_key"
_store_lock = threading.Lock()


def _derive_key() -> bytes:
    """派生加密密钥（使用持久化 master_key，避免主机名/用户名变化导致密钥失效）"""
    # 优先使用持久化的随机密钥
    if MASTER_KEY_PATH.exists():
        try:
            return base64.urlsafe_b64decode(MASTER_KEY_PATH.read_bytes())
        except Exception:
            pass
    # 生成新密钥并持久化
    key = os.urandom(32)
    MASTER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        MASTER_KEY_PATH.write_bytes(base64.urlsafe_b64encode(key))
    except Exception:
        pass
    return key


def _mask(plain: str) -> str:
    """简单加密 API Key"""
    if not plain:
        return ""
    key = _derive_key()
    data = plain.encode()
    masked = bytes(a ^ key[i % len(key)] for i, a in enumerate(data))
    return base64.urlsafe_b64encode(masked).decode()


def _unmask(encoded: str) -> str:
    """解密 API Key（支持新旧密钥过渡）"""
    if not encoded:
        return ""
    # 先尝试新 master_key
    try:
        key = _derive_key()
        data = base64.urlsafe_b64decode(encoded)
        result = bytes(a ^ key[i % len(key)] for i, a in enumerate(data)).decode()
        return result
    except Exception:
        pass
    # fallback: 尝试用旧的主机名密钥解密（兼容旧版本数据）
    try:
        import socket, getpass
        legacy_seed = f"{socket.gethostname()}:{getpass.getuser()}".encode()
        legacy_key = hashlib.sha256(legacy_seed).digest()
        data = base64.urlsafe_b64decode(encoded)
        result = bytes(a ^ legacy_key[i % len(legacy_key)] for i, a in enumerate(data)).decode()
        return result
    except Exception:
        return f"[DECRYPT_ERROR:{encoded[:20]}...]"  # 解密失败标记，API 调用时会明确报错


def _load() -> dict:
    with _store_lock:
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if STORE_PATH.exists():
            try:
                return json.loads(STORE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        return {"providers": {}}


def _save(data: dict) -> None:
    with _store_lock:
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STORE_PATH)


def list_providers() -> list[dict]:
    """列出所有 Provider（隐藏 Key）"""
    data = _load()
    result = []
    for name, cfg in data.get("providers", {}).items():
        p = dict(cfg)
        p["api_key"] = "***" if p.get("api_key") else ""
        result.append(p)
    return result


def get_provider(name: str) -> Optional[dict]:
    """获取单个 Provider（含解密 Key）"""
    data = _load()
    cfg = data.get("providers", {}).get(name)
    if cfg:
        cfg["api_key"] = _unmask(cfg.get("api_key", ""))
    return cfg


def add_provider(name: str, api_url: str, api_key: str, models: list[str] = None):
    """添加或更新 Provider（加密存储 Key）"""
    data = _load()
    if "providers" not in data:
        data["providers"] = {}
    data["providers"][name] = {
        "name": name,
        "api_url": api_url.rstrip("/") if api_url else "",
        "api_key": _mask(api_key),
        "models": models or [],
    }
    _save(data)


def remove_provider(name: str):
    """删除 Provider"""
    data = _load()
    data.get("providers", {}).pop(name, None)
    _save(data)


def update_models(name: str, models: list[str]):
    """更新 Provider 的模型列表"""
    data = _load()
    if name in data.get("providers", {}):
        data["providers"][name]["models"] = models
        _save(data)

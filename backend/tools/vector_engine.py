"""向量引擎 — embedding 模型调用 + 向量索引"""
import json
import math
import httpx
import asyncio
from pathlib import Path
from providers.model_settings import get_settings


async def _embed_texts(texts: list[str]) -> list[list[float]] | None:
    """调用 embedding API 获取向量，自动分批"""
    settings = get_settings()
    if not settings.get("use_embeddings"):
        return None

    model = settings.get("embedding_model", "text-embedding-3-small")
    url = settings.get("embedding_url")
    key = settings.get("embedding_api_key")

    # 没有指定独立 URL，尝试用默认 Provider
    if not url:
        from providers.store import get_provider
        p = get_provider("GLM") or get_provider("DeepSeek")
        if not p:
            return None
        url = p.get("api_url", "").rstrip("/") + "/embeddings"
        if not key:
            from providers.store import _unmask
            key = _unmask(p.get("api_key", ""))

    if not url or not key:
        return None

    # 截断长文本
    truncated = [t[:8000] for t in texts]
    all_vectors = []

    # 分批请求，每批 20 条
    batch_size = 20
    async with httpx.AsyncClient(timeout=120) as client:
        for i in range(0, len(truncated), batch_size):
            batch = truncated[i:i + batch_size]
            try:
                r = await client.post(
                    url,
                    json={"model": model, "input": batch},
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                all_vectors.extend([d["embedding"] for d in data["data"]])
            except Exception:
                return None

    return all_vectors if len(all_vectors) == len(texts) else None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return dot / (norm_a * norm_b)


async def embed_chunks(chunks: list[dict]) -> bool:
    """为 chunk 列表生成向量并写入 chunk['vector']"""
    texts = [c.get("embed_text") or c["text"] for c in chunks]
    vectors = await _embed_texts(texts)
    if not vectors:
        return False
    for c, v in zip(chunks, vectors):
        c["vector"] = v
    return True


def vector_search(query_vec: list[float], chunks: list[dict], top_k: int = 8) -> list[dict]:
    """向量相似度搜索"""
    # 预计算查询向量模长，避免循环中重复计算
    q_norm = math.sqrt(sum(x * x for x in query_vec))
    if q_norm < 1e-10:
        return []
    # 归一化查询向量，后续用内积替代余弦
    q_normed = [x / q_norm for x in query_vec]

    scores = []
    for c in chunks:
        v = c.get("vector")
        if not v or not isinstance(v, list):
            continue
        # 内积 = 余弦相似度（索引向量已归一化 或 近似）
        v_norm = math.sqrt(sum(x * x for x in v))
        if v_norm < 1e-10:
            continue
        sim = sum(qi * vi for qi, vi in zip(q_normed, v)) / v_norm
        if sim > 0.35:  # 提高阈值，过滤弱相关
            scores.append((sim, c))

    scores.sort(key=lambda x: x[0], reverse=True)
    results = []
    seen = set()
    for score, c in scores[:top_k * 2]:
        key = c["file"]
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "file": c["file"],
            "lines": c.get("lines", ""),
            "score": round(score, 3),
            "snippet": c["text"][:300]
        })
        if len(results) >= top_k:
            break
    return results

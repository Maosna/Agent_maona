"""知识库管理 — 文档索引 + 向量/RAG 联动"""
import json, re, shutil, math, asyncio, time
from pathlib import Path
from collections import Counter

KB_ROOT = Path.home() / ".agent_maona" / "knowledge"
KB_ROOT.mkdir(parents=True, exist_ok=True)
KB_UPLOAD_MAX_BYTES = 15 * 1024 * 1024  # 15MB，对齐 Dify 免费版

KB_DEFAULT_SETTINGS = {
    "description": "",
    "retrieval_method": "vector",
    "top_k": 3,
    "score_threshold": 0.3,
    "chunk_size": 1000,
    "chunk_overlap": 80,
    "auto_cite": True,
    "cite_format": "inline"
}

# ===== 内存索引缓存 =====
_index_cache = {}  # {kb_name: {"chunks": [...], "idf": {...}, "mtime": float, "mode": str}}
_CACHE_TTL = 30  # 缓存有效期 30 秒

def _load_index(kb_name: str) -> dict | None:
    """从缓存或磁盘加载索引"""
    now = time.time()
    cached = _index_cache.get(kb_name)
    if cached and (now - cached["mtime"]) < _CACHE_TTL:
        return cached

    chunks_file = KB_ROOT / kb_name / "idx" / "chunks.json"
    if not chunks_file.exists():
        return None

    try:
        chunks = json.loads(chunks_file.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None

    idf = {}
    idf_file = KB_ROOT / kb_name / "idx" / "idf.json"
    if idf_file.exists():
        try: idf = json.loads(idf_file.read_text(encoding='utf-8'))
        except: pass

    mode = "tfidf"
    idx_path = KB_ROOT / kb_name / "index.json"
    if idx_path.exists():
        try: mode = json.loads(idx_path.read_text(encoding='utf-8')).get("mode", "tfidf")
        except: pass

    entry = {"chunks": chunks, "idf": idf, "mtime": now, "mode": mode}
    _index_cache[kb_name] = entry
    return entry

def _clear_cache(kb_name: str = None):
    """清除索引缓存"""
    if kb_name:
        _index_cache.pop(kb_name, None)
    else:
        _index_cache.clear()

from tools.rag import _tokenize

def _parse_file(filepath: str) -> str:
    """解析文件文本内容，支持 PDF/DOCX/TXT/MD"""
    p = Path(filepath)
    suffix = p.suffix.lower()
    content = ""

    if suffix == ".pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(p))
            pages = []
            for page in reader.pages:
                t = page.extract_text()
                if t: pages.append(t)
            content = "\n\n".join(pages)
        except Exception as e:
            raise ValueError(f"PDF解析失败: {e}")

    elif suffix == ".docx":
        try:
            from docx import Document
            doc = Document(str(p))
            paras = [para.text for para in doc.paragraphs if para.text.strip()]
            content = "\n".join(paras)
        except Exception as e:
            raise ValueError(f"DOCX解析失败: {e}")

    elif suffix in (".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
                    ".html", ".css", ".json", ".yaml", ".yml", ".csv", ".xml",
                    ".sh", ".bat", ".ps1", ".java", ".c", ".cpp", ".h", ".rs",
                    ".go", ".rb", ".php", ".sql", ".r", ".m", ".swift"):
        try:
            content = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                content = p.read_text(encoding='gbk')
            except:
                try:
                    content = p.read_bytes().decode('utf-8', errors='replace')
                except:
                    raise ValueError("无法读取文件编码")

    else:
        raise ValueError(f"不支持的文件格式: {suffix}")

    if not content or not content.strip():
        return ""

    return content.strip()  # 不按字符数截断，上传时通过文件大小限制（15MB）

def list_kbs() -> list[dict]:
    """列出所有知识库"""
    result = []
    for d in sorted(KB_ROOT.iterdir()):
        if d.is_dir():
            idx = d / "index.json"
            meta = {"name": d.name, "docs": 0, "chunks": 0, "mode": "tfidf", "description": ""}
            if idx.exists():
                try:
                    m = json.loads(idx.read_text(encoding='utf-8'))
                    meta["docs"] = m.get("docs", 0)
                    meta["chunks"] = m.get("chunks", 0)
                    meta["mode"] = m.get("mode", "tfidf")
                    meta["description"] = (m.get("settings", {}) or {}).get("description", "")
                except: pass
            result.append(meta)
    return result

def create_kb(name: str) -> str:
    """创建知识库"""
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fff]', '_', name).strip('_')
    if not sanitized:
        return f"无效名称: {name}"
    path = KB_ROOT / sanitized
    if path.exists():
        return f"知识库 '{sanitized}' 已存在"
    path.mkdir()
    path.joinpath("index.json").write_text(json.dumps({
        "name": sanitized, "docs": 0, "chunks": 0,
        "mode": "tfidf",
        "settings": KB_DEFAULT_SETTINGS
    }, ensure_ascii=False, indent=2))
    return f"✅ 已创建知识库: {sanitized}"

def add_url(kb_name: str, url: str) -> str:
    """抓取 URL 内容加入知识库"""
    kb_path = KB_ROOT / kb_name
    if not kb_path.exists():
        return f"知识库 '{kb_name}' 不存在，请先 kb_create"
    
    try:
        import httpx, asyncio
        async def _fetch_url(u):
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
                r = await c.get(u)
                return r.text[:50000]
        try:
            loop = asyncio.get_running_loop()
            # 当前在事件循环中运行，创建新线程来跑 asyncio.run
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(lambda: asyncio.run(_fetch_url(url)))
                text = future.result(timeout=35)
        except RuntimeError:
            # 没有运行中的事件循环，直接使用 asyncio.run
            text = asyncio.run(_fetch_url(url))
    except Exception as e:
        return f"抓取 URL 失败: {e}"
    
    return _add_text(kb_name, url, text)

def add_text(kb_name: str, title: str, content: str) -> str:
    """添加文本到知识库"""
    kb_path = KB_ROOT / kb_name
    if not kb_path.exists():
        return f"知识库 '{kb_name}' 不存在"
    return _add_text(kb_name, title, content)

def _add_text(kb_name: str, title: str, text: str) -> str:
    kb_path = KB_ROOT / kb_name
    docs_dir = kb_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    # 去除已有扩展名避免双重后缀
    if '.' in safe_title:
        ext = safe_title.rsplit('.', 1)[-1].lower()
        if ext in ('txt', 'md', 'pdf', 'docx', 'doc', 'csv', 'py', 'js', 'ts', 'jsx', 'tsx', 'html', 'css', 'json', 'yaml', 'yml', 'xml'):
            safe_title = safe_title.rsplit('.', 1)[0]
    filepath = docs_dir / f"{safe_title}.txt"
    # 处理重名：添加数字后缀
    counter = 1
    while filepath.exists():
        safe_title_with_counter = f"{safe_title}_{counter}"
        filepath = docs_dir / f"{safe_title_with_counter}.txt"
        counter += 1
    filepath.write_text(text, encoding='utf-8')
    
    # 更新索引
    _build_index(kb_name)
    return f"✅ 已添加: {title}"

def _save_doc(kb_name: str, title: str, text: str):
    """仅保存文档，不重建索引（批量导入时使用）"""
    kb_path = KB_ROOT / kb_name
    docs_dir = kb_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    # 去除已有扩展名避免双重后缀
    if '.' in safe_title:
        ext = safe_title.rsplit('.', 1)[-1].lower()
        if ext in ('txt', 'md', 'pdf', 'docx', 'doc', 'csv', 'py', 'js', 'ts', 'jsx', 'tsx', 'html', 'css', 'json', 'yaml', 'yml', 'xml'):
            safe_title = safe_title.rsplit('.', 1)[0]
    filepath = docs_dir / f"{safe_title}.txt"
    # 处理重名：添加数字后缀
    counter = 1
    stem = filepath.stem
    while filepath.exists():
        filepath = docs_dir / f"{stem}_{counter}.txt"
        counter += 1
    filepath.write_text(text, encoding='utf-8')

# ===== 文档级元数据 =====
DOC_DEFAULT_META = {"auto_cite": True, "cite_format": "inline"}

def _get_doc_meta(kb_name: str, doc_name: str) -> dict:
    """获取文档元数据"""
    meta_path = KB_ROOT / kb_name / "docs" / (doc_name.rsplit(".", 1)[0] + ".meta.json")
    if meta_path.exists():
        try: return json.loads(meta_path.read_text(encoding='utf-8'))
        except: pass
    return dict(DOC_DEFAULT_META)

def _save_doc_meta(kb_name: str, doc_name: str, meta: dict):
    """保存文档元数据"""
    meta_path = KB_ROOT / kb_name / "docs" / (doc_name.rsplit(".", 1)[0] + ".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

def get_doc_chunks(kb_name: str, doc_name: str) -> list:
    """获取文档的所有索引块"""
    chunks_file = KB_ROOT / kb_name / "idx" / "chunks.json"
    if not chunks_file.exists():
        return []
    try:
        all_chunks = json.loads(chunks_file.read_text(encoding='utf-8'))
        return [c for c in all_chunks if c.get("file") == doc_name]
    except:
        return []

def _split_paragraph(para: str, chunk_size: int) -> list[str]:
    """将超长段落按次级分隔符切分，保持句子完整"""
    if len(para) <= chunk_size:
        return [para] if para.strip() else []

    # 尝试按行切
    lines = para.split('\n')
    chunks = []
    buf = ""
    for line in lines:
        candidate = buf + ('\n' if buf else '') + line
        if len(candidate) <= chunk_size:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            # 单行超长，按句号切
            if len(line) > chunk_size:
                sub = _split_by_sentences(line, chunk_size)
                chunks.extend(sub)
            else:
                buf = line
    if buf:
        chunks.append(buf)
    return chunks


def _split_by_sentences(text: str, chunk_size: int) -> list[str]:
    """按句末标点切分长文本"""
    parts = re.split(r'(?<=[。！？.!?；;])\s*', text)
    chunks = []
    buf = ""
    for p in parts:
        candidate = buf + p
        if len(candidate) <= chunk_size:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            if len(p) > chunk_size:
                # 还超长，强制按长度切
                for i in range(0, len(p), chunk_size):
                    chunks.append(p[i:i + chunk_size])
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 50, separator: str = "\n\n") -> (list, list):
    """Dify 风格分段：
    1. 预处理
    2. 按主分隔符切段落
    3. 段落 <= chunk_size → 直接作为 chunk
    4. 段落 > chunk_size → 按行/句切分
    5. 不合并，保留独立语义单元
    6. 重叠仅用于 embedding
    """
    # 1. 预处理
    text = re.sub(r' {3,}', '  ', text)
    text = re.sub(r'\t{2,}', '\t', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 2. 按主分隔符切段落
    paragraphs = text.split(separator)
    raw_chunks = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            raw_chunks.append(para)
        else:
            raw_chunks.extend(_split_paragraph(para, chunk_size))

    # 3. 重叠（仅用于 embedding 的副本）
    indexed = []
    for i, c in enumerate(raw_chunks):
        c = c.strip()
        if not c:
            continue
        if i > 0 and overlap > 0 and len(c) > overlap * 2:
            prev = indexed[i-1] if i-1 < len(indexed) else raw_chunks[i-1]
            prefix = prev[-overlap:] if len(prev) > overlap else ""
            indexed.append(prefix + c)
        else:
            indexed.append(c)

    return raw_chunks, indexed


def _build_index(kb_name: str):
    """重建知识库索引（优先向量，回退 TF-IDF）"""
    kb_path = KB_ROOT / kb_name
    docs_dir = kb_path / "docs"

    # 读取 KB 级 chunk 配置
    chunk_size = 1000
    chunk_overlap = 50
    idx_path = kb_path / "index.json"
    if idx_path.exists():
        try:
            s = json.loads(idx_path.read_text(encoding='utf-8')).get("settings", {})
            chunk_size = int(s.get("chunk_size", 1000))
            chunk_overlap = int(s.get("chunk_overlap", 50))
        except: pass

    chunks = []
    df = Counter()

    for fpath in sorted(docs_dir.glob("*.txt")):
        try:
            text = fpath.read_text(encoding='utf-8')
        except:
            continue

        texts, embed_texts = _chunk_text(text, chunk_size, chunk_overlap)
        for i, chunk_text in enumerate(texts):
            tokens = _tokenize(chunk_text)
            if len(tokens) < 2:
                continue
            chunks.append({
                'file': fpath.name,
                'lines': f'#{i+1}/{len(texts)}',
                'text': chunk_text[:3000],           # 存储原始文本（无重叠）
                'embed_text': embed_texts[i][:3000],  # 带重叠的用于 embedding
                'tokens': tokens,
                'vector': None
            })
            for t in set(tokens):
                df[t] += 1

    if not chunks:
        _clear_cache(kb_name)
        return 0

    # 尝试向量索引（跳过极短 chunk，TF-IDF 足够）
    vector_ok = False
    try:
        from tools.vector_engine import embed_chunks
        # 只对长度 >= 50 的 chunk 做 embedding
        embed_targets = [c for c in chunks if len(c.get("embed_text") or c["text"]) >= 50]
        if embed_targets:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                fut = asyncio.run_coroutine_threadsafe(embed_chunks(embed_targets), loop)
                vector_ok = fut.result(timeout=180)
            else:
                vector_ok = asyncio.run(embed_chunks(embed_targets))
    except:
        pass

    # 回退 TF-IDF：存为 JSON 对象而非字符串
    if not vector_ok:
        N = len(chunks)
        idf = {}
        for term, d in df.items():
            idf[term] = math.log((N + 1) / (d + 1)) + 1
        for c in chunks:
            tf = Counter(c['tokens'])
            vec = {t: tf[t] * idf.get(t, 0) for t in tf if t in idf}
            norm = math.sqrt(sum(v*v for v in vec.values())) or 1
            c['vector'] = f"tfidf:{json.dumps({k: v/norm for k, v in vec.items()})}"

    # 清理并保存
    for c in chunks:
        del c['tokens']
    idx_dir = kb_path / "idx"
    idx_dir.mkdir(exist_ok=True)
    idx_dir.joinpath("chunks.json").write_text(json.dumps(chunks, ensure_ascii=False))
    if not vector_ok:
        idx_dir.joinpath("idf.json").write_text(json.dumps(idf, ensure_ascii=False))

    # 更新 index.json（保留已有的 settings 字段）
    existing = {}
    idx_path = kb_path / "index.json"
    if idx_path.exists():
        try: existing = json.loads(idx_path.read_text(encoding='utf-8'))
        except: pass
    existing.update({
        "name": kb_name,
        "docs": len(list(docs_dir.glob("*.txt"))),
        "chunks": len(chunks),
        "mode": "vector" if vector_ok else "tfidf"
    })
    idx_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    _clear_cache(kb_name)

def search_kb(kb_name: str, query: str, top_k: int = 8) -> str:
    """搜索知识库（优先向量，回退 TF-IDF，带缓存加速）"""
    # 先尝试从缓存加载
    idx = _load_index(kb_name)
    if not idx:
        chunks_file = KB_ROOT / kb_name / "idx" / "chunks.json"
        if not chunks_file.exists():
            _build_index(kb_name)
            if not chunks_file.exists():
                return f"knowledge base '{kb_name}' is empty"
        idx = _load_index(kb_name)
        if not idx:
            return f"knowledge base '{kb_name}' is empty"

    chunks = idx["chunks"]
    mode = idx.get("mode", "tfidf")

    # 总是先尝试向量搜索，失败时自动回退 TF-IDF
    try:
        from tools.vector_engine import _embed_texts, vector_search
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            fut = asyncio.run_coroutine_threadsafe(_embed_texts([query]), loop)
            q_vecs = fut.result(timeout=15)
        else:
            q_vecs = asyncio.run(_embed_texts([query]))
        if q_vecs and q_vecs[0]:
            results = vector_search(q_vecs[0], chunks, top_k)
            if results:
                return _format_results(kb_name, query, results)
    except Exception:
        pass  # 向量搜索不可用时回退 TF-IDF

    # 回退 TF-IDF
    return _search_tfidf(kb_name, query, chunks, top_k, idx.get("idf", {}))

def _search_tfidf(kb_name: str, query: str, chunks: list, top_k: int, idf: dict = None) -> str:
    """TF-IDF 搜索回退"""
    if idf is None:
        idf_file = KB_ROOT / kb_name / "idx" / "idf.json"
        idf = json.loads(idf_file.read_text(encoding='utf-8')) if idf_file.exists() else {}

    q_tokens = _tokenize(query)
    # 中文单字权重降低，优先匹配词组
    q_vec = {}
    cn_single = re.compile(r'^[\u4e00-\u9fff]$')
    for t in q_tokens:
        if t in idf:
            w = idf[t] * (0.3 if cn_single.match(t) else 1.0)
            q_vec[t] = w
    norm = math.sqrt(sum(v*v for v in q_vec.values())) or 1
    q_vec = {k: v/norm for k, v in q_vec.items()}

    scores = []
    for c in chunks:
        vec = c.get('vector')
        # 解析向量：list = embedding, str = tfidf:json, dict = 旧格式
        if isinstance(vec, str) and vec.startswith("tfidf:"):
            try:
                vec = json.loads(vec.split(":", 1)[1])
            except:
                continue
        if isinstance(vec, list) and len(vec) > 0:
            continue  # embedding 向量，这里不走 TF-IDF
        if isinstance(vec, dict) and vec:
            dot = sum(q_vec.get(k, 0) * v for k, v in vec.items())
            scores.append((dot, c))

    scores.sort(key=lambda x: x[0], reverse=True)
    scores = [(s, c) for s, c in scores if s > 0.05][:top_k]

    if not scores:
        return f"no results for '{query}' in '{kb_name}'"

    results = []
    for score, c in scores:
        results.append({"file": c["file"], "lines": c.get("lines", ""), "score": round(score, 3), "snippet": c["text"][:200]})
    return _format_results(kb_name, query, results)

def _format_results(kb_name: str, query: str, results: list[dict]) -> str:
    lines = [f"search '{query}' in '{kb_name}':\n"]
    for r in results:
        fname = r['file']
        if fname.endswith('.txt'):
            fname = fname[:-4]
        lines.append(f"\n📄 {fname} [{r['score']}]")
        lines.append(f"  {r['snippet']}")
    return "\n".join(lines)

def delete_kb(name: str) -> str:
    """删除知识库"""
    path = KB_ROOT / name
    if not path.exists():
        return f"知识库 '{name}' 不存在"
    shutil.rmtree(path)
    return f"✅ 已删除知识库: {name}"

def list_kb_docs(name: str) -> str:
    """列出知识库中的文档"""
    docs_dir = KB_ROOT / name / "docs"
    if not docs_dir.exists():
        return f"知识库 '{name}' 为空"
    files = sorted(docs_dir.glob("*.txt"))
    return "\n".join(f"📄 {f.name}" for f in files)

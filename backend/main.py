"""Agent_maona 后端入口

启动命令: python main.py 或 uvicorn main:app --host 127.0.0.1 --port 8765
"""
import os
import sys
import json
import secrets
import webbrowser
from pathlib import Path

# === 修复沙箱/托管 Python 的 home 目录问题 ===
# 托管 Python 的 Path.home() 可能指向不存在的沙箱目录
# Windows 上 Path.home() 读 %USERPROFILE%，直接覆盖它最可靠
import getpass as _gp
_real_home = os.environ.get("USERPROFILE") or os.environ.get("LOCALAPPDATA") or f"C:/Users/{_gp.getuser()}"
try:
    test = Path.home() / ".maona_home_test"
    test.parent.mkdir(parents=True, exist_ok=True)
    test.write_text("ok")
    test.unlink()
except (OSError, PermissionError):
    os.environ["HOME"] = _real_home
    os.environ["USERPROFILE"] = _real_home
    print(f"[Maona] 沙箱 home 回退到: {_real_home}")

# 确保 backend 目录在 path 中
sys.path.insert(0, str(Path(__file__).parent))

# 生成启动令牌（防止本地其他应用调用 API）
# Session Token 持久化：优先从文件读取（保持后端重启后 Token 不变）
TOKEN_FILE = Path(__file__).parent / ".session_token"
if TOKEN_FILE.exists():
    SESSION_TOKEN = TOKEN_FILE.read_text().strip()
    if len(SESSION_TOKEN) < 16:  # 文件损坏时重新生成
        SESSION_TOKEN = secrets.token_hex(16)
        TOKEN_FILE.write_text(SESSION_TOKEN)
else:
    SESSION_TOKEN = secrets.token_hex(16)
    TOKEN_FILE.write_text(SESSION_TOKEN)
print(f"[Maona] Session token: {SESSION_TOKEN[:8]}...")

# ===== 全局未捕获异常日志 =====
from datetime import datetime
import logging
import threading

def _setup_crash_log():
    """将未捕获异常写入 crash 日志文件，方便排查 exit code=1 问题"""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    crash_log = log_dir / "crash.log"

    # Python 全局异常钩子（包括非 asyncio 线程中的异常）
    _orig_excepthook = sys.excepthook
    def _crash_excepthook(exc_type, exc_val, exc_tb):
        import traceback as _tb
        msg = f"[{datetime.now().isoformat()}] UNHANDLED EXCEPTION\n"
        msg += "".join(_tb.format_exception(exc_type, exc_val, exc_tb))
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        # 仍然打印到 stderr（uvicorn 会捕获）
        print(msg, file=sys.stderr, flush=True)
        _orig_excepthook(exc_type, exc_val, exc_tb)
    sys.excepthook = _crash_excepthook

    # 线程中未捕获异常 (Python 3.8+)
    if hasattr(threading, 'excepthook'):
        _orig_threadhook = threading.excepthook
        def _crash_threadhook(args):
            msg = f"[{datetime.now().isoformat()}] THREAD EXCEPTION\n"
            msg += f"  thread={args.thread.name}  exc={args.exc_type.__name__}: {args.exc_value}\n"
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
            print(msg, file=sys.stderr, flush=True)
            _orig_threadhook(args)
        threading.excepthook = _crash_threadhook

_setup_crash_log()

def _install_asyncio_handler():
    """在 lifespan 中安装 asyncio task 异常处理器（需要事件循环已启动）"""
    log_dir = Path(__file__).parent / "logs"
    crash_log = log_dir / "crash.log"
    def _asyncio_exception_handler(loop, context):
        msg_obj = context.get("message", str(context))
        exc = context.get("exception")
        msg = f"[{datetime.now().isoformat()}] ASYNCIO TASK EXCEPTION\n"
        msg += f"  message={msg_obj}\n"
        if exc:
            import traceback as _tb
            msg += "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        print(msg, file=sys.stderr, flush=True)
    try:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(_asyncio_exception_handler)
    except RuntimeError:
        pass  # 无事件循环时跳过

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse
from fastapi.responses import FileResponse
import tempfile
import shutil
import asyncio

from config import HOST, PORT
from api.chat import router as chat_router
from api.files import router as files_router
from api.memory import router as memory_router
from api.settings import router as settings_router
from api.tasks import router as tasks_router
from api.personas_api import router as personas_router

# 使用 lifespan 替代已弃用的 on_event
from contextlib import asynccontextmanager

async def _init_mcp_background():
    """后台初始化 MCP，不阻塞 FastAPI 启动"""
    try:
        from tools.mcp_client import ensure_mcp_connected
        await asyncio.sleep(1)  # 给 FastAPI 一点启动时间
        mcp_ok = await ensure_mcp_connected()
        print(f"[Maona] MCP: {'connected' if mcp_ok else 'unavailable'} (godot-mcp tools)")
    except Exception as e:
        print(f"[Maona] MCP init skipped: {e}")


@asynccontextmanager
async def lifespan(app):
    # 安装 asyncio 异常处理器
    _install_asyncio_handler()

    from memory.conversations import init_db
    await init_db()
    # 设置 Godot 插件根目录环境变量
    import os
    plugin_root = str(Path(__file__).resolve().parent.parent / "data" / "godot-mcp")
    os.environ["MAONA_PLUGIN_ROOT"] = plugin_root
    os.environ["GODOT_MCP_ROOT"] = plugin_root
    # 后台任务：清理旧任务、构建知识图谱（不阻塞启动）
    async def _bg_startup():
        try:
            from tasks.runner import cleanup_old_tasks
            cleanup_old_tasks()
        except Exception:
            pass
        try:
            from memory.graph import auto_build_from_memory
            auto_build_from_memory()
        except Exception:
            pass
    asyncio.create_task(_bg_startup())
    yield
    # ===== shutdown: 资源清理 =====
    print("[Maona] 正在清理资源...", file=sys.stderr, flush=True)
    # 1. 关闭所有缓存的 Provider httpx 客户端
    try:
        from providers.manager import _instances
        for key, p in list(_instances.items()):
            try:
                if hasattr(p, 'aclose'):
                    await p.aclose()
            except Exception:
                pass
        _instances.clear()
    except Exception:
        pass
    # 2. 关闭 MCP 子进程
    try:
        from tools.mcp_client import _mcp_process
        if _mcp_process and _mcp_process.returncode is None:
            _mcp_process.terminate()
            try:
                _mcp_process.wait(timeout=3)
            except Exception:
                _mcp_process.kill()
    except Exception:
        pass
    print("[Maona] 资源清理完成", file=sys.stderr, flush=True)


app = FastAPI(
    title="Agent Maona",
    description="精简自用 Agent 桌面办公助手",
    version="0.1.0",
    lifespan=lifespan,
)

# 在 lifespan 启动时执行，而非模块 import 时
def _cleanup_tasks_on_startup():
    try:
        from tasks.runner import cleanup_old_tasks
        cleanup_old_tasks()
    except Exception:
        pass  # 静默失败，不影响主流程

# CORS - 允许 Electron 渲染进程访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8765", "http://127.0.0.1:8765", "file://"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session token 中间件 + CSP + Origin 检查
from starlette.requests import Request as StarletteRequest
@app.middleware("http")
async def security_middleware(request: StarletteRequest, call_next):
    response = await call_next(request)
    # CSP header
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http://127.0.0.1:8765"
    # Session token check for API routes
    path = request.url.path
    if path == "/api/health" or path == "/api/token" or path == "/api/diagnostics" or path.startswith("/api/conversations/dump") or path.startswith("/api/usage/") or not path.startswith("/api/") or path.startswith("/assets") or path.startswith("/css") or path.startswith("/js"):
        return response
    token = request.headers.get("x-session-token", "")
    if token != SESSION_TOKEN:
        return JSONResponse(status_code=403, content={"error": "invalid session token"})
    return response

# ===== 模型设置 API（必须在 router include 之前注册） =====
from providers.model_settings import get_settings, update_settings

@app.get("/api/model-settings")
async def get_model_settings():
    return get_settings()

@app.post("/api/model-settings")
async def save_model_settings(data: dict):
    return update_settings(**data)

# ===== 知识库 API =====
from tools.knowledge import list_kbs, create_kb, add_text, add_url, delete_kb, search_kb as _search_kb, list_kb_docs, KB_ROOT

@app.get("/api/knowledge/list")
async def kb_list():
    return list_kbs()

@app.post("/api/knowledge/create")
async def kb_create(data: dict):
    return {"status": create_kb(data.get("name", ""))}

@app.post("/api/knowledge/add")
async def kb_add(data: dict):
    return {"status": add_text(data.get("kb", ""), data.get("title", ""), data.get("content", ""))}

@app.post("/api/knowledge/add-url")
async def kb_add_url(data: dict):
    return {"status": add_url(data.get("kb", ""), data.get("url", ""))}

@app.get("/api/knowledge/search")
async def kb_search(kb: str, q: str):
    result = _search_kb(kb, q)
    # parse result into structured format
    lines = result.split("\n")
    results = []
    current = {}
    for line in lines:
        if line.startswith("📄 "):
            if current: results.append(current)
            current = {"file": line[3:].split(" [")[0], "score": line.split("[")[-1].rstrip("]") if "[" in line else ""}
        elif line.strip().startswith("📄") == False and current:
            current["text"] = (current.get("text","") + " " + line.strip()).strip()
    if current: results.append(current)
    return {"results": results, "raw": result}

@app.delete("/api/knowledge/{name}")
async def kb_delete(name: str):
    return {"status": delete_kb(name)}

@app.get("/api/knowledge/{name}/docs")
async def kb_docs(name: str):
    """列出知识库中的所有文档"""
    kb_path = KB_ROOT / name / "docs"
    if not kb_path.exists():
        return []
    docs = []
    for f in sorted(kb_path.glob("*.txt")):
        docs.append({"name": f.name, "size": f.stat().st_size, "updated": f.stat().st_mtime})
    return docs

@app.get("/api/knowledge/{name}/doc/{doc_name}")
async def kb_get_doc(name: str, doc_name: str):
    """获取文档内容"""
    doc_path = KB_ROOT / name / "docs" / doc_name
    if not doc_path.exists():
        return {"error": "文档不存在"}
    return {"name": doc_name, "content": doc_path.read_text(encoding='utf-8')}

@app.delete("/api/knowledge/{name}/doc/{doc_name}")
async def kb_delete_doc(name: str, doc_name: str):
    """删除文档"""
    doc_path = KB_ROOT / name / "docs" / doc_name
    if not doc_path.exists():
        return {"error": "文档不存在"}
    doc_path.unlink()
    from tools.knowledge import _build_index
    _build_index(name)
    return {"status": "ok"}

@app.get("/api/knowledge/{name}/doc/{doc_name}/detail")
async def kb_doc_detail(name: str, doc_name: str):
    """文档详情：内容 + 所有分段 + 元数据"""
    from tools.knowledge import _get_doc_meta, get_doc_chunks
    doc_path = KB_ROOT / name / "docs" / doc_name
    if not doc_path.exists():
        return {"error": "文档不存在"}
    content = doc_path.read_text(encoding='utf-8')
    chunks = get_doc_chunks(name, doc_name)
    meta = _get_doc_meta(name, doc_name)
    return {
        "name": doc_name,
        "size": doc_path.stat().st_size,
        "content": content[:5000],
        "total_chunks": len(chunks),
        "chunks": chunks[:50],
        "meta": meta
    }

@app.get("/api/knowledge/{name}/doc/{doc_name}/settings")
async def kb_doc_settings(name: str, doc_name: str):
    """获取文档级设置"""
    from tools.knowledge import _get_doc_meta
    return _get_doc_meta(name, doc_name)

@app.put("/api/knowledge/{name}/doc/{doc_name}/settings")
async def kb_doc_update_settings(name: str, doc_name: str, data: dict):
    """更新文档级设置（引用控制等）"""
    from tools.knowledge import _get_doc_meta, _save_doc_meta
    meta = _get_doc_meta(name, doc_name)
    for k in ("auto_cite", "cite_format"):
        if k in data:
            meta[k] = data[k]
    _save_doc_meta(name, doc_name, meta)
    return {"status": "ok", "meta": meta}

@app.put("/api/knowledge/{name}/rename")
async def kb_rename(name: str, data: dict):
    """重命名知识库"""
    new_name = data.get("name", "")
    if not new_name:
        return {"error": "缺少名称"}
    import shutil
    src = KB_ROOT / name
    dst = KB_ROOT / new_name
    if dst.exists():
        return {"error": "名称已存在"}
    shutil.move(str(src), str(dst))
    return {"status": "ok"}

# ===== 知识库文件上传 =====
UPLOAD_DIR = Path(tempfile.gettempdir()) / "maona_kb_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/api/knowledge/upload")
async def kb_upload_files(files: list[UploadFile] = File(...)):
    """上传文件到临时目录，返回文件信息列表"""
    from tools.knowledge import KB_UPLOAD_MAX_BYTES
    uploaded = []
    for f in files:
        content = await f.read()
        if len(content) > KB_UPLOAD_MAX_BYTES:
            return {"error": f"文件 {f.filename} 超过大小限制（最大 15MB）"}
        safe_name = Path(f.filename).name
        dest = UPLOAD_DIR / f"{Path(f.filename).stem}_{secrets.token_hex(4)}{Path(f.filename).suffix}"
        dest.write_bytes(content)
        uploaded.append({
            "temp_path": str(dest),
            "name": safe_name,
            "size": len(content),
            "type": Path(f.filename).suffix.lower()
        })
    return {"files": uploaded}

@app.post("/api/knowledge/process-files")
async def kb_process_files(data: dict):
    """解析上传的文件并加入知识库，最后统一重建索引"""
    kb_name = data.get("kb", "")
    files = data.get("files", [])
    chunk_size = data.get("chunk_size", 1000)

    if not kb_name:
        return {"error": "缺少知识库名称"}

    from tools.knowledge import _parse_file, _save_doc, _build_index, KB_ROOT

    kb_path = KB_ROOT / kb_name
    if not kb_path.exists():
        return {"error": f"知识库 '{kb_name}' 不存在"}

    docs_dir = kb_path / "docs"
    docs_dir.mkdir(exist_ok=True)

    results = []
    for f in files:
        temp_path = f.get("temp_path", "")
        name = f.get("name", "unknown")
        try:
            text = _parse_file(temp_path)
            if text:
                _save_doc(kb_name, name, text)
                results.append({"name": name, "status": "ok", "chars": len(text)})
            else:
                results.append({"name": name, "status": "empty"})
        except Exception as e:
            results.append({"name": name, "status": f"error: {str(e)}"})

    # 统一重建索引
    if any(r["status"] == "ok" for r in results):
        try:
            _build_index(kb_name)
        except:
            pass

    # 清理临时文件
    for f in files:
        p = Path(f.get("temp_path", ""))
        if p.exists():
            try: p.unlink()
            except: pass

    return {"results": results, "total": len(results)}

@app.get("/api/knowledge/{name}/settings")
async def kb_get_settings(name: str):
    """获取知识库完整设置"""
    from tools.knowledge import KB_DEFAULT_SETTINGS
    kb_path = KB_ROOT / name
    if not kb_path.exists():
        return {"error": "知识库不存在"}
    idx_path = kb_path / "index.json"
    settings = dict(KB_DEFAULT_SETTINGS)
    base = {"name": name, "docs": 0, "chunks": 0, "mode": "tfidf"}
    if idx_path.exists():
        try:
            m = json.loads(idx_path.read_text(encoding='utf-8'))
            base["docs"] = m.get("docs", 0)
            base["chunks"] = m.get("chunks", 0)
            base["mode"] = m.get("mode", "tfidf")
            stored = m.get("settings", {})
            settings.update(stored)
        except: pass
    settings.update(base)
    return settings

@app.put("/api/knowledge/{name}/settings")
async def kb_update_settings(name: str, data: dict):
    """更新知识库设置（检索参数、引用控制）"""
    kb_path = KB_ROOT / name
    if not kb_path.exists():
        return {"error": "知识库不存在"}
    idx_path = kb_path / "index.json"
    current = {"name": name, "docs": 0, "chunks": 0, "mode": "tfidf"}
    if idx_path.exists():
        try: current.update(json.loads(idx_path.read_text(encoding='utf-8')))
        except: pass

    allowed = {"description", "retrieval_method", "top_k", "score_threshold",
               "chunk_size", "chunk_overlap", "auto_cite", "cite_format"}
    current.setdefault("settings", {})
    for k in allowed:
        if k in data:
            current["settings"][k] = data[k]
    current["settings"]["top_k"] = int(current["settings"].get("top_k", 3))
    current["settings"]["score_threshold"] = float(current["settings"].get("score_threshold", 0.5))

    idx_path.write_text(json.dumps(current, ensure_ascii=False, indent=2))
    return {"status": "ok", "settings": current["settings"]}

@app.post("/api/knowledge/{name}/reindex")
async def kb_reindex(name: str):
    """强制重建知识库索引（不重新上传文件）"""
    from tools.knowledge import _build_index
    kb_path = KB_ROOT / name
    if not kb_path.exists():
        return {"error": "知识库不存在"}
    cnt = _build_index(name)
    return {"status": "ok", "chunks": cnt}

@app.get("/api/knowledge/{name}/test-search")
async def kb_test_search(name: str, q: str = ""):
    """检索测试 — 返回带分数的文档块"""
    if not q.strip():
        return {"results": []}
    from tools.knowledge import search_kb as _search_kb
    raw = _search_kb(name, q)
    lines = raw.split("\n")
    results = []
    cur = {}
    for line in lines:
        if line.startswith("\U0001f4c4 "):
            if cur and cur.get("text"):
                results.append(cur)
            parts = line[3:].split(" [")
            cur = {"file": parts[0], "score": parts[1].rstrip("]") if len(parts) > 1 else "", "text": ""}
        elif cur:
            cur["text"] = (cur.get("text", "") + " " + line.strip()).strip()
    if cur and cur.get("text"):
        results.append(cur)
    return {"results": results, "query": q}

@app.get("/api/knowledge/upload-preview")
async def kb_upload_preview(path: str):
    """预览上传的临时文件内容（前 2000 字符）"""
    p = Path(path)
    if not p.exists():
        return {"error": "文件不存在"}
    try:
        from tools.knowledge import _parse_file
        text = _parse_file(str(p))
        return {"name": p.name, "content": text[:2000] if text else "", "size": p.stat().st_size}
    except Exception as e:
        return {"error": str(e)}

# 注册路由（必须在静态文件挂载之前）
app.include_router(chat_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(personas_router, prefix="/api")

# 前端静态文件
# 打包模式：Electron 通过 MAONA_RESOURCES_DIR 环境变量传入 resources 目录路径
# 开发模式：renderer/ 在 backend/ 的父级目录
_RESOURCES = os.environ.get("MAONA_RESOURCES_DIR")
if _RESOURCES:
    STATIC_DIR = Path(_RESOURCES) / "renderer"
else:
    STATIC_DIR = Path(__file__).parent.parent / "renderer"

# 挂载 CSS / JS 等资源（禁用缓存，开发模式下每次刷新都拿最新文件）
if STATIC_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

@app.middleware("http")
async def no_cache_static(request: StarletteRequest, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/js/") or path.startswith("/css/") or path == "/index.html":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/")
@app.get("/index.html")
async def serve_index():
    """服务前端入口页面"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "index.html not found"}


@app.get("/api/token")
async def get_token():
    return {"token": SESSION_TOKEN}


@app.get("/api/health")
async def health():
    """增强健康检查：验证 Provider 和数据库可用"""
    import shutil
    mcp_ok = False
    try:
        venv = Path.home() / ".agent_maona" / "venv"
        exe = venv / "Scripts" / "node.exe" if os.name == "nt" else venv / "bin" / "node"
        mcp_ok = shutil.which("node") is not None or exe.exists()
    except: pass
    import sys as _sys
    return {
        "status": "ok",
        "version": "0.8.0",
        "mcp_available": mcp_ok,
        "python": _sys.version,
    }


@app.get("/api/diagnostics")
async def diagnostics():
    """返回诊断信息：MCP状态、Node可用性、缓存状态等"""
    import shutil
    info = {
        "mcp_available": False,
        "mcp_tool_count": 0,
        "mcp_tool_names": [],
        "node_path": shutil.which("node") or "NOT FOUND",
        "node_version": "",
        "prompt_cache_size": 0,
        "active_sessions": 0,
    }
    # MCP 状态
    try:
        from tools.mcp_client import _mcp_ready, _mcp_tools, _mcp_process, _mcp_error_log
        info["mcp_available"] = _mcp_ready
        info["mcp_tool_count"] = len(_mcp_tools)
        info["mcp_tool_names"] = [t.get("name", "?") for t in _mcp_tools[:10]]
        if _mcp_process:
            info["mcp_process_alive"] = _mcp_process.returncode is None
            info["mcp_process_exitcode"] = _mcp_process.returncode
        info["mcp_error_log"] = _mcp_error_log[-300:] if _mcp_error_log else ""
    except Exception as e:
        info["mcp_error"] = str(e)[:200]
    # Node 版本
    if info["node_path"] != "NOT FOUND":
        try:
            import subprocess
            result = subprocess.run([info["node_path"], "--version"], capture_output=True, text=True, timeout=5)
            info["node_version"] = result.stdout.strip()
        except Exception:
            pass
    # 缓存状态
    try:
        from api.chat import _conv_prompt_cache, _agent_sessions, _runtime_diag
        info["prompt_cache_size"] = len(_conv_prompt_cache)
        info["active_sessions"] = len(_agent_sessions)
        # 运行时诊断
        info["runtime"] = {
            "total_rounds": _runtime_diag.get("total_rounds", 0),
            "total_tool_calls": _runtime_diag.get("total_tool_calls", 0),
            "auto_snapshots": _runtime_diag.get("auto_snapshots", 0),
            "auto_continues": _runtime_diag.get("auto_continues", 0),
            "provider_events": _runtime_diag.get("provider_events", [])[-10:],
            "phase_events": _runtime_diag.get("phase_events", []),
            "compressions": _runtime_diag.get("compressions", [])[-5:],
            "quality_gates": _runtime_diag.get("quality_gates", [])[-10:],
            "code_analysis": _runtime_diag.get("code_analysis", [])[-10:],
            "injections": _runtime_diag.get("injections", []),
            "errors": _runtime_diag.get("errors", [])[-10:],
            "last_error": _runtime_diag.get("last_error"),
            "model_settings": _runtime_diag.get("model_settings", {}),
            "round_timeline": _runtime_diag.get("round_timeline", [])[-30:],
        }
    except Exception:
        pass
    return info


@app.get("/api/usage/logs")
async def usage_logs(days: int = 7, model: str = "", conversation_id: str = "", limit: int = 200, offset: int = 0):
    """查询用量日志"""
    from usage_tracker import query_usage
    return query_usage(days=days, model=model, conversation_id=conversation_id, limit=limit, offset=offset)


@app.get("/api/usage/stats")
async def usage_stats():
    """用量统计概览"""
    from usage_tracker import get_usage_stats
    return get_usage_stats()


@app.get("/api/usage/export")
async def usage_export(days: int = 30, model: str = ""):
    """导出用量 CSV"""
    import csv, io
    from usage_tracker import query_usage
    data = query_usage(days=days, model=model, limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "模型", "输入Token", "输出Token", "总Token", "成本(USD)", "对话ID"])
    for r in data["rows"]:
        writer.writerow([r["timestamp"], r["model"], r["tokens_input"], r["tokens_output"], r["tokens_total"], r["cost"], r["conversation_id"]])
    from starlette.responses import Response
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=maona_usage_{days}d.csv"})


@app.get("/api/conversations/dump")
async def dump_all_conversations(conv_id: str = None):
    """导出所有对话数据（含完整消息历史、tool_calls、reasoning）用于调试"""
    try:
        from memory.conversations import _get_db
        db = _get_db()
        result = {"conversations": []}
        if conv_id:
            rows = db.execute(
                "SELECT c.id, c.title, c.project_id, c.created_at, c.updated_at, "
                "m.id as msg_id, m.role, m.content, m.reasoning_content, m.tool_calls, m.created_at as msg_time "
                "FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                "WHERE c.id = ? ORDER BY m.created_at", (conv_id,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT c.id, c.title, c.project_id, c.created_at, c.updated_at, "
                "m.id as msg_id, m.role, m.content, m.reasoning_content, m.tool_calls, m.created_at as msg_time "
                "FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                "ORDER BY c.updated_at DESC LIMIT 500"
            ).fetchall()
        # 按对话分组
        convs = {}
        for r in rows:
            cid = r["id"]
            if cid not in convs:
                convs[cid] = {
                    "id": cid, "title": r["title"], "project_id": r["project_id"],
                    "created_at": r["created_at"], "updated_at": r["updated_at"],
                    "messages": []
                }
            if r["msg_id"]:
                msg = {"msg_id": r["msg_id"], "role": r["role"], "content": (r["content"] or "")[:5000],
                       "created_at": r["msg_time"]}
                if r["reasoning_content"]:
                    msg["reasoning"] = r["reasoning_content"][:3000]
                if r["tool_calls"]:
                    try:
                        msg["tool_calls"] = json.loads(r["tool_calls"]) if isinstance(r["tool_calls"], str) else r["tool_calls"]
                    except:
                        msg["tool_calls"] = r["tool_calls"][:1000]
                convs[cid]["messages"].append(msg)
        result["conversations"] = list(convs.values())
        result["total_conversations"] = len(convs)
        # 注入运行时诊断
        from api.chat import _runtime_diag
        result["runtime"] = {
            "total_rounds": _runtime_diag.get("total_rounds", 0),
            "phase_events": _runtime_diag.get("phase_events", []),
            "quality_gates": _runtime_diag.get("quality_gates", [])[-10:],
            "compressions": _runtime_diag.get("compressions", [])[-5:],
        }
        return result
    except Exception as e:
        return {"error": str(e)[:500], "conversations": []}


if __name__ == "__main__":
    import uvicorn
    import traceback

    # 首次启动预置 Provider 模板
    try:
        from config import seed_default_providers
        seed_default_providers()
    except Exception as _e:
        print(f"[Maona] 预置 Provider 失败: {_e}", file=sys.stderr)

    print(f"\n  Agent Maona 启动中...")
    print(f"  后端: http://{HOST}:{PORT}")
    print(f"  前端: http://{HOST}:{PORT}/index.html")
    print(f"  API 文档: http://{HOST}:{PORT}/docs\n")

    if "--no-browser" not in sys.argv:
        webbrowser.open(f"http://{HOST}:{PORT}")

    import time as _time, subprocess as _sp

    for _attempt in range(10):
        try:
            uvicorn.run(app, host=HOST, port=PORT, log_level="info")
            break
        except Exception as _e:
            if "10048" in str(_e) and _attempt < 9:
                # 端口被占用，快速清理后重试
                try:
                    _sp.run(
                        'powershell -Command "Get-NetTCPConnection -LocalPort {0} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"'.format(PORT),
                        shell=True, timeout=3
                    )
                except: pass
                print(f"[Maona] 端口被占用，已清理，1秒后重试... ({_attempt+1}/10)")
                _time.sleep(1)
            else:
                print(f"[Maona] 致命错误:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                sys.exit(1)

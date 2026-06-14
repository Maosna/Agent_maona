"""工具调度器 - 根据名称分发执行（带文件读取缓存）"""
import json, os, uuid, time
from pathlib import Path
from .file_ops import read_file, write_file, list_files, search_content, edit_file, git_diff, git_log, rename_file, delete_file, read_docx, read_xlsx, read_pptx, pdf_read, sql_query, api_post
from .shell import run_command, web_search, web_fetch, download_file, run_python, system_info, read_csv, image_info, install_pip, compress_image, text_to_speech, screenshot, open_browser, clipboard, zip_archive, notify, encode_decode, count_tokens, cost_summary
from .browser import browser_navigate, browser_screenshot, browser_click, browser_fill, browser_extract, browser_wait, browser_close
from .lsp import lsp_diagnose, lsp_references, lsp_hover, lsp_outline, lsp_format
from .deploy import deploy_preview, deploy_package
from .godot_ops import godot_setup, check_godot_project, validate_project
from .gdscript_lint import validate_gdscript
from .creative import image_generate, schedule_task, list_scheduled_tasks, cancel_scheduled_task, skill_auto_save
from .comfy_cli import comfy_cli, comfy_node_scaffold, comfy_node_install, comfy_node_publish, comfy_launch, comfy_model_download
from .memory_tools import save_memory, read_memory, save_daily_log, save_bug_fix
from skills import get_skill_body
from skills import scan_skills as _scan_skills, get_market_skills as _get_market_skills, install_skill as _install_skill
from memory.conversations import search_conversation_messages

# 智能记忆工具
from memory.procedural import record_workflow, suggest_workflow, get_system_prompt_hint
from memory.graph import search_related as _search_graph, add_node, add_edge
from memory.planner import decompose_task as _decompose_task, TaskPlan, backtrack_prompt
from memory.checkpoint import create_checkpoint as _create_checkpoint, list_checkpoints as _list_checkpoints

import json

# 并发安全锁
import asyncio
_state_lock = asyncio.Lock()

# 当前会话模式（由 switch_mode 工具修改）
_current_mode: str = "craft"
# 当前会话 ID（由 chat.py 设置）
_current_conv_id: str = "default"
# 当前任务状态
_current_tasks: dict = {}
TASK_DIR = Path.home() / ".agent_maona" / "tasks"
TASK_DIR.mkdir(parents=True, exist_ok=True)

def set_mode(mode: str):
    global _current_mode
    _current_mode = mode

def set_conv_id(conv_id: str):
    global _current_conv_id
    _current_conv_id = conv_id


# 环境缓存回调（由 api/chat.py 注入，避免循环导入）
_env_cache_callback = None

def set_env_cache_callback(cb):
    global _env_cache_callback
    _env_cache_callback = cb


async def _cache_env_handler(**kw) -> str:
    """缓存环境探测结果"""
    global _env_cache_callback, _current_conv_id
    if not _env_cache_callback:
        return "⚠️ 环境缓存未初始化"
    conv_id = _current_conv_id
    updates = {k: v for k, v in kw.items() if v is not None and k != "_workspace"}
    if updates:
        await _env_cache_callback(conv_id, updates)
        return f"✅ 已缓存环境状态: {', '.join(f'{k}={v}' for k, v in updates.items())}"
    return "⚠️ 没有可缓存的环境信息"


def get_mode() -> str:
    return _current_mode


# ===== 任务管理 =====
def _load_tasks(conv_id: str) -> dict:
    global _current_tasks
    if conv_id in _current_tasks:
        return _current_tasks[conv_id]
    path = TASK_DIR / f"{conv_id}.json"
    if path.exists():
        try:
            _current_tasks[conv_id] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _current_tasks[conv_id] = []
    else:
        _current_tasks[conv_id] = []
    return _current_tasks[conv_id]

def _save_tasks(conv_id: str):
    path = TASK_DIR / f"{conv_id}.json"
    path.write_text(json.dumps(_current_tasks.get(conv_id, []), ensure_ascii=False, indent=2))

def _task_create(subject="", description="", steps=None, **kw):
    tid = str(uuid.uuid4())[:8]
    tasks = _load_tasks(_current_conv_id)
    tasks.append({
        "id": tid, "subject": subject, "description": description,
        "steps": steps or [], "current_step": 0,
        "status": "pending", "created": time.strftime("%H:%M:%S"),
        "notes": []
    })
    if len(tasks) == 1:
        tasks[-1]["status"] = "in_progress"
    _save_tasks(_current_conv_id)
    return f"已创建任务 [{tid}]：{subject}\n步骤：{' → '.join(steps) if steps else '(无)'}\n状态：进行中"

def _task_update(task_id="", status="in_progress", step=0, note="", **kw):
    tasks = _load_tasks(_current_conv_id)
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = status
            if step is not None:
                t["current_step"] = step
            if note:
                t["notes"].append(f"[{time.strftime('%H:%M:%S')}] {note}")
            _save_tasks(_current_conv_id)
            total = len(t["steps"])
            done = t["current_step"]
            bar = "█" * done + "░" * (total - done) if total else ""
            return f"任务 [{task_id}] → {status} | 进度: {done}/{total} | {bar}\n{note}"
    return f"任务 {task_id} 未找到"

def _task_list(**kw):
    tasks = _load_tasks(_current_conv_id)
    if not tasks:
        return "暂无任务"
    lines = []
    for t in tasks:
        icon = {"pending": "○", "in_progress": "●", "completed": "✓", "failed": "✗"}.get(t["status"], "?")
        total = len(t["steps"])
        done = t.get("current_step", 0)
        bar = f" [{done}/{total}]" if total else ""
        lines.append(f"{icon} [{t['id']}] {t['subject']}{bar} — {t['status']}")
    return "\n".join(lines)

# ===== 备份恢复 =====
def _restore_backup(path="", list_only=False, **kw):
    p = Path(path).expanduser().resolve()
    backup_dir = p.parent / ".maona" / "backups"
    if not backup_dir.exists():
        return "该文件无可用备份"

    backups = sorted(backup_dir.glob(f"{p.name}.*.bak"), reverse=True)
    if not backups:
        return "该文件无可用备份"

    if list_only:
        lines = [f"可用备份 ({len(backups)} 个):"]
        for b in backups[:10]:
            ts = b.suffixes[-2].lstrip(".") if len(b.suffixes) >= 2 else "?"
            lines.append(f"  {b.name} ({ts})")
        return "\n".join(lines)

    # 恢复最新备份
    latest = backups[0]
    p.write_bytes(latest.read_bytes())
    return f"已恢复 {p.name} 从备份 {latest.name}"

def _switch_mode_inner(mode: str, reason: str) -> str:
    if mode not in ("craft", "plan", "ask"):
        return f"错误：无效模式 {mode}，支持 craft/plan/ask"
    set_mode(mode)
    labels = {"craft": "动手", "plan": "规划", "ask": "问答"}
    return f"已切换为{labels[mode]}模式：{reason}" if reason else f"已切换为{labels[mode]}模式"

async def _async_load(skill_id: str) -> str:
    return get_skill_body(skill_id)


async def _search_conversations(query="", limit=10, **kw):
    """搜索历史对话消息"""
    if not query:
        return "请提供搜索关键词 (query)"
    from api.chat import _get_current_project
    project_id = _get_current_project() or "default"
    results = await search_conversation_messages(project_id, query, min(limit, 20))
    if not results:
        return f"未找到与「{query}」相关的历史对话。"
    lines = [f"## 历史对话搜索结果（{len(results)} 条，关键词：{query}）"]
    for r in results:
        lines.append(f"\n📁 [{r.get('title', '?')}] ({r.get('role', '?')}): {r.get('preview', '')}")
    return "\n".join(lines)


# ===== Git 快照 =====
def _git_snapshot(message="", path="", **kw):
    import subprocess
    ws = path
    if not ws or not Path(ws).exists():
        return "git_snapshot: 未指定有效工作目录"
    # 前置检查：目标目录是否已初始化 Git 仓库
    git_dir = Path(ws) / ".git"
    if not git_dir.exists():
        return f"git_snapshot 跳过: {ws} 不是 Git 仓库（没有 .git 目录），跳过提交。如需版本控制，请先执行 git init。"
    try:
        subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True, timeout=10)
        r = subprocess.run(["git", "commit", "-m", f"bot: {message}"], cwd=ws, capture_output=True, timeout=10)
        out = (r.stdout + r.stderr).decode(errors="replace").strip()
        if "nothing to commit" in out.lower():
            return "无变更，跳过"
        return f"已提交: {message}\n{out[:300]}"
    except Exception as e:
        return f"git_snapshot 跳过: {e}（不影响任务）"

# ===== 实时预览缓存 =====
_preview_file = None
def _live_preview(path="", **kw):
    """标记文件为实时预览目标，并通知前端打开"""
    global _preview_file
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"文件不存在: {path}"
    _preview_file = str(p)
    return json.dumps({"action": "preview", "path": str(p), "name": p.name})

# ===== 子任务并行（WorkBuddy 多类型子 Agent 等效） =====

# 按模式分工具集
_READ_ONLY_TOOLS = {
    "read_file", "list_files", "search_content", "web_search", "web_fetch",
    "read_memory", "system_info",
    "project_index", "code_search", "rag_search",
    "search_conversations", "find_skills", "load_skill",
    "git_diff", "git_log",
}

_RESEARCH_TOOLS = _READ_ONLY_TOOLS | {"sub_task"}  # 可递归拆分研究

_MODE_TOOLS = {
    "explore": _READ_ONLY_TOOLS,     # 纯探索，不可写
    "plan": _READ_ONLY_TOOLS,       # 方案设计，不可写（同 explore）
    "research": _RESEARCH_TOOLS,     # 深度研究，可拆分子任务
    "implement": None,              # None = 全工具，当前默认行为
}

_MODE_PROMPTS = {
    "explore": (
        "你是 Maona 探索子 Agent，只读模式。\n"
        "你只能读取文件、搜索代码、查文档——不能修改任何文件或执行命令。\n"
        "完成后直接返回探索结果（文件路径、关键代码片段、架构概要）。"
    ),
    "plan": (
        "你是 Maona 规划子 Agent，只读模式。\n"
        "你只能分析现有代码和文档，不能修改文件。\n"
        "完成后返回结构化的方案：分步骤、每步目标、涉及文件、预估复杂度。"
    ),
    "research": (
        "你是 Maona 研究子 Agent，搜索模式。\n"
        "你可以搜索网络、检索知识库、查找历史对话来收集信息。\n"
        "完成后返回整理好的研究结果：信息来源、关键发现、建议方案。"
    ),
    "implement": (
        "你是 Maona 执行子 Agent，专注高效完成任务。\n"
        "工作原则：能一步完成不用两步，跳过不必要的检查，完成后直接返回结果。\n"
        "遇到能力不足时，用 find_skills(query) 搜索可安装的技能。"
    ),
}


async def _sub_task(prompt="", context="", tools="", **kw):
    """多类型子 Agent 调用，带独立工具循环（对齐 WorkBuddy Agent 工具）"""
    if not prompt:
        return "sub_task: 未提供任务描述"
    try:
        from providers.manager import ProviderManager
        pm = ProviderManager()
        providers = pm.list_available()
        if not providers:
            return "sub_task: 无可用 Provider"
        name = providers[0]["name"]
        provider = pm.get_provider(name)

        msg = prompt
        if context:
            msg = f"上下文:\n{context}\n\n任务:\n{prompt}"

        # 模式解析：根据任务关键词自动推断，或由调用者显式指定
        mode = kw.get("mode", "")
        if not mode:
            p_lower = prompt.lower()
            if any(k in p_lower for k in ["查", "找", "搜索", "探索", "了解", "分析", "看看",
                                           "find", "search", "explore", "look", "investigate"]):
                mode = "explore"
            elif any(k in p_lower for k in ["方案", "计划", "规划", "设计", "plan", "design", "architect"]):
                mode = "plan"
            elif any(k in p_lower for k in ["研究", "调研", "收集", "research", "gather", "collect"]):
                mode = "research"
            else:
                mode = "implement"

        # 按模式过滤工具集
        from tools.definitions import TOOLS
        from tools.mcp_client import get_mcp_tool_names, get_mcp_tool_def
        allowed = _MODE_TOOLS.get(mode)
        if allowed is not None:
            sub_tools = [t for t in TOOLS if t["function"]["name"] in allowed]
        else:
            sub_tools = list(TOOLS)
            # implement 模式：追加 MCP 工具（如 build_godot_scene）
            for name in get_mcp_tool_names():
                tdef = get_mcp_tool_def(name)
                if tdef:
                    sub_tools.append(tdef)

        max_rounds = int(kw.get("max_rounds", 30 if mode != "implement" else 50))
        sub_system = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["implement"])
        sub_messages = [
            {"role": "user", "content": msg}
        ]
        # sub_tools 已在上面按模式过滤（implement 模式可获全部 TOOLS + MCP 工具）

        for r in range(max_rounds):
            resp = await provider.chat_non_stream(sub_messages, tools=sub_tools)
            content = resp.get("content", "")
            tool_calls = resp.get("tool_calls", [])

            if not tool_calls:
                return content or "子任务完成"

            # 执行工具
            sub_messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
            for tc in tool_calls:
                t_name = tc.get("function", {}).get("name", "")
                t_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                try:
                    t_result = await execute_tool(t_name, t_args)
                except:
                    t_result = "工具执行失败"
                sub_messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": str(t_result)[:20000]})

        return sub_messages[-1].get("content", "") if sub_messages else "子任务完成"
    except Exception as e:
        return f"sub_task 失败: {e}"

# ===== 代码库智能搜索 =====
def _code_search(query="", path="", max_results=15, **kw):
    """多关键词代码搜索，返回相关片段"""
    import re
    p = Path(path).expanduser().resolve() if path else Path.cwd()
    if not p.exists():
        p = Path.cwd()
    
    keywords = query.split()
    if not keywords:
        return "code_search: 请输入搜索关键词"
    
    results = []
    # 搜索代码文件
    CODE_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.css', '.json', '.gd', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.sh', '.bat', '.ps1', '.sql', '.md'}
    SKIP_DIRS = {'node_modules', '__pycache__', '.git', '.maona', 'godot-editor', 'tesseract', '.vscode', 'dist', 'build', '.next'}
    
    try:
        patterns = [re.compile(kw, re.IGNORECASE) for kw in keywords]
    except:
        return f"code_search: 无效正则 '{query}'"
    
    for fpath in sorted(p.rglob("*")):
        if any(d in fpath.parts for d in SKIP_DIRS):
            continue
        if fpath.suffix.lower() not in CODE_EXTS:
            continue
        try:
            text = fpath.read_text(encoding='utf-8', errors='replace')
        except:
            continue
        
        score = 0
        matches = []
        for i, line in enumerate(text.split('\n'), 1):
            line_score = sum(1 for pat in patterns if pat.search(line))
            if line_score:
                score += line_score
                matches.append((i, line.strip()[:120]))
        
        if score > 0:
            results.append({
                "file": str(fpath.relative_to(p)),
                "score": score,
                "matches": len(matches),
                "samples": matches[:3]
            })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:max_results]
    
    if not top:
        return f"未找到与 '{query}' 相关的代码"
    
    lines = [f"🔍 '{query}' — {len(results)} 个文件匹配，显示前 {len(top)} 个:\n"]
    for r in top:
        lines.append(f"\n📄 {r['file']} (相关度: {r['score']}, {r['matches']} 处匹配)")
        for ln, code in r['samples']:
            lines.append(f"  L{ln}: {code}")
    
    return "\n".join(lines)

# ===== 技能自我管理 =====
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "skills"
def _skill_create(name="", display="", description="", body="", **kw):
    if not name or not body:
        return "skill_create: 需要 name 和 body"
    dir_path = SKILLS_DIR / name
    if dir_path.exists():
        return f"skill_create: 技能 '{name}' 已存在，用 skill_update 修改"
    dir_path.mkdir(parents=True)
    info = {
        "name": name,
        "description": display or description or name,
        "category": "general",
        "type": "behavior",
        "author": "Maona AI",
        "tags": [],
        "trigger_keywords": [],
        "body": body
    }
    (dir_path / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
    return f"✅ 已创建技能: {name}"

def _skill_update(name="", body="", **kw):
    if not name or not body:
        return "skill_update: 需要 name 和 body"
    dir_path = SKILLS_DIR / name
    info_path = dir_path / "info.json"
    if not info_path.exists():
        return f"skill_update: 技能 '{name}' 不存在，用 skill_create 创建"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        info["body"] = body
        info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2))
        return f"✅ 已更新技能: {name}"
    except Exception as e:
        return f"skill_update 失败: {e}"

def _skill_delete(name="", **kw):
    if not name:
        return "skill_delete: 需要 name"
    dir_path = SKILLS_DIR / name
    if not dir_path.exists():
        return f"skill_delete: 技能 '{name}' 不存在"
    import shutil
    shutil.rmtree(dir_path)


def _find_skills(query="", install=False, **kw):
    """搜索可用技能（已安装 + 市场），可选安装"""
    if not query:
        return "请提供搜索关键词 (query)"
    # 搜索已安装技能
    installed = _scan_skills()
    matches = [s for s in installed if query.lower() in s.get("description", "").lower()
               or query.lower() in s.get("name", "").lower()
               or any(query.lower() in t.lower() for t in s.get("tags", []))]
    # 搜索市场
    marketplace = _get_market_skills()
    market_matches = [s for s in marketplace
                      if not any(i["id"] == s["id"] for i in installed)
                      and (query.lower() in s.get("description", "").lower()
                           or query.lower() in s.get("name", "").lower()
                           or any(query.lower() in t.lower() for t in s.get("tags", [])))]
    lines = [f"## 技能搜索结果（关键词：{query}）"]
    if matches:
        lines.append(f"\n### 已安装（{len(matches)} 个）")
        for s in matches[:5]:
            status = "✅ 已启用" if s.get("enabled") else "⏸️ 未启用"
            lines.append(f"- **{s['id']}** ({status}) — {s.get('description', '(无描述)')[:100]}")
    if market_matches:
        lines.append(f"\n### 可安装（{len(market_matches)} 个）")
        for s in market_matches[:5]:
            lines.append(f"- **{s['id']}** — {s.get('description', '(无描述)')[:100]}")
            if install:
                ok = _install_skill(s["id"])
                lines.append(f"  {'✅ 已安装' if ok else '❌ 安装失败'}")
    if not matches and not market_matches:
        lines.append("\n未找到匹配技能。尝试换关键词或用 skill_create 自行创建。")
    return "\n".join(lines)

# ===== RAG 语义搜索 =====
_RAG_CACHE: dict[str, 'RagIndex'] = {}
def _get_rag(path: str):
    global _RAG_CACHE
    p = Path(path).expanduser().resolve()
    key = str(p)
    if key in _RAG_CACHE:
        return _RAG_CACHE[key]
    from .rag import RagIndex
    idx = RagIndex(p)
    if idx.load():
        _RAG_CACHE[key] = idx
        return idx
    return None

def _rag_build(path="", force=False, **kw):
    global _RAG_CACHE
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"rag_build: 目录不存在: {path}"
    from .rag import RagIndex
    idx = RagIndex(p)
    if not force:
        if idx.load():
            return f"索引已存在: {idx.stats()}\n加 force=true 强制重建"
    count = idx.build()
    if count == 0:
        return "rag_build: 未找到可索引的文件"
    idx.save()
    _RAG_CACHE[str(p)] = idx
    return f"✅ 索引进度: {idx.stats()}"

def _rag_search(query="", path="", top_k=8, **kw):
    if not query:
        return "rag_search: 请输入搜索内容"
    # 尝试从缓存或索引加载
    idx = None
    if path:
        idx = _get_rag(path)
    if not idx:
        # 扫描可能的工作空间索引
        import os
        for d in os.environ.get("MAONA_WS", ""), os.getcwd():
            if d:
                idx = _get_rag(d)
                if idx: break
    if not idx:
        return "rag_search: 未找到索引，请先运行 rag_build(path)"
    results = idx.search(query, top_k)
    if not results:
        return f"未找到与 '{query}' 语义相关的代码"
    lines = [f"🔍 '{query}' — {len(results)} 个最相关结果:\n"]
    for r in results:
        lines.append(f"\n📄 {r['file']} ({r['lines']}) [相关性: {r['score']:.3f}]")
        lines.append(f"   {r['snippet']}")
    return "\n".join(lines)

# ===== 测试 / Lint / 性能 =====
def _run_test(path="", **kw):
    import subprocess
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"目录不存在: {path}"
    t0 = time.time()
    test_dir = p / "tests" if (p / "tests").exists() else p / "test"
    if (p / "package.json").exists() and "test" in (p / "package.json").read_text(encoding='utf-8', errors='replace'):
        r = subprocess.run(["npm", "test"], cwd=str(p), capture_output=True, timeout=120)
    elif (p / "pytest.ini").exists() or (p / "pyproject.toml").exists() or test_dir.exists():
        r = subprocess.run(["python", "-m", "pytest", "-x", "--tb=short"], cwd=str(p), capture_output=True, timeout=120)
    elif (p / "Makefile").exists():
        r = subprocess.run(["make", "test"], cwd=str(p), capture_output=True, timeout=120)
    else:
        return f"未检测到测试框架（找过 pytest/npm test/make test）"
    elapsed = time.time() - t0
    out = (r.stdout + r.stderr).decode(errors='replace').strip()
    if r.returncode == 0:
        return f"✅ 测试通过 ({elapsed:.1f}s)\n{out[-500:]}"
    else:
        return f"❌ 测试失败 ({elapsed:.1f}s)\n{out[-800:]}"

def _run_check(path="", file="", **kw):
    import subprocess
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"目录不存在: {path}"
    results = []
    py_files = list(p.rglob("*.py")) if not file else [p / file]
    if py_files:
        r = subprocess.run(["python", "-m", "py_compile"] + [str(f) for f in py_files[:20]], capture_output=True, timeout=30)
        err = r.stderr.decode(errors='replace').strip()
        if err:
            results.append(f"Python 语法错误:\n{err[:500]}")
        else:
            results.append("Python 语法: ✅")
    js_files = list(p.rglob("*.js")) if not file else [p / file]
    if js_files and (p / "node_modules").exists():
        for f in js_files[:10]:
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, timeout=10)
            if r.returncode != 0:
                results.append(f"JS 语法错误 {f.name}: {r.stderr.decode(errors='replace')[:200]}")
        if not any("JS 语法错误" in x for x in results):
            results.append("JS 语法: ✅")
    if not results:
        return "未找到可检查的文件类型"
    return "\n".join(results)

def _profile(command="", path="", **kw):
    import subprocess, time
    p = Path(path).expanduser().resolve() if path else Path.cwd()
    if not command:
        return "profile: 需要提供 command"
    t0 = time.time()
    r = subprocess.run(command, shell=True, cwd=str(p), capture_output=True, timeout=60)
    elapsed = time.time() - t0
    out = (r.stdout + r.stderr).decode(errors='replace').strip()
    # 附加会话额度消耗
    cost = ""
    try:
        from .shell import _cost_records
        if _cost_records:
            total_prompt = sum(r.get("prompt", 0) for r in _cost_records)
            total_comp = sum(r.get("completion", 0) for r in _cost_records)
            cost = f"\n\n💰 额度: 输入 {total_prompt} tokens | 输出 {total_comp} tokens | 共 {len(_cost_records)} 次调用"
    except:
        pass
    return f"⏱ 耗时: {elapsed:.2f}s\n状态: {'✅ 成功' if r.returncode == 0 else '❌ 失败'}\n输出:\n{out[:500]}{cost}"

# ===== 知识库 =====
def _kb_create(name="", **kw):
    from .knowledge import create_kb
    return create_kb(name)

def _kb_add_url(kb="", url="", **kw):
    from .knowledge import add_url
    return add_url(kb, url)

def _kb_add(kb="", title="", content="", **kw):
    from .knowledge import add_text
    return add_text(kb, title, content)

def _kb_search(kb="", query="", top_k=5, **kw):
    from .knowledge import search_kb
    return search_kb(kb, query, top_k)

# ===== 项目索引 =====
def _project_index(path="", refresh=False, **kw):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"目录不存在: {path}"
    cache_file = p / ".maona" / "index.json"
    if not refresh and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8")).get("summary", "索引已存在，加 refresh=true 强制刷新")
        except: pass
    # 扫描
    files = []
    for f in sorted(p.rglob("*")):
        if any(x in str(f) for x in ['node_modules', '__pycache__', '.git', '.maona', 'godot-editor', 'tesseract']):
            continue
        if f.is_file():
            try:
                size = f.stat().st_size
                rel = str(f.relative_to(p))
                if size < 100_000:
                    files.append({"path": rel, "size": size})
                else:
                    files.append({"path": rel, "size": size, "large": True})
            except: pass
    # 生成摘要
    exts = {}
    for f in files:
        ext = Path(f["path"]).suffix or "(noext)"
        exts[ext] = exts.get(ext, 0) + 1
    summary = f"项目: {p.name}\n文件数: {len(files)}\n类型: {', '.join(f'{v}x {k}' for k,v in sorted(exts.items(), key=lambda x:-x[1])[:8])}"
    index = {"root": str(p), "file_count": len(files), "extensions": exts, "files": files[:200], "summary": summary}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    return summary


# ===== 智能记忆工具处理器 =====
def _remember_workflow_handler(keywords: str, steps: str) -> str:
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        steps_data = json.loads(steps) if isinstance(steps, str) else steps
        record_workflow(kw_list, steps_data)
        return f"已记录工作流: {', '.join(kw_list[:5])} ({len(steps_data)} 步)"
    except Exception as e:
        return f"记录失败: {e}"


def _search_workflow_handler(intent: str) -> str:
    workflows = suggest_workflow(intent)
    if not workflows:
        return "未找到匹配的历史工作流。"
    lines = [f"找到 {len(workflows)} 个相关历史工作流:"]
    for i, w in enumerate(workflows, 1):
        steps = " -> ".join(s.get("tool", "?") for s in w.get("pipeline", [])[:5])
        lines.append(f"{i}. [{', '.join(w.get('pattern', [])[:3])}] {steps} ({w.get('success_count', 0)}次)")
    return "\n".join(lines)


def _search_graph_handler(query: str, relation: str = "") -> str:
    results = _search_graph(query, top_k=5)
    if not results:
        return f"图谱中未找到与 {query} 相关的实体。"
    lines = [f"图谱搜索结果（{len(results)} 条）:"]
    for r in results:
        related = ", ".join(r.get("related", [])[:3])
        lines.append(f"- {r['name']} [{r.get('type', '?')}] (score={r['score']:.1f})")
    return "\n".join(lines)


def _decompose_task_handler(request: str) -> str:
    return f"任务拆解请求已接收。将在执行阶段根据 {request[:80]} 自动拆解为子任务并逐步执行。"


def _save_checkpoint_handler(summary: str) -> str:
    cid = _create_checkpoint(_current_conv_id, {
        "summary": summary,
        "messages": f"{summary}（检查点已保存）",
    })
    return f"检查点已保存: {cid}"


def _list_checkpoints_handler() -> str:
    cps = _list_checkpoints(_current_conv_id)
    if not cps:
        return "暂无检查点。"
    lines = [f"检查点列表（{len(cps)} 个）:"]
    for cp in cps[:10]:
        lines.append(f"- {cp['id']} | {cp.get('created_at', '')[:16]} | {cp.get('summary', '')}")
    return "\n".join(lines)


# 工具名称 → 执行函数映射
TOOL_HANDLERS = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "search_content": search_content,
    "edit_file": edit_file,
    "run_command": run_command,
    "web_search": web_search,
    "web_fetch": web_fetch,
    "download_file": download_file,
    "run_python": run_python,
    "system_info": system_info,
    "save_memory": save_memory,
    "read_memory": read_memory,
    "save_daily_log": save_daily_log,
    "save_bug_fix": save_bug_fix,
    "git_diff": git_diff,
    "git_log": git_log,
    "rename_file": rename_file,
    "delete_file": delete_file,
    "read_docx": read_docx,
    "read_xlsx": read_xlsx,
    "read_pptx": read_pptx,
    "load_skill": lambda **kw: _async_load(kw.get("skill_id", "")),
    "switch_mode": lambda **kw: (_switch_mode_inner(kw.get("mode", "craft"), kw.get("reason", ""))),
    "task_create": _task_create,
    "task_update": _task_update,
    "task_list": _task_list,
    "restore_backup": _restore_backup,
    "git_snapshot": _git_snapshot,
    "project_index": _project_index,
    "live_preview": _live_preview,
    "preview_html": _live_preview,   # 别名
    "html_preview": _live_preview,   # 别名
    "sub_task": _sub_task,
    # 浏览器自动化
    # LSP 代码智能
    # 部署
    "code_search": _code_search,
    "skill_create": _skill_create,
    "skill_update": _skill_update,
    "skill_delete": _skill_delete,
    "find_skills": _find_skills,
    "rag_build": _rag_build,
    "rag_search": _rag_search,
    "run_test": _run_test,
    "run_check": _run_check,
    "profile": _profile,
    "kb_create": _kb_create,
    "kb_add_url": _kb_add_url,
    "kb_add": _kb_add,
    "kb_search": _kb_search,
    # 文件/数据处理
    "read_csv": read_csv,
    # 系统工具
    "install_pip": install_pip,
    # 创意/媒体工具
    "image_info": image_info,
    "compress_image": compress_image,
    "text_to_speech": text_to_speech,
    # 创意工具
    "cache_env": _cache_env_handler,
    "search_conversations": _search_conversations,
    # 文件操作
    "pdf_read": pdf_read,
    "sql_query": sql_query,
    "api_post": api_post,
    # 系统工具
    "screenshot": screenshot,
    "open_browser": open_browser,
    "clipboard": clipboard,
    "zip_archive": zip_archive,
    "notify": notify,
    "encode_decode": encode_decode,
    "count_tokens": count_tokens,
    "cost_summary": cost_summary,
    # 浏览器自动化
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_fill": browser_fill,
    "browser_extract": browser_extract,
    "browser_wait": browser_wait,
    "browser_close": browser_close,
    # LSP 代码智能
    "lsp_diagnose": lsp_diagnose,
    "lsp_references": lsp_references,
    "lsp_hover": lsp_hover,
    "lsp_outline": lsp_outline,
    "lsp_format": lsp_format,
    # 部署
    "deploy_preview": deploy_preview,
    "deploy_package": deploy_package,
    # Godot 项目操作
    "godot_setup": godot_setup,
    "check_godot_project": check_godot_project,
    "validate_gdscript": validate_gdscript,
    # 创意工具
    "image_generate": image_generate,
    "schedule_task": schedule_task,
    "list_scheduled_tasks": list_scheduled_tasks,
    "cancel_scheduled_task": cancel_scheduled_task,
    "skill_auto_save": skill_auto_save,
    # ComfyUI CLI
    "comfy_cli": comfy_cli,
    "comfy_node_scaffold": comfy_node_scaffold,
    "comfy_node_install": comfy_node_install,
    "comfy_node_publish": comfy_node_publish,
    "comfy_launch": comfy_launch,
    "comfy_model_download": comfy_model_download,
    # 智能记忆
    "remember_workflow": lambda keywords="", steps="", **kw: _remember_workflow_handler(keywords, steps),
    "search_workflow": lambda intent="", **kw: _search_workflow_handler(intent),
    "search_graph": lambda query="", relation="", **kw: _search_graph_handler(query, relation),
    "decompose_task": lambda request="", **kw: _decompose_task_handler(request),
    "save_checkpoint": lambda summary="", **kw: _save_checkpoint_handler(summary),
    "list_checkpoints": lambda **kw: _list_checkpoints_handler(),
}

# 会话内文件读取缓存: {path_abs: (mtime, content)}
_file_cache: dict[str, tuple[float, str]] = {}

# LLM 参数别名映射（模块级常量，避免每次调用重新创建）
_ARG_ALIASES = {
    "run_python": {"script": "code", "source": "code"},
    "write_file": {"file_path": "path", "source": "content", "data": "content"},
    "edit_file": {"file_path": "path"},
    "rename_file": {"new_path": "new_name"},
    "search_content": {"query": "pattern"},
}


async def execute_tool(name: str, arguments: dict) -> str:
    """执行工具调用并返回结果字符串（文件读取有缓存）"""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"错误：未知工具 {name}"

    # 文件读取：检查缓存
    if name == "read_file":
        path = arguments.get("path", "")
        try:
            p = Path(path).expanduser().resolve()
            mtime = p.stat().st_mtime if p.exists() else 0
            cache_key = str(p)
            if cache_key in _file_cache and _file_cache[cache_key][0] == mtime:
                return "(缓存) " + _file_cache[cache_key][1]
            result = await handler(**arguments)
            if not result.startswith("错误"):
                _file_cache[cache_key] = (mtime, result)
            else:
                _file_cache.pop(cache_key, None)
            return result
        except:
            pass

    # 文件写入/编辑：自动备份 + 清除缓存 + 参数标准化
    if name in ("write_file", "edit_file", "delete_file", "rename_file"):
        # 标准化参数：file_path / new_path → path
        if "file_path" in arguments and "path" not in arguments:
            arguments["path"] = arguments.pop("file_path")
        path = arguments.get("path", "") or arguments.get("new_path", "")
        try:
            p = Path(path).expanduser().resolve()
            _file_cache.pop(str(p), None)
            # 自动备份：如果文件存在且不是在工作空间/tmp下
            if p.exists() and name in ("write_file", "edit_file"):
                backup_dir = p.parent / ".maona" / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"{p.name}.{ts}.bak"
                backup_path.write_bytes(p.read_bytes())
        except:
            pass

    # 参数标准化：常见 LLM 叫法映射
    aliases = _ARG_ALIASES.get(name, {})
    for old, new in aliases.items():
        if old in arguments and new not in arguments:
            arguments[new] = arguments.pop(old)

    try:
        import inspect
        if inspect.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler):
            return await handler(**arguments)
        else:
            result = handler(**arguments)
            # 同步函数可能返回协程（如 lambda 包装的 async）
            if inspect.iscoroutine(result):
                return await result
            return str(result) if result is not None else "操作完成"
    except TypeError as e:
        return f"错误：工具参数不正确 - {e}"
    except Exception as e:
        return f"错误：工具执行失败 - {e}"

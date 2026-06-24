"""对话 API - /chat/stream 流式对话 + Tool Use + 记忆集成"""
import json
import asyncio
import time
import os
import re
from pathlib import Path
from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from models.schemas import ChatRequest
from config import SYSTEM_PROMPT, AGENT_MAX_ROUNDS
from tools.definitions import TOOLS
from tools.dispatcher import execute_tool, set_conv_id, set_env_cache_callback
from tools.mcp_client import start_mcp_server, call_mcp_tool, get_mcp_tool_names, get_mcp_tool_def, is_mcp_tool, ensure_mcp_connected
from tools.ocr import ocr_base64, is_vision_model
from memory.context import build_context, get_recent_context
from memory.conversations import (
    ensure_project, create_conversation, save_message, update_title,
    get_conversation, list_conversations, delete_conversation, init_db,
    search_conversation_messages,
)
from memory.store import append_daily, read_longterm, write_longterm
from providers import manager as pm, store as ps
from providers.model_settings import get_settings as get_model_settings
from usage_tracker import record_usage


def _text_content(m):
    """提取消息的纯文本内容（兼容 vision 格式数组）"""
    c = m.content if hasattr(m, 'content') else m.get("content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""

router = APIRouter(prefix="/chat", tags=["chat"])

# 注入环境缓存回调到 dispatcher，消除循环导入
async def _env_cache_wrapper(conv_id: str, updates: dict):
    workspace = _get_current_workspace() or "global"
    await update_env_cache(workspace, conv_id, updates)
set_env_cache_callback(_env_cache_wrapper)

# ===== 持久化 Agent Loop 会话管理（WorkBuddy 等效） =====

class AgentLoopSession:
    def __init__(self, conv_id, provider, project, workspace, provider_name, model, model_budget):
        self.conv_id = conv_id
        self.provider = provider
        self.project = project
        self.workspace = workspace
        self.provider_name = provider_name
        self.model = model
        self.model_budget = model_budget
        self.input_queue = asyncio.Queue()
        self.active = True
        self.last_activity = time.time()
        self.system_prompt = ""  # 首次构建后缓存

_agent_sessions = {}  # 预留：未来会话级状态管理
_conv_prompt_cache: dict[str, str] = {}  # 同对话复用 system prompt

MAX_TOOL_ROUNDS = int(os.getenv("AGENT_MAONA_MAX_ROUNDS", "150"))  # Agent 循环上限，环境变量可覆盖

# 简易限流：每分钟最多 30 次请求
_rate_limits: dict[str, list[float]] = {}
_rate_limit_lock = asyncio.Lock()  # 防止并发写入竞态

# 高风险操作确认等待池
_pending_confirms: dict[str, asyncio.Future] = {}

# 会话级环境缓存：避免每个对话轮都重新探测环境
_session_env_cache: dict[str, dict] = {}

# 会话级请求上下文（使用 contextvars 防止并发请求数据污染）
import contextvars
_current_request_workspace_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("workspace", default="")
_current_request_project_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("project", default="default")

# 便捷访问：向后兼容
def _get_current_workspace():
    return _current_request_workspace_ctx.get() or ""
def _get_current_project():
    return _current_request_project_ctx.get() or "default"

# 会话级环境缓存隔离锁
_env_cache_lock = asyncio.Lock()

async def update_env_cache(workspace: str, conv_id: str, updates: dict):
    """更新会话环境缓存（供工具调用）"""
    cache_key = f"{workspace or 'global'}:{conv_id}"
    async with _env_cache_lock:
        if cache_key not in _session_env_cache:
            _session_env_cache[cache_key] = {}
        _session_env_cache[cache_key].update(updates)

def get_env_cache(workspace: str, conv_id: str) -> dict:
    """获取会话环境缓存"""
    cache_key = f"{workspace or 'global'}:{conv_id}"
    return _session_env_cache.get(cache_key, {})


async def _wait_confirmation(confirm_id: str, timeout: int = 30) -> bool:
    """等待用户确认（带超时）"""
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _pending_confirms[confirm_id] = future
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        _pending_confirms.pop(confirm_id, None)
        return False
    finally:
        _pending_confirms.pop(confirm_id, None)


async def _check_rate_limit(client_ip: str = "local", max_rpm: int = 30) -> bool:
    async with _rate_limit_lock:
        now = time.time()
        window = [t for t in _rate_limits.get(client_ip, []) if now - t < 60]
        _rate_limits[client_ip] = window
        if len(window) >= max_rpm:
            return False
        window.append(now)
        return True
    # 定期清理过期 IP 条目
    if now % 300 < 0.01:  # 约每 5 分钟清理一次
        stale = [k for k, v in _rate_limits.items() if not v]
        for k in stale:
            _rate_limits.pop(k, None)


async def send(msg_type: str, **kw):
    d = {"type": msg_type}
    d.update(kw)
    return json.dumps(d, ensure_ascii=False)


def pick_provider(request: ChatRequest):
    """选择 Provider 和 Model"""
    available = pm.list_available()
    if not available:
        raise ValueError("没有可用的 API，请先在设置中添加")

    # 用户指定了 provider
    if request.provider:
        cfg = ps.get_provider(request.provider)
        if not cfg:
            raise ValueError(f"未找到 Provider: {request.provider}")
        if not cfg.get("api_key"):
            raise ValueError(f"{request.provider} 未配置 API Key")
        model = request.model or (cfg["models"][0] if cfg["models"] else "default")
        return request.provider, model

    # 自动选择第一个可用的
    cfg = ps.get_provider(available[0]["name"])
    if not cfg:
        raise ValueError(f"Provider {available[0]['name']} 配置丢失")
    model = request.model or (cfg["models"][0] if cfg["models"] else "default")
    return available[0]["name"], model


def estimate_tokens(messages: list[dict]) -> int:
    """估算 token 数：中文 ~1 token/字，英文 ~0.25 token/字符，计入 tool_calls 和 role 开销"""
    total = 0
    for m in messages:
        role = getattr(m, "role", None) or ""
        # role marker 开销 (~4 tokens)
        total += 4

        content = getattr(m, "content", None) or ""
        if isinstance(content, str):
            cn = sum(1 for ch in content if "\u4e00" <= ch <= "\u9fff")
            en = len(content) - cn
            total += cn + int(en * 0.25)  # 修正：英文/代码 ~0.25 token/字符
        elif isinstance(content, list):
            total += 200  # 图片消息估算

        # tool_calls 字段开销
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    total += 10  # id + type + function wrapper
                    total += len(fn.get("name", ""))  # 函数名
                    args = fn.get("arguments", "")
                    total += len(args) // 3  # JSON 参数 ~0.33 token/字符

        # tool_call_id 开销
        tc_id = getattr(m, "tool_call_id", None)
        if tc_id:
            total += 4 + len(str(tc_id)) // 2  # "tool_call_id" + 值

    return total


TOKEN_BUDGET = int(os.getenv("AGENT_MAONA_TOKEN_BUDGET", "800000"))  # 800K 默认，DeepSeek 1M 留余量
COMPRESS_THRESHOLD = float(os.getenv("AGENT_MAONA_COMPRESS_THRESHOLD", "0.0"))  # 0 = 自动按模型选择

def get_compress_threshold(model_budget: int) -> float:
    """根据模型上下文大小动态选择压缩阈值。环境变量覆盖优先。"""
    if COMPRESS_THRESHOLD > 0:
        return COMPRESS_THRESHOLD  # 用户强制覆盖
    if model_budget >= 800000:
        return 0.80  # 大上下文（DeepSeek 800K+）→ 80%触发，充分利用窗口
    elif model_budget >= 200000:
        return 0.65
    else:
        return 0.50  # 小上下文（GLM 等 128K 以内）→ 保守，留空间给输出

# 模型上下文大小映射（真实上下文窗口 + 内部预算留 20% 安全余量）
_MODEL_CONTEXT_LIMITS = {
    "deepseek-chat":     800000,   # DeepSeek V4 真实 1M context / 内部预算 800K
    "deepseek-reasoner": 800000,
    "deepseek-v4-flash": 800000,
    "deepseek-v4-pro":   800000,
    "deepseek":          800000,
    "glm-4":             102400,   # GLM-4 真实 128K
    "glm-4-flash":       102400,
    "glm":               102400,
    "qwen":              160000,   # Qwen 真实 200K（含预留）
    "gpt-4o":            200000,
    "gpt-4":             120000,
    "claude":            300000,
}
# 真实模型上下文窗口（用于UI展示，非内部预算）
_MODEL_REAL_CONTEXTS = {
    "deepseek-chat":     1048576,  # 1M tokens
    "deepseek-reasoner": 1048576,
    "deepseek-v4-flash": 1048576,
    "deepseek-v4-pro":   1048576,
    "deepseek":          1048576,
    "glm-4":             131072,   # 128K
    "glm-4-flash":       131072,
    "glm":               131072,
    "qwen":              200000,
    "gpt-4o":            250000,
    "gpt-4":             128000,
    "claude":            400000,
}

def get_model_context_window(provider_name: str = "", model_name: str = "") -> int:
    """返回模型真实上下文窗口大小（用于 UI 展示）"""
    name = (model_name or provider_name or "").lower()
    for key, limit in _MODEL_REAL_CONTEXTS.items():
        if key in name:
            return limit
    return 200000  # 默认 200K

def get_model_budget(provider_name: str = "", model_name: str = "") -> int:
    """根据模型动态返回内部 token 预算（含安全余量）"""
    name = (model_name or provider_name or "").lower()
    for key, limit in _MODEL_CONTEXT_LIMITS.items():
        if key in name:
            return min(limit, TOKEN_BUDGET)  # 取较小值（环境变量可强制设大值）
    return min(500000, TOKEN_BUDGET)  # 未知模型默认 500K


async def summarize_conversation(provider, messages: list[dict], project: str) -> str:
    """用 LLM 将对话总结为结构化记忆，保留工具调用中的关键文件路径和决策"""
    # 保留 user/assistant 消息 + 最近的 tool 消息（重命名 role 兼容非标准 role）
    slim = []
    for m in messages:
        role = m.get("role", m["role"]) if isinstance(m, dict) else getattr(m, "role", None)
        content = (m.get("content") or "") if isinstance(m, dict) else (getattr(m, "content", None) or "")
        if not content:
            continue
        if role in ("user", "assistant"):
            slim.append({"role": role, "content": content[:5000]})
        elif role == "tool":
            # 工具结果保留，重命名为 "user"（非标准 role 会被某些 API 拒绝）
            tc_id = m.get("tool_call_id", "") if isinstance(m, dict) else getattr(m, "tool_call_id", "")
            prefix = f"[工具结果 - {tc_id[:20]}]: " if tc_id else "[工具结果]: "
            slim.append({"role": "user", "content": prefix + content[:2500]})

    # 只保留最近的 tool 结果（防止摘要 payload 过大）
    tool_msgs = [m for m in slim if m["content"].startswith("[工具结果]")]
    if len(tool_msgs) > 25:
        for m in tool_msgs[:-25]:
            slim.remove(m)

    if not slim:
        return ""

    slim.append({
        "role": "user",
        "content": (
            f"请将以上对话总结为详细的结构化工作日志（{project}）。这是压缩后的上下文，之后我就只能看到这份摘要了，请务必详尽。\n\n"
            "用 Markdown 格式，严格包含以下各项：\n"
            "1. 用户请求了什么（原文保留关键描述）\n"
            "2. 完成的操作（逐条列出：创建/修改了哪些文件路径、每个操作的目的、执行了什么关键命令）\n"
            "3. 关键决策（为什么选这个方案、弃用了什么方案、有哪些重要的 API 或架构约定）\n"
            "4. 遇到的错误及如何修复的（保留至少 1-3 个关键代码行的上下文，如果无则写「无」）\n"
            "5. 当前状态：已确认完成的部分、尚在进行中的部分、下一步该做什么\n"
            "6. 工具调用统计：共约 N 个工具调用，大致完成了百分之多少的进度\n\n"
            "要求：事实性、有文件路径和代码片段、不要客套话。信息量优先于简洁。"
        ),
    })

    try:
        resp = await provider.chat_non_stream(slim, tools=None)
        content = resp.get("content") or ""
        return content[:5000] if content else ""
    except Exception as e:
        print(f"[Maona] 对话摘要生成失败: {type(e).__name__}: {e}")
        return ""


async def stream_chat(request: ChatRequest):
    try:
        provider_name, model = pick_provider(request)
        # 根据模型动态设置 token 预算
        model_budget = get_model_budget(provider_name, model)
    except ValueError as e:
        yield await send("error", content=str(e))
        yield await send("done")
        return

    # 新消息超过模型上下文窗口 → 直接拒绝，不浪费 API 调用
    new_tokens = estimate_tokens(request.messages)
    if new_tokens > model_budget:
        yield await send("error", content=f"当前消息过大（约 {new_tokens:,} tokens），超过模型上下文窗口（{model_budget:,} tokens）。请拆分消息或缩短内容。")
        yield await send("done")
        return

    provider = pm.get_provider(provider_name, model)

    # 降级包装：主 Provider 失败时自动切换备用
    from providers.wrapper import FallbackProviderWrapper
    provider = FallbackProviderWrapper(provider_name, model)

    project = request.project_id or "agent_maona"
    workspace = request.workspace  # 工作空间路径，用于本地 .maona/ 存储
    # 路径遍历防护：验证 workspace 在安全范围内
    if workspace:
        try:
            ws_path = Path(workspace).expanduser().resolve()
            # 检查是否为系统目录
            ws_str = str(ws_path).replace("\\", "/").lower()
            blocked_prefixes = [
                "c:/windows", "c:/program files", "c:/program files (x86)", "/etc", "/sys", "/proc", "/dev", "/boot"
            ]
            for prefix in blocked_prefixes:
                if ws_str.startswith(prefix):
                    print(f"[Maona] 拒绝访问系统目录作为工作空间: {workspace}")
                    yield await send("error", content="安全限制：不能使用系统目录作为工作空间。")
                    return
            workspace = str(ws_path)
        except Exception:
            print(f"[Maona] 工作空间路径解析失败: {workspace}")
            workspace = None
    _current_request_workspace_ctx.set(workspace or "")  # 使用 contextvar，隔离并发请求
    _current_request_project_ctx.set(project)  # 使用 contextvar，隔离并发请求

    # MCP 预热：仅在涉及 Godot 且编辑器已运行时连接
    _mcp_warmed = False
    _mcp_warning = ""
    user_text = " ".join(_text_content(m) for m in request.messages)
    needs_godot = any(k in user_text.lower() for k in ("godot", "galgame", "gdscript", ".tscn", "游戏", "场景", "节点",
                                              "project.godot", "build_godot", "视觉小说", "godot-mcp",
                                              "mcp", "node.js", "9080"))
    if needs_godot:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            godot_running = s.connect_ex(("127.0.0.1", 9080)) == 0
            s.close()
        except Exception:
            godot_running = False
        if godot_running:
            try:
                from tools.mcp_client import ensure_mcp_connected
                _mcp_warmed = await ensure_mcp_connected()
            except Exception as e:
                print(f"[Maona] MCP 连接异常: {e}")
        if not _mcp_warmed:
            if not godot_running:
                _mcp_warning = ("\n\n⚠️ Godot MCP 未连接（9080 端口无监听）。\n"
                                "建议先告诉用户：「请在 Godot 中打开项目，项目设置→插件→启用 GodotMCP」。\n"
                                "如果用户无法启用 MCP（插件有问题、不想装等），可以用 write_file 写 .tscn 作为降级方案。\n"
                                "不要跳过这个提示直接开始——先问用户是否方便启用 MCP。")
            else:
                _mcp_warning = ("\n\n⚠️ Maona 的 Node.js MCP 桥接服务启动失败，build_godot_scene 工具不在你的工具列表中。"
                                "如果用户问 MCP 状态，告知：虽然 Godot 编辑器在 9080 端口运行，但 Maona 的 Node.js MCP 桥接未成功启动。")

    # 为工作空间创建 .maona/ 目录（如果不存在）
    if workspace:
        ws_maona = Path(workspace) / ".maona"
        ws_maona.mkdir(parents=True, exist_ok=True)

    # 对话持久化
    await ensure_project(project)
    conv_id = request.conversation_id or await create_conversation(project)
    set_conv_id(conv_id)  # 同步到任务管理系统
    
    # MCP 健康检查 + 缓存失效：若 MCP 状态变化，清 prompt 缓存以重建工具上下文
    if needs_godot and _mcp_warmed and conv_id in _conv_prompt_cache:
        _conv_prompt_cache.pop(conv_id, None)
    # 保存最新一条用户消息（历史消息已存过，避免重复）
    user_msgs = [m for m in request.messages if m.role == "user"]
    if user_msgs:
        await save_message(conv_id, "user", _text_content(user_msgs[-1]))

    _model_context_window = get_model_context_window(provider_name, model)
    yield await send("meta", provider=provider_name, model=model, conversation_id=conv_id, token_budget=model_budget,
                     context_window=_model_context_window)

    # Claude Code 风格：使用完整对话历史，不注入摘要
    _all_history = []
    if request.conversation_id:
        try:
            prev = await get_conversation(request.conversation_id)
            if prev and prev.get("messages"):
                _all_history = prev["messages"]
        except Exception:
            pass
    tailored_prompt = SYSTEM_PROMPT  # 默认值，防未定义
    if conv_id in _conv_prompt_cache:
        tailored_prompt = _conv_prompt_cache[conv_id]
    else:
        custom_system = ""
        if workspace:
            system_path = Path(workspace) / ".maona" / "system.md"
            if system_path.exists():
                custom_system = system_path.read_text(encoding="utf-8").strip()
            # Claude Code 风格：MAONA.md 项目级约定文件
            maona_md = Path(workspace) / "MAONA.md"
            if maona_md.exists():
                conventions = maona_md.read_text(encoding="utf-8").strip()
                if custom_system:
                    custom_system += f"\n\n## 项目约定 (MAONA.md)\n{conventions}"
                else:
                    custom_system = f"## 项目约定\n{conventions}"
            # 加载工作空间规则
            rules_path = Path(workspace) / ".maona" / "rules.md"
            if rules_path.exists():
                rules = rules_path.read_text(encoding="utf-8").strip()
                if custom_system:
                    custom_system += f"\n\n## 工作空间规则\n{rules}"
                else:
                    custom_system = f"## 工作空间规则\n{rules}"
        if custom_system:
            tailored_prompt = f"{custom_system}\n\n---\n注意：以上规则来自工作空间 ({workspace})，请严格遵循。"
        else:
            tailored_prompt = SYSTEM_PROMPT

    # 注入工作空间路径
    if workspace:
        tailored_prompt += f"\n工作空间: {workspace}"

    # 注入用户画像（Cloud Memory 本地等效 — 跨对话自动积累）
    from memory.profile import get_profile_text
    profile_text = get_profile_text()
    if profile_text:
        tailored_prompt += f"\n\n{profile_text}"

    # 注入会话级环境缓存（避免每轮重复探测 Godot/Python/Node 环境）
    cache_key = f"{workspace or 'global'}:{conv_id}"
    cached_env = _session_env_cache.get(cache_key, {})
    if cached_env:
        env_lines = ["\n## 会话环境（已缓存，本对话中无需重新探测）"]
        for k, v in cached_env.items():
            if isinstance(v, bool):
                env_lines.append(f"- {k}: {'✅' if v else '❌'}")
            else:
                env_lines.append(f"- {k}: {v}")
        tailored_prompt += "\n".join(env_lines)
        tailored_prompt += ("\n⚠️ 以上环境信息在本轮对话开始时已确认，直接使用即可，严禁重新执行环境探测命令（包括"
                           "任何 Skill 中的'环境检测'步骤）。除非用户明确说「环境变了」「重启了编辑器」「换了工作空间」。")

    # 注入人设提示词
    if request.persona_id and request.persona_id != "default":
        from personas import get_persona
        persona = get_persona(request.persona_id)
        if persona and persona.get("prompt"):
            tailored_prompt += f"\n\n## 当前人设：{persona['name']}\n{persona['prompt']}"

    # 注入已启用的技能摘要（按需加载模式）
    from skills import get_enabled_prompts
    skill_prompts = get_enabled_prompts()
    if skill_prompts:
        tailored_prompt += f"\n\n## 可用技能\n{skill_prompts}"

    # 注入模式指令
    mode = request.mode or "craft"
    from tools.dispatcher import set_mode as set_dispatcher_mode
    set_dispatcher_mode(mode)  # 同步初始模式到 dispatcher

    tailored_prompt += "\n\n## 工作模式"
    tailored_prompt += "\n当前只有一个模型可用，不需要在模型间切换。你可以用 switch_mode 工具切换工作模式："
    tailored_prompt += "\n- 用户只是问问题/查资料 → 切 ask 模式（只读）"
    tailored_prompt += "\n- 用户要求做复杂修改/新功能 → 先切 plan 出方案，确认后切 craft 执行"
    tailored_prompt += "\n- 简单修改/单文件改动 → 保持 craft 直接做"
    tailored_prompt += "\n\n## 任务完成标准（必须遵守）"
    tailored_prompt += "\n1. 每轮工具调用后问自己：用户要的东西做完了吗？做完了就停，写一段中文总结告诉用户做了什么"
    tailored_prompt += "\n2. 完成任务后必须用自然语言汇报结果，格式：\"完成了 [N] 个步骤：①... ②... → 结果：...\""
    tailored_prompt += "\n3. 不要做完事就沉默——用户不知道你改了什么文件、效果是什么。主动说清楚"
    tailored_prompt += "\n4. 不要重复检查已创建的文件或已验证的目录——做完了就是做完了"
    tailored_prompt += "\n5. 若工具返回成功就相信它，不要再用另一个工具验证。但以下验证类工具返回的错误必须修复：validate_gdscript(🔴)、check_godot_project(🔴)、verify_scene(失败)、get_godot_errors(ERROR)。这些是自动质量关卡，不能跳过。"
    tailored_prompt += "\n6. 改完代码后、汇报完成前，必须调用 validate_gdscript(project_dir) 做通用验证。有 🔴 就修→重测→修→重测，直到全绿。这是完成标准的一部分，不是可选项。"
    tailored_prompt += "\n\n## 分阶段执行（复杂任务强制）"
    tailored_prompt += "\n涉及 10+ 工具调用或预估 30+ 分钟的任务，分两阶段："
    tailored_prompt += "\n  **Plan 阶段**：仅研究代码/分析需求 → 输出结构化的分步计划（每个步骤含预期文件清单和验证方式）→ 停止，等待用户确认。"
    tailored_prompt += "\n  **Craft 阶段**：用户确认后，严格按照计划执行。不重新设计、不分心加功能。每步完成后调 validate_gdscript 验证。"
    tailored_prompt += "\n\n## 任务跟踪（强制执行 — 不遵守任务质量必崩）"
    tailored_prompt += "\n涉及 3 步以上或预估 5+ 轮工具调用的任务，必须在开始前用 task_create 建立结构化计划。"

    # 注入验证闭环提示
    from memory.verify import VALIDATION_PROMPT
    tailored_prompt += VALIDATION_PROMPT
    tailored_prompt += "\n每完成一步立即调 task_update 标记完成。这不仅是进度展示——上下文压缩后你需要靠 task_list 回忆做了多少、还剩什么。"
    tailored_prompt += "\n如果跳过 task_create，上下文压缩后你会「失忆」——不知道哪些文件已创建、哪些逻辑已完成。"
    tailored_prompt += "\n做任务前先用 project_index(path) 了解项目结构，别盲目翻文件。"
    tailored_prompt += "\n寻找代码用 code_search(query) 智能搜索，比 search_content 更聪明。"
    tailored_prompt += "\n做任务前先 rag_build(path) → rag_search(query) 语义搜索，找\"错误处理\"能找到 try/catch。"
    tailored_prompt += "\n需要长期记忆的知识（项目文档/API参考/教程）用 kb_create → kb_add → 之后 kb_search 搜索。"
    tailored_prompt += "\n多个独立子任务可以同时调 sub_task(prompt) 并行跑。支持四种模式（自动推断或显式指定 mode）："
    tailored_prompt += "\n  - explore：纯只读探索（查文件、搜代码、分析结构）——不能改文件，最安全最快"
    tailored_prompt += "\n  - plan：只读规划（分析现有代码、出新方案）——不能改文件"
    tailored_prompt += "\n  - research：搜索研究（网络搜索、知识库检索、历史对话搜索）——不能改文件"
    tailored_prompt += "\n  - implement：全工具执行（默认，什么都能做）——仅用于需要改文件的子任务"
    tailored_prompt += "\n  例如：sub_task(prompt=\"分析 galgame 项目的 GDScript 架构缺陷\", mode=\"explore\")"
    tailored_prompt += "\n发现反复做的操作模式？用 skill_create(name, body) 创建技能，下次直接 load_skill 加载。"
    tailored_prompt += "\n遇到不熟悉的任务、需要特定领域能力、或现有工具无法满足需求时，必须先调 find_skills(query=\"关键词\") 搜索是否有匹配的技能——不要直接说\"我做不到\"。"
    tailored_prompt += "\n这样你能看到进度条，不会遗漏步骤，也不会做完后忘记汇报。"
    tailored_prompt += "\n每次 write_file/edit_file 前会自动备份原文件到 .maona/backups/。"
    tailored_prompt += "\n改完代码后调 run_test(path) 验证没改坏，调 run_check(path) 检查语法/类型。创建 .py 文件后立即 run_check 确认无语法错误——这是自验证闭环，不要省略。"
    tailored_prompt += "\n如果工具执行失败，仔细阅读错误信息中的具体原因后修正，不要盲目重试相同的参数。"
    tailored_prompt += "\n\n## Godot 项目工具选择规则（强制，优先级最高）"
    tailored_prompt += "\n处理 Godot 项目相关任务时，以下规则优先级高于任何加载的 Skill："
    tailored_prompt += "\n1. 项目创建/初始化：必须走 load_skill(\"godot-dev\") → godot-deploy → godot-new 完整链，严禁使用 godot_setup（已弃用，建出的项目与标准流程不兼容）"
    tailored_prompt += "\n2. 场景编辑：使用 GodotMCP 原子工具操作场景和节点——create_scene(path, root_type, root_name) 创建场景，create_node(parent_path, node_type, node_name) 添加节点（parent_path 用 /root/父节点 格式），update_node_property(node_path, property, value) 设属性（Color=[r,g,b,a] 0-1），create_script(script_path, content) 写脚本并用 update_node_property 的 script 属性挂载到节点，save_scene(path) 保存。这些工具直接操作 Godot 编辑器，格式永远正确。"
    tailored_prompt += "\n3. 项目验证：创建/修改 Godot 项目后必须依次调 validate_gdscript + check_godot_project 做静态校验，然后用 verify_scene(project_dir, scene_path) 在 Godot 编辑器中加载场景做运行时诊断。最后用 get_godot_errors(project_dir) 读取 Godot 日志中最近的 ERROR/WARNING，检查运行时崩溃。"
    tailored_prompt += "\n3a. ⚠️ 修复循环（强制执行）：如果任何验证（validate_gdscript/check_godot_project/verify_scene）返回 🔴 错误（不是 🟡 警告），你必须立即定位原因、修复、重新验证。不允许把 🔴 错误当成「已知问题」或跳过。至少修复-重测一次，直到所有 🔴 消失或你确认无法修复（需向用户说明原因）。"
    tailored_prompt += "\n4. Skill 中的「必做不可省略」类指令，如果与系统级约束冲突（如「环境已缓存，严禁重探测」），以系统级约束为准"
    tailored_prompt += "\n5. 不要用 write_file + run_command 等原始工具去重新实现 godot-deploy/godot-new 的功能——Skill 的正确性远高于手写。但 GodotMCP 原子工具（create_scene/create_node 等）是推荐的场景编辑方式。"
    tailored_prompt += "\nWindows 上简单命令优先用 cmd /c（如 `cmd /c dir`），需要复杂逻辑再用 PowerShell。PS 输出已自动重定向，不用担心。"
    tailored_prompt += "\nGodot 项目生成 .gd 脚本后，用 validate_gdscript(project_dir=项目目录) 检查信号/类型/API 错误，修复后再继续。"
    tailored_prompt += "\n完成环境探测后调 cache_env(has_project=True, ...) 缓存结果，后续轮次不要再重复探测。"
    tailored_prompt += "\n改完文件后调用 git_snapshot(message=\"做了什么\") 自动提交，出错了 git reset HEAD~1 就能回滚。"
    tailored_prompt += "\n如果某步改错了，用 restore_backup(path) 回滚。工作空间 .maona/checkpoint.json 记录当前进度。"
    tailored_prompt += "\n\n## 对话续接规则（最高优先级，所有消息默认适用）"
    tailored_prompt += "\n⚠️ 本对话是连续的工程会话，不是每轮重启的独立对话。对话历史就是你最好的信息来源。"
    tailored_prompt += "\n  - 对话历史中已记录你做了什么、创建了什么文件、项目是什么状态。直接信它，直接行动。"
    tailored_prompt += "\n  - 禁止写「让我先看看...」「先检查项目现状」「了解当前状态」这类确认性质的探索。如果对话历史里写了项目在哪、文件叫什么——你已经知道了。"
    tailored_prompt += "\n  - 除非用户说「项目变了」「换了个目录」「删了重建」，否则不要在每轮开始时重新探测环境或列出目录。cache_env 已缓存的结果就是你的起点。"
    tailored_prompt += "\n  - 直接执行用户要求的具体操作，不需要在前面加一段背景回顾。"
    tailored_prompt += "\n\n## 跨对话记忆（强制执行）"
    tailored_prompt += "\n每次完成实质性工作（≥3 步操作）后，必须调 save_daily_log(content=\"...\") 写日志。日志会被注入到下一轮对话中，是跨对话传承的唯一桥梁。"
    tailored_prompt += "\n日志内容必须包含：①做了什么（工具/Skill 名称）②创建/修改了哪些文件（完整路径清单）③遇到什么问题、如何修复。"
    tailored_prompt += "\n格式示例：“## [14:00] 创建 Galgame 项目 | - 操作：godot-deploy 下载编辑器 + godot-new 建项目 | - 文件：F:\\game\\galgame\\project.godot, scenes/main/main.tscn, scripts/autoload/dialogue_manager.gd | - 结果：项目创建成功，TSCN 有 StyleBoxFlat.new() 格式错误待修复”"
    tailored_prompt += "\n不是等到对话结束才写——每完成一个子任务就写一条。不写日志的后果：下次对话 Agent 完全不知道你创建了什么文件、用了什么架构、踩了什么坑。"
    
    # 缓存 system prompt，同一对话后续消息直接复用
    if conv_id not in _conv_prompt_cache:
        _conv_prompt_cache[conv_id] = tailored_prompt

    # MCP 未就绪警告（追加到已构建的 prompt 末尾）
    if _mcp_warning:
        tailored_prompt += _mcp_warning

    # 注入工作空间记忆（琐碎对话跳过，节省 tokens）
    last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    is_trivial_msg = len(last_user) < 20
    memory_ctx = "" if is_trivial_msg else build_context(project, workspace)
    if memory_ctx:
        tailored_prompt += f"\n\n## 工作空间记忆\n{memory_ctx}"

    # 注入程序记忆（工作流模式）
    try:
        from memory.procedural import get_system_prompt_hint
        proc_hint = get_system_prompt_hint(request.message)
        if proc_hint:
            tailored_prompt += f"\n{proc_hint}"
    except Exception:
        pass

    # 注入已知错误修复方案
    from tools.memory_tools import get_known_bugs
    known_bugs_ctx = get_known_bugs(workspace)
    if known_bugs_ctx:
        tailored_prompt += known_bugs_ctx

    # Claude Code 风格：完整对话历史，无条数硬上限，按 token 预算动态裁剪
    all_raw = list(_all_history)
    seen_user_contents = {m.get("content", "") for m in all_raw if isinstance(m, dict) and m.get("role") == "user"}
    for m in request.messages:
        content = m.content or ""
        if content and content not in seen_user_contents:
            all_raw.append({"role": "user", "content": content})
            seen_user_contents.add(content)
    from types import SimpleNamespace as _SimpleNS
    all_msgs = [_SimpleNS(**(dict(m) if isinstance(m, dict) else {"role": m.role, "content": m.content})) for m in all_raw]
    total_tokens = estimate_tokens(all_msgs)

    if total_tokens > model_budget:
        # 从最新消息往前数，保留能塞进 90% 预算的消息
        keep, keep_tokens = [], 0
        budget_target = int(model_budget * 0.90)
        for m in reversed(all_msgs):
            t = estimate_tokens([m])
            if keep_tokens + t > budget_target and keep:
                break
            keep.insert(0, m)
            keep_tokens += t
        old_msgs = [m for m in all_msgs if m not in keep]
        if old_msgs:
            try:
                summary_msgs = [{"role": m.role, "content": m.content} for m in old_msgs]
                if "## 对话摘要" in tailored_prompt:
                    summary_msgs.insert(0, {"role": "user", "content": "之前的对话摘要：\n" + tailored_prompt.split("## 对话摘要\n", 1)[1].split("\n\n", 1)[0]})
                compressed = await summarize_conversation(provider, summary_msgs, project)
                if compressed:
                    if "## 对话摘要" in tailored_prompt:
                        tailored_prompt = tailored_prompt.split("## 对话摘要\n")[0].strip()
                    tailored_prompt += f"\n\n## 对话摘要\n{compressed}"
            except Exception:
                pass
        recent = keep
    else:
        recent = all_msgs

    messages = [{"role": "system", "content": tailored_prompt}]
    for m in recent:
        # 工具结果消息在历史对话中用于恢复上下文
        if m.role == "tool":
            msg = {"role": "tool", "content": m.content or ""}
            if hasattr(m, "tool_call_id") and m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            messages.append(msg)
            continue
        content = m.content
        # 智能图片处理：多模态模型直传，文本模型 OCR 降级
        if isinstance(content, list):
            if not is_vision_model(model or ""):
                # 文本模型：OCR 提取文字替换图片
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        img_url = part.get("image_url", {}).get("url", "")
                        if img_url:
                            text_parts.append(f"[图片OCR结果]: {ocr_base64(img_url)}")
                        else:
                            text_parts.append("[图片: URL为空]")
                    elif isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = "\n\n".join(text_parts)
            # vision 模型：保持数组格式直传

        # 从历史 assistant 消息的 tool_calls 中重建 tool 结果消息
        tool_calls_data = getattr(m, "tool_calls", None) or m.get("tool_calls") if isinstance(m, dict) else None
        if tool_calls_data and isinstance(tool_calls_data, list):
            # 构建 assistant 消息（带 tool_calls 但不带 result）
            api_tool_calls = []
            tool_results = []
            for tc in tool_calls_data:
                if isinstance(tc, dict):
                    api_tc = {
                        "id": tc.get("id", f"call_{len(api_tool_calls)}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("tool", tc.get("function", {}).get("name", "")),
                            "arguments": json.dumps(tc.get("args", tc.get("function", {}).get("arguments", {})), ensure_ascii=False)
                        }
                    }
                    api_tool_calls.append(api_tc)
                    if tc.get("result"):
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": api_tc["id"],
                            "content": str(tc["result"])[:5000]
                        })
            messages.append({"role": m.role, "content": content or None, "tool_calls": api_tool_calls})
            messages.extend(tool_results)
        else:
            messages.append({"role": m.role, "content": content})

    # Claude Code 风格：注入对话级 todo 任务列表
    if workspace and request.conversation_id:
        todo_path = Path(workspace) / ".maona" / f"todo_{request.conversation_id}.md"
        if todo_path.exists():
            todo_content = todo_path.read_text(encoding="utf-8").strip()
            if todo_content:
                messages.append({"role": "user", "content": f"## 当前任务进度 (todo)\n{todo_content}\n请根据以上进度继续工作。用 task_update 完成时顺便更新 todo 文件。"})

    final_text = ""
    has_error = False
    final_reasoning = None  # 最后一轮推理（用于纯推理回复）
    all_reasoning = []  # 所有轮次的推理
    all_tool_calls = []
    _message_saved = False
    MAX_RETRIES = 2
    MAX_AUTO_CONTINUES = 8  # 持久循环：最多自动续接 8 轮（↑5）
    auto_continue_round = 0
    _completion_exits = 0  # 断路器：连续完成文本次数
    _runtime_diag = {"total_rounds": 0, "total_tool_calls": 0, "phase_events": [], "compressions": [], "code_analysis": [], "injections": [], "errors": []}  # 诊断数据
    # === 自适应探索预算 ===
    _project_file_count = 0
    _exploration_budget = 5
    _explored_files = set()
    _consecutive_no_action = 0
    ACTION_TOOLS = {"write_file", "edit_file", "delete_file", "rename_file", "task_create", "task_update", "skill_create", "skill_update", "skill_delete", "kb_create", "kb_add_url", "kb_add", "save_memory", "save_daily_log"}
    def _update_exploration_budget(fc):
        nonlocal _exploration_budget
        if fc <= 0: _exploration_budget = 5
        elif fc <= 15: _exploration_budget = 3
        elif fc <= 50: _exploration_budget = 4
        elif fc <= 200: _exploration_budget = 6
        elif fc <= 500: _exploration_budget = 8
        else: _exploration_budget = 10
    def _parse_file_count(text):
        import re as _re; m = _re.search(r'文件数[：:]\s*(\d+)', text); return int(m.group(1)) if m else 0
    _pending_tasks = 0  # 简单任务计数，不用于 Phase 决策
    _completed_tasks = 0
    _last_checkpoint_round = 0
    try:
        while auto_continue_round < MAX_AUTO_CONTINUES:
            for round_i in range(MAX_TOOL_ROUNDS):
                retry_count = 0  # 每轮独立的 retry 计数
                # 使用当前动态模式（AI 可能通过 switch_mode 工具切换了）
                from tools.dispatcher import get_mode as get_dynamic_mode
                current_mode = get_dynamic_mode()
                ms = get_model_settings()
                resp = await provider.chat_non_stream(messages, get_enabled_tools(current_mode),
                    temperature=ms.get("temperature"), max_tokens=ms.get("max_tokens"), top_p=ms.get("top_p"),
                    thinking_enabled=ms.get("thinking_enabled", False), reasoning_effort=ms.get("reasoning_effort", "high"))
                if resp.get("error"):
                    has_error = True
                    yield await send("error", content=resp["error"])
                    break

                # 记录用量
                try:
                    usage = resp.get("usage", {})
                    tokens_in = usage.get("prompt_tokens") or estimate_tokens(messages)
                    tokens_out = usage.get("completion_tokens") or (estimate_tokens([{"content": resp.get("content", "") or (resp.get("tool_calls") and json.dumps(resp["tool_calls"]))}]) if resp.get("content") or resp.get("tool_calls") else 0)
                    if tokens_in or tokens_out:
                        last_user_text = ""
                        for m in reversed(request.messages):
                            if m.role == "user":
                                last_user_text = _text_content(m)[:200]
                                break
                        record_usage(
                            model=model,
                            provider=provider_name,
                            conversation_id=conv_id,
                            tokens_input=tokens_in,
                            tokens_output=tokens_out,
                            prompt_preview=last_user_text,
                        )
                        print(f"[UsageTracker] 已记录 {model}: {tokens_in}+{tokens_out} tokens")
                except Exception as e:
                    print(f"[UsageTracker] 记录异常: {e}")

                _runtime_diag["total_rounds"] += 1
                tool_calls = resp.get("tool_calls")
                reasoning = resp.get("reasoning")
                if reasoning:
                    final_reasoning = reasoning
                    yield await send("reasoning", content=reasoning)
                if tool_calls:
                    _runtime_diag["total_tool_calls"] += len(tool_calls)
                    yield await send("step", round=round_i + 1, total=MAX_TOOL_ROUNDS)

                    # 发送模型在当前轮的说明文字
                    round_text = resp.get("content") or ""
                    if round_text:
                        yield await send("token", content=round_text)
                        final_text = (final_text + "\n" + round_text).strip()  # 累积每轮说明
    
                    # 批量执行所有工具调用，收集结果
                    round_results = []
                    tasks = []
                    tc_infos = []
                    for tc in tool_calls:
                        if "type" not in tc and "function" in tc:
                            tc["type"] = "function"
                        fn = tc.get("function", {})
                        name = fn.get("name", "unknown")
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                        except json.JSONDecodeError:
                            args = {}
                            yield await send("token", content=f"\n⚠️ 工具 {name} 参数格式错误，已用空参数继续执行\n")
                        tc_infos.append((tc, name, args_str, args))
                        yield await send("tool_call", tool=name, args=args_str[:300])
    
                    # 智能并行：读操作全部并行，写操作按目标文件分组（同文件串行，不同文件并行）
                    WRITE_TOOLS = {"write_file", "edit_file", "delete_file", "rename_file"}
                    read_tcs = [(tc, n, a_s, a) for tc, n, a_s, a in tc_infos if n not in WRITE_TOOLS]
    
                    # 写操作按文件分组
                    from collections import defaultdict
                    write_groups = defaultdict(list)
                    for tc, n, a_s, a in tc_infos:
                        if n in WRITE_TOOLS:
                            fpath = a.get("file_path", a.get("path", ""))
                            write_groups[fpath].append((tc, n, a_s, a))
    
                    async def _run_one(tc, name, args_str, args):
                        try:
                            if is_mcp_tool(name):
                                r = await call_mcp_tool(name, args)
                            else:
                                r = await execute_tool(name, args)
                            if isinstance(r, str) and r.startswith("__CONFIRM_"):
                                return (name, "__CONFIRM_" + str(args.get("command", "")[:200]), True)
                        except Exception as e:
                            return (name, f"错误: {e}", False)
                        return (name, str(r), False)
    
                    if read_tcs:
                        read_tasks = [_run_one(tc, n, a_s, a) for tc, n, a_s, a in read_tcs]
                        read_results = await asyncio.gather(*read_tasks)
                        for name, result, needs_confirm in read_results:
                            if needs_confirm:
                                confirm_id = f"confirm_{conv_id}_{round_i}_{name}"
                                yield await send("confirm_required", confirm_id=confirm_id, tool=name, command=result[len("__CONFIRM_"):])
                                confirmed = await _wait_confirmation(confirm_id, timeout=30)
                                if confirmed:
                                    args_d = next((a for tc, n, _as, a in tc_infos if n == name), {})
                                    args_d["__confirmed"] = True
                                    result = await execute_tool(name, args_d)
                                else:
                                    result = "用户取消了此高风险操作"
                            yield await send("tool_result", tool=name, result=str(result))
                            round_results.append(str(result))
    
                    # 写操作：不同文件并行，同文件串行
                    async def _run_write_group(items):
                        for tc, name, args_str, args in items:
                            result = await execute_tool(name, args)
                            if isinstance(result, str) and result.startswith("__CONFIRM_"):
                                confirm_id = f"confirm_{conv_id}_{round_i}_{name}"
                                yield await send("confirm_required", confirm_id=confirm_id, tool=name, command=result[len("__CONFIRM_"):])
                                confirmed = await _wait_confirmation(confirm_id, timeout=30)
                                if confirmed:
                                    args["__confirmed"] = True
                                    result = await execute_tool(name, args)
                                else:
                                    result = "用户取消了此高风险操作"
                            yield await send("tool_result", tool=name, result=str(result))
                            round_results.append(str(result))
    
                    if write_groups:
                        write_coros = []
                        async def _run_group(items):
                            results = []
                            for tc, name, args_str, args in items:
                                r = await execute_tool(name, args)
                                if isinstance(r, str) and r.startswith("__CONFIRM_"):
                                    results.append((name, f"⚠️ 高风险操作需要确认: {r.split(chr(10))[1] if chr(10) in r else r[11:100]}"))
                                else:
                                    results.append((name, str(r)))
                            return results
                        for items in write_groups.values():
                            write_coros.append(_run_group(items))
                        write_results = await asyncio.gather(*write_coros)
                        for group_results in write_results:
                            for name, result in group_results:
                                yield await send("tool_result", tool=name, result=str(result))
                                round_results.append(str(result))
    
                    # 记录所有工具调用结果
                    for idx, (tc, name, args_str, args) in enumerate(tc_infos):
                        result_for_log = round_results[idx] if idx < len(round_results) else "未执行"
                        all_tool_calls.append({"tool": name, "args": args, "ok": not str(result_for_log).startswith("错误"), "result": str(result_for_log)[:50000], "round_text": round_text})
    
                    # 把本轮的 assistant + tool 消息追加到列表
                    assistant_msg = {
                        "role": "assistant",
                        "content": resp.get("content") or None,
                        "tool_calls": [tc_info[0] for tc_info in tc_infos]
                    }
                    if reasoning:
                        assistant_msg["reasoning_content"] = reasoning
                        all_reasoning.append(reasoning)
                    messages.append(assistant_msg)
                    for idx2, (tc, name, _args_str, _args) in enumerate(tc_infos):
                        result_for_llm = round_results[idx2] if idx2 < len(round_results) else "未执行"
                        tc_id = tc.get("id") or f"call_{name}_{round_i}"
                        tc["id"] = tc_id
                        messages.append({"role": "tool", "tool_call_id": tc_id, "content": str(result_for_llm)})
                    # 自适应探索追踪
                    for idx, (_, name, _, args) in enumerate(tc_infos):
                        if name == "project_index" and idx < len(round_results):
                            fc = _parse_file_count(str(round_results[idx]))
                            if fc > 0 and fc != _project_file_count: _project_file_count = fc; _update_exploration_budget(fc)
                        if name in ("read_file","list_files","search_content") and idx < len(round_results):
                            fp = ""
                            if name == "read_file": fp = args.get("path") or args.get("file_path",""); 
                            elif name == "list_files": fp = args.get("path","")
                            if fp: _explored_files.add(fp)
                    round_has_action = any(n in ACTION_TOOLS for _, n, _, _ in tc_infos)
                    _consecutive_no_action = 0 if round_has_action else _consecutive_no_action + 1
                    # Phase 追踪

                    # 任务计数（用于探索引导，不做 Phase 决策）
                    for idx, (_, name, _, args) in enumerate(tc_infos):
                        if name == "task_create": _pending_tasks += 1
                        if name == "task_update" and idx < len(round_results):
                            r = str(round_results[idx]).lower()
                            if any(w in r for w in ("completed","完成","已完成")): _completed_tasks += 1; _pending_tasks = max(0, _pending_tasks - 1)
                    # Claude Code 风格：持久化 todo 文件
                    if workspace:
                        todo_path = Path(workspace) / ".maona" / f"todo_{conv_id}.md"
                        todo_lines = []
                        for idx, (_, name, _, args) in enumerate(tc_infos):
                            if name == "task_create":
                                subj = args.get("subject") or args.get("description", "任务")[:80]
                                todo_lines.append(f"- [ ] {subj}")
                            elif name == "task_update" and idx < len(round_results):
                                r = str(round_results[idx]).lower()
                                if any(w in r for w in ("completed","完成","已完成")):
                                    subj = args.get("subject") or args.get("description", "任务")[:80]
                                    todo_lines.append(f"- [x] {subj}")
                        if todo_lines:
                            try:
                                todo_path.parent.mkdir(parents=True, exist_ok=True)
                                existing = todo_path.read_text(encoding="utf-8") if todo_path.exists() else ""
                                existing_lines = existing.strip().split("\n") if existing.strip() else []
                                # 合并：更新已有条目或追加
                                new_todos = {}
                                for line in existing_lines + todo_lines:
                                    if line.startswith("- ["):
                                        is_done = "[x]" in line[:6]
                                        text = line[6:].strip() if len(line) > 6 else line
                                        new_todos[text] = is_done
                                final_lines = [f"- [{'x' if done else ' '}] {text}" for text, done in new_todos.items()]
                                todo_path.write_text("\n".join(final_lines), encoding="utf-8")
                            except Exception: pass
                    # 验证结果注入：validate_gdscript/check_godot_project 有错误时，把报错原文喂给 Agent
                    for idx, (_, name, _, args) in enumerate(tc_infos):
                        if name in ("validate_gdscript", "check_godot_project") and idx < len(round_results):
                            result = str(round_results[idx])
                            if "🔴" in result or "ERROR" in result.upper() or "错误" in result:
                                messages.append({"role": "user", "content": f"[验证结果] {name} 发现错误，请修复后重新验证：\n{result[:2000]}"})
                    # 子 Agent 上下文隔离
                    for idx2, (tc, name, _args_str, _args) in enumerate(tc_infos):
                        if name == "sub_task":
                            raw = str(round_results[idx2] if idx2 < len(round_results) else "")
                            if len(raw) > 3000:
                                import re as _re2
                                paths = _re2.findall(r'(?:创建|修改|写入|读取)[：:]\\s*([^\\n]+)', raw)
                                errors = _re2.findall(r'(?:错误|ERROR|失败|FAILED)[：:\\s]*([^\\n]{10,200})', raw)
                                sp = [f"[子 Agent 结果已压缩 · 原文 {len(raw)} 字符]"]
                                if paths: sp.append(f"涉及文件: {', '.join(paths[:8])}")
                                if errors: sp.append(f"关键问题: {'; '.join(errors[:3])}")
                                result_for_llm = raw[:500] + "\\n..." + "\\n".join(sp) + "\\n..." + raw[-200:]
                                tc_id2 = tc.get("id") or f"call_{name}_{round_i}"; tc["id"] = tc_id2
                                messages[-1]["content"] = result_for_llm if messages and messages[-1].get("role") == "tool" else str(result_for_llm)
                    # Code 分析：写前必读
                    blind_edits = []
                    for idx, (_, name, _args_str, args) in enumerate(tc_infos):
                        if name == "edit_file":
                            fp = args.get("file_path", args.get("path", ""))
                            fpn = fp.replace("\\", "/").lower(); en = {p.replace("\\", "/").lower() for p in _explored_files if p}
                            if fpn and fpn not in en: blind_edits.append(fp)
                    if blind_edits:
                        bf = "\\n".join(f"  - {f}" for f in blind_edits[:5])
                        messages.append({"role": "user", "content": f"[Code 分析] edit_file 目标不在最近读取列表中：\\n{bf}\\n建议先用 read_file 了解内容。"})
                        _runtime_diag.setdefault("code_analysis", []).append({"round": round_i+1, "type": "blind_edit", "files": blind_edits[:5]})
                    # Code 分析：依赖检查
                    wfiles = [args.get("file_path", args.get("path","")) for _, name, _, args in tc_infos if name == "write_file" and args.get("file_path", args.get("path",""))]
                    if wfiles and len(wfiles) <= 3:
                        refs = set()
                        for m in messages[-20:]:
                            c = str(m.get("content",""))[:5000]
                            for wf in wfiles:
                                wn = wf.replace("\\","/").split("/")[-1].replace(".gd","").replace(".py","")
                                if wn and len(wn) > 2 and wn in c: refs.add(wf)
                        if refs:
                            rl = "\\n".join(f"  - {f}" for f in refs)
                            messages.append({"role": "user", "content": f"[Code 分析] 写入文件被引用，建议验证依赖：\\n{rl}"})
                            _runtime_diag.setdefault("code_analysis", []).append({"round": round_i+1, "type": "dependency_check", "written": wfiles, "referenced_in": list(refs)})

                    # 自适应探索预算注入
                    _budget = _exploration_budget
                    if _consecutive_no_action >= int(_exploration_budget * 0.8):
                        pt = f"，{_pending_tasks} 个任务待执行" if _pending_tasks > 0 else ""
                        messages.append({"role": "user", "content": f"已 {_consecutive_no_action} 轮无产出{pt}，信息应该够了。"})
                    # 渐进式规则注入
                    if round_i in (5, 10, 15, 25, 40, 60) and round_i > _last_checkpoint_round:
                        _last_checkpoint_round = round_i
                        pi = f"待完成: {_pending_tasks}。" if _pending_tasks > 0 else (f"已完成: {_completed_tasks}。" if _completed_tasks > 0 else "")
                        messages.append({"role": "user", "content": f"[进度检查 · 第 {round_i} 轮] {pi}① 信任工具结果 ② validate_gdscript ③ MCP降级 ④ 够了就动手。"})
                        _runtime_diag.setdefault("injections", []).append({"round": round_i+1, "type": "checkpoint_reminder"})
    
                    # 反思纠错：任一工具失败时，自动提示重试（含具体错误信息）
                    failures = [(tc_infos[i][0].get("function", {}).get("name", "?"), round_results[i])
                               for i in range(len(round_results)) if str(round_results[i]).startswith("错误")]
                    all_ok = len(failures) == 0
                    if not all_ok and retry_count < MAX_RETRIES:
                        retry_count += 1
                        err_msgs = "; ".join(f"{n}: {str(r)[:80]}" for n, r in failures[:3])
                        messages.append({"role": "user", "content": f"[系统] {len(failures)} 个工具失败: {err_msgs}。请修正参数或重试。（自动重试 {retry_count}/{MAX_RETRIES}）"})
                        continue
    
                    # 每轮后更新上下文用量（实时展示）
                    est_tokens = estimate_tokens(messages)
                    model_budget = _model_context_window or 128000
                    pct = min(100, int(est_tokens / model_budget * 100)) if model_budget else 0
                    yield await send("context", tokens=est_tokens, budget=model_budget, pct=pct, context_window=_model_context_window, model=model)

                    # 预算上限检查
                    budget_cap = ms.get("budget_cap", 500000)
                    total_session_tokens = sum(getattr(getattr(m, "usage", {}), "total_tokens", 0) for m in messages if hasattr(m, "usage"))
                    if total_session_tokens > budget_cap:
                        yield await send("error", content=f"已达到对话 Token 预算上限 ({budget_cap:,})，请简化任务或开启新对话。")
                        break
    
                    # Phase 模型已移除，Agent 通过对话历史自主判断当前阶段    
                    # === 4级压缩流水线 ===
                    if round_i >= 3 and round_i % 4 == 0:
                        est = estimate_tokens(messages)
                        sys_prompt_len = len(str(messages[0].get("content", ""))) if messages else 0
                        est += sys_prompt_len // 2
                        if est > model_budget * get_compress_threshold(model_budget):
                            # Tier 1: 裁剪大工具输出
                            for m in messages[1:]:
                                if m.get("role") == "tool":
                                    c = str(m.get("content", ""))
                                    if len(c) > 4000:
                                        m["content"] = c[:2000] + f"\\n...[已截断 {len(c)-2500} 字符]...\\n" + c[-500:]
                            est = estimate_tokens(messages) + sys_prompt_len // 2
                            if est <= model_budget * get_compress_threshold(model_budget): print(f"[Maona] Tier1 裁剪后上下文恢复"); continue
                            # Tier 2-4: Claude Code 风格 — 按 token 保留能塞进预算的消息
                            system_msg = messages[0]
                            keep, keep_tk = [], 0
                            budget_target_2 = int(model_budget * get_compress_threshold(model_budget) * 0.85)
                            for m in reversed(messages[1:]):
                                t = estimate_tokens([m])
                                if keep_tk + t > budget_target_2 and keep:
                                    break
                                keep.insert(0, m)
                                keep_tk += t
                            recent_msgs = keep
                            old_msgs = [m for m in messages[1:] if m not in recent_msgs]
                            tool_results_to_keep = []
                            for m in old_msgs:
                                if m.get("role") == "tool" and m.get("content") and len(str(m.get("content",""))) < 8000:
                                    tool_results_to_keep.append(m)
                            summary = await summarize_conversation(provider, old_msgs, project)
                            if summary:
                                recovery = (f"## 恢复上下文\\n"
                                           f"- {_project_file_count}文件 | {len(all_tool_calls)}工具调用")
                                sc = system_msg.get("content") or ""
                                if "## 对话摘要" in sc: sc = sc.split("## 对话摘要\\n")[0].strip()
                                system_msg["content"] = sc + "\\n\\n## 对话摘要\\n" + summary + "\\n\\n" + recovery
                                messages = [system_msg] + tool_results_to_keep + recent_msgs
                                _runtime_diag.setdefault("compressions", []).append({"round": round_i+1, "tier": 4, "before_tokens": est, "after_tokens": estimate_tokens(messages)})
                            else:
                                messages = [system_msg] + tool_results_to_keep + recent_msgs
                    # 每轮后保存检查点（工作空间 + 任务模式）
                    if all_tool_calls:
                        try:
                            if workspace: ckpt_dir = Path(workspace) / ".maona"
                            else: ckpt_dir = Path.home() / ".agent_maona" / "checkpoints"
                            ckpt_dir.mkdir(parents=True, exist_ok=True)
                            ckpt = {"round": round_i + 1, "tools_done": len(all_tool_calls), "tools": all_tool_calls[-5:], "conv_id": conv_id, "project_file_count": _project_file_count, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
                            ckpt_file = ckpt_dir / ("checkpoint.json" if workspace else f"{conv_id}.json")
                            ckpt_file.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2))
                        except: pass
                    continue  # 回到 for 循环，让模型基于结果决定下一步
                else:
                    # 无工具调用 → LLM 给出最终回复
                    final_text = resp.get("content") or ""
                    if not final_text and reasoning:
                        final_text = reasoning[:1000]  # 纯推理回复
                    break  # 退出 for 循环

            # 持久循环：检查 Agent 是否应该自动续接
            task_complete = bool(final_text) and not resp.get("tool_calls")
            if not task_complete:
                # for 循环耗尽（达到 MAX_TOOL_ROUNDS）→ 任务被截断
                final_text = f"[任务已达 {MAX_TOOL_ROUNDS} 轮上限，被截断。已完成 {len(all_tool_calls)} 个工具调用。请在新对话中继续或要求我继续未完成的部分。]"
                break  # 退出 while 循环
            # 任务已完成，检查是否需要自动续接
            if auto_continue_round + 1 < MAX_AUTO_CONTINUES and all_tool_calls and final_text:
                _completion_exits += 1
                if _completion_exits >= 3:
                    break  # 断路器：连续3次完成文本 → 强制停止
                asking_user = final_text.strip().endswith("？") or "?" in final_text.strip()[-50:] or "需要我" in final_text[-200:] or "需要帮你" in final_text[-200:]
                # 检测「任务明确完成」的结束标志
                task_done = any(h in final_text for h in (
                    "全部完成", "已全部", "任务完成", "✅", "无需重复执行",
                    "已完成工作", "以上就是", "总结如下", "确认完成", "已完整",
                    "已创建完成", "已完成创建", "整理完毕", "收工",
                ))
                if task_done:
                    break  # 任务明确完成，不续接
                # 检测「需要继续」的触发信号
                wants_continue = any(h in final_text for h in (
                    "继续完成", "继续构建", "继续开发", "继续添加", "继续完善",
                    "接着做", "还没做完", "未完成", "换个方向",
                ))
                if wants_continue and not asking_user:
                    auto_continue_round += 1
                    yield await send("auto_continue", round=auto_continue_round, total=MAX_AUTO_CONTINUES)
                    messages.append({"role": "assistant", "content": final_text[:500]})
                    final_text = ""
                    py_created = any("write_file" in str(tc) and ".py" in str(tc) for tc in all_tool_calls[-3:])
                    hint = f"[系统自动续接 {auto_continue_round}/{MAX_AUTO_CONTINUES}] 继续执行未完成的任务。"
                    if py_created:
                        hint += " 如果创建了Python文件，请用 run_check 验证语法完整性。"
                    messages.append({"role": "user", "content": hint})
                    continue  # 回到 while 循环
            break  # 正常退出 while 循环

        # 立即保存：即使流被中断，数据已入库，重进对话可见
        if final_text and not final_text.startswith("[任务已达"):
            try:
                await save_message(conv_id, "assistant", final_text,
                    reasoning_content=("\x00".join(all_reasoning) if all_reasoning else final_reasoning),
                    tool_calls=all_tool_calls if all_tool_calls else None)
                _message_saved = True
            except Exception: pass
        elif final_reasoning and not final_text:
            try:
                await save_message(conv_id, "assistant", final_reasoning[:500],
                    reasoning_content=final_reasoning)
                _message_saved = True
            except Exception: pass
            yield await send("round_limit", rounds=MAX_TOOL_ROUNDS, tools_done=len(all_tool_calls))

        # === 最终回复：模拟流式（从 chat_non_stream 结果按小粒度发送）===
        if final_text:
            # 按 4 字符粒度分批，前端增量渲染，体验接近真流式
            for i in range(0, len(final_text), 4):
                yield await send("token", content=final_text[i:i+4])
                await asyncio.sleep(0.02)  # 微延迟，让前端有时间渲染

        messages.append({"role": "assistant", "content": final_text})

        # 自动生成标题（仅首次，直接用第一句话截取，省一次 API 调用）
        try:
            existing = await get_conversation(conv_id)
            if existing and (existing.get("title") or "").startswith("新对话"):
                user_msgs_for_title = [m for m in request.messages if m.role == "user"]
                if user_msgs_for_title:
                    first = user_msgs_for_title[0]["content"].strip()
                    # 取前 15 个中文字符或前 30 个 ASCII 字符作为标题
                    title = ""
                    count = 0
                    for ch in first:
                        title += ch
                        count += 2 if ord(ch) > 127 else 1
                        if count >= 30:
                            break
                    title = title.strip().replace("\n", " ")[:20]
                    if title:
                        await update_title(conv_id, title)
        except Exception:
            pass

        # 上下文用量统计
        total_chars = sum(len(str(m.get("content", ""))) for m in messages if m.get("content"))
        est_tokens = total_chars // 2  # 粗略估计：平均 2 字符 ≈ 1 token
        pct = min(100, int(est_tokens / model_budget * 100)) if model_budget else 0
        yield await send("context", tokens=est_tokens, budget=model_budget, pct=pct)

        # 先通知前端完成（解除输入框锁定）
        yield await send("done")

        # 结构化记忆摘要（琐碎对话跳过）
        if not has_error:
            user_total_len = sum(len(_text_content(m)) for m in request.messages if m.role == "user")
            has_tools = len(all_tool_calls) > 0
            # 跳过：用户输入 < 50 字 且 AI 回复 < 200 字 且 无工具调用
            is_trivial = (user_total_len < 50 and (not final_text or len(final_text) < 200) and not has_tools)
            if not is_trivial:
                try:
                    summary = await summarize_conversation(provider, messages, project)
                    append_daily(project, summary, workspace=workspace)
                except Exception:
                    user_msg = next((m.content for m in request.messages if m.role == "user"), "")
                    if user_total_len >= 50 or has_tools:
                        append_daily(project, f"## 对话\n- 用户: {user_msg[:200]}\n- 回复: {final_text[:200]}", workspace=workspace)

        # 自动更新用户画像（Cloud Memory 本地等效）
        if not has_error:
            try:
                from memory.profile import update_profile
                rich_msgs = []
                for m in messages:
                    mc = m.get("content", "")
                    if isinstance(mc, list):
                        mc = json.dumps([x.get("text","") for x in mc if x.get("type")=="text"])
                    rich_msgs.append({"role": m.get("role",""), "content": mc[:200], "tool_calls": m.get("tool_calls")})
                await update_profile(project, workspace or "", rich_msgs)
            except Exception:
                pass

        # 自动技能积累：8+ 工具调用的复杂任务自动保存为技能
        if not has_error and len(all_tool_calls) >= 8:
            try:
                import re
                user_req = next((_text_content(m)[:80] for m in request.messages if m.role == "user"), "任务")
                safe_name = re.sub(r'[^a-zA-Z\u4e00-\u9fff0-9]', '-', user_req[:30].strip()).strip('-').lower()
                if not safe_name:
                    safe_name = f"task-{len(all_tool_calls)}steps"
                skill_prompt = f"原始需求: {user_req}\n\n执行步骤 ({len(all_tool_calls)} 步):\n"
                for i, tc in enumerate(all_tool_calls):
                    skill_prompt += f"{i+1}. {tc['tool']}({json.dumps(tc['args'], ensure_ascii=False)[:100]})\n"
                from tools.creative import skill_auto_save
                skill_auto_save(name=f"auto-{safe_name}", prompt_template=skill_prompt,
                               trigger=f"用户要求: {user_req[:50]}")
            except Exception:
                pass
        return

    except Exception as e:
        # 中断时保存部分进度（仅当正常流程未保存时）
        try:
            if all_tool_calls and not _message_saved:
                partial_text = final_text or f"[已中断，完成 {len(all_tool_calls)} 个工具调用]"
                # 清理流式输出残留（"▶ 深度思考"、"深度思考中..." 等）
                import re
                partial_text = re.sub(r'[▶▷]\s*深度思考[中]*\.{0,3}', '', partial_text)
                partial_text = re.sub(r'深度思考[中]*\.{0,3}', '', partial_text)
                partial_text = partial_text.strip()
                if not partial_text:
                    partial_text = f"[已中断，完成 {len(all_tool_calls)} 个工具调用]"
                await save_message(
                    conv_id, "assistant", partial_text,
                    reasoning_content=("\x00".join(all_reasoning) if all_reasoning else None),
                    tool_calls=all_tool_calls
                )
        except Exception:
            pass
        yield await send("error", content=str(e))

    yield await send("done")


async def _sse_wrap(generator):
    """将 JSON 字符串生成器包装为 SSE 流，带错误捕获"""
    try:
        async for data in generator:
            yield f"data: {data}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

@router.post("/stream")
async def chat_stream(request: ChatRequest, req: Request = None):
    if not await _check_rate_limit(req.client.host if req else "local"):
        return StreamingResponse(_rate_limit_response(), media_type="text/event-stream")
    return StreamingResponse(_sse_wrap(stream_chat(request)), media_type="text/event-stream")


async def _rate_limit_response():
    yield f"data: {json.dumps({'type': 'error', 'content': '请求太频繁，请稍后再试'})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/confirm")
async def confirm_tool(data: dict):
    """用户确认/拒绝高风险工具调用"""
    cid = data.get("confirm_id", "")
    ok = data.get("confirmed", False)
    future = _pending_confirms.get(cid)
    if future and not future.done():
        future.set_result(ok)
        return {"status": "ok"}
    return {"status": "expired"}


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/providers/available")
async def available_providers():
    """获取可用的 Provider 和模型列表（供前端模型选择器使用）"""
    return {"providers": pm.list_available()}


@router.get("/conversations")
async def get_conversations(project_id: str = "agent_maona", limit: int = 5, offset: int = 0):
    await ensure_project(project_id)
    convs = await list_conversations(project_id)
    total = len(convs)
    convs = convs[offset:offset + limit]
    return {"conversations": convs, "total": total, "has_more": offset + limit < total}


@router.post("/conversations")
async def new_conversation(project_id: str = "agent_maona", title: str = "新对话"):
    await ensure_project(project_id)
    conv_id = await create_conversation(project_id, title)
    return {"id": conv_id, "title": title}


@router.get("/conversations/{conversation_id}")
async def get_conv(conversation_id: str):
    conv = await get_conversation(conversation_id)
    if not conv:
        return {"error": "对话不存在"}, 404
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conv(conversation_id: str):
    _conv_prompt_cache.pop(conversation_id, None)  # 清除缓存
    try:
        await delete_conversation(conversation_id)
    except Exception as e:
        # 彻底兜底：直接操作数据库
        try:
            from memory.conversations import _get_db
            db = await _get_db()
            await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            await db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            await db.commit()
            await db.close()
        except Exception:
            pass
        print(f"[chat] delete error (recovered): {e}")
    return {"status": "ok"}


@router.patch("/conversations/{conversation_id}")
async def rename_conv(conversation_id: str, title: str = ""):
    """重命名对话"""
    await update_title(conversation_id, title)
    return {"status": "ok"}


@router.get("/memory/context")
async def get_memory_context(project: str = "agent_maona", workspace: str = None):
    return {
        "project": project,
        "context": build_context(project, workspace),
        "recent": get_recent_context(project, 3, workspace),
    }


@router.get("/conversations/search")
async def search_conversations(q: str = "", project_id: str = "agent_maona"):
    """搜索对话标题和内容"""
    await ensure_project(project_id)
    return {"results": await search_conversation_messages(project_id, q)}


# ===== 统一技能系统 API =====

@router.get("/skills")
async def list_skills():
    """获取已安装技能"""
    from skills import scan_skills
    return {"skills": scan_skills()}


@router.get("/skills/market")
async def list_market():
    """获取技能市场（未安装的可安装技能）"""
    from skills import get_market_skills
    return {"skills": get_market_skills()}


@router.post("/skills/{skill_id}/install")
async def install_skill_endpoint(skill_id: str):
    """从市场安装技能"""
    from skills import install_skill
    ok = install_skill(skill_id)
    return {"success": ok}


@router.post("/skills/{skill_id}/uninstall")
async def uninstall_skill_endpoint(skill_id: str):
    """卸载技能"""
    from skills import uninstall_skill
    ok = uninstall_skill(skill_id)
    return {"success": ok}


@router.post("/skills/{skill_id}/toggle")
async def toggle_skill_endpoint(request: Request, skill_id: str):
    """切换技能启用状态"""
    enabled = False
    try:
        body = await request.json()
        enabled = body.get("enabled", False)
    except:
        pass
    from skills import toggle_skill
    toggle_skill(skill_id, enabled)
    return {"success": True}


@router.post("/skills/suite/{suite_id}/toggle")
async def toggle_suite_endpoint(request: Request, suite_id: str):
    """批量切换套件下所有技能"""
    enabled = False
    try:
        body = await request.json()
        enabled = body.get("enabled", False)
    except:
        pass
    from skills import toggle_suite
    count = toggle_suite(suite_id, enabled)
    return {"success": True, "count": count}


# ===== 工具管理 API =====

_tool_state = {}  # 工具启用状态缓存 {name: {"enabled": bool}}

def _tool_state_path():
    """工具状态文件：存放在项目根目录下的 data/ 目录"""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "data" / "tool_state.json"
    return p

def _load_tool_state():
    import json
    p = _tool_state_path()
    if p.exists():
        try:
            global _tool_state
            _tool_state = json.loads(p.read_text(encoding="utf-8"))
        except:
            pass

def _save_tool_state():
    import json
    p = _tool_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_tool_state, ensure_ascii=False, indent=2), encoding="utf-8")

def get_enabled_tools(mode="craft"):
    """返回启用的工具定义，根据模式过滤。switch_mode 和 load_skill 始终可用。"""
    _load_tool_state()
    all_tools = [t for t in TOOLS if _tool_state.get(t["function"]["name"], {}).get("enabled", True)]
    
    # MCP Godot 工具（启动时已连接，直接获取）
    for name in get_mcp_tool_names():
        if not any(t["function"]["name"] == name for t in all_tools):
            tdef = get_mcp_tool_def(name)
            if tdef:
                all_tools.append(tdef)
    
    ALWAYS_AVAILABLE = {"switch_mode", "load_skill"}
    
    if mode == "ask":
        SAFE_READ = {
            "read_file", "list_files", "search_content", "web_search", "web_fetch",
            "git_diff", "git_log", "pdf_read", "read_csv", "system_info", "image_info",
            "count_tokens", "read_docx", "read_pptx", "read_xlsx", "load_skill", "read_memory"
        }
        return [t for t in all_tools if t["function"]["name"] in SAFE_READ or t["function"]["name"] in ALWAYS_AVAILABLE]
    
    if mode == "plan":
        # Plan 模式：只读 + 规划工具，不允许修改文件
        PLAN_TOOLS = {
            "read_file", "list_files", "search_content", "web_search", "web_fetch",
            "git_diff", "git_log", "pdf_read", "read_csv", "system_info", "image_info",
            "count_tokens", "read_docx", "read_pptx", "read_xlsx", "load_skill", "read_memory",
            "project_index", "code_search", "find_skills", "rag_search", "kb_search",
            "task_create", "switch_mode", "cache_env", "search_conversations",
        }
        return [t for t in all_tools if t["function"]["name"] in PLAN_TOOLS or t["function"]["name"] in ALWAYS_AVAILABLE]
    
    return all_tools

# 分类信息
TOOL_CATEGORIES = {
    "文件操作": ["read_file", "write_file", "edit_file", "list_files", "search_content", "rename_file", "delete_file"],
    "终端与代码": ["run_command", "run_python", "install_pip"],
    "网络": ["web_search", "web_fetch", "api_post", "download_file"],
    "数据": ["read_csv", "read_docx", "read_pptx", "read_xlsx", "pdf_read", "sql_query"],
    "系统": ["system_info", "screenshot", "image_info", "compress_image", "open_browser", "clipboard", "notify"],
    "Git": ["git_diff", "git_log"],
    "工具": ["html_preview", "zip_archive", "encode_decode", "text_to_speech", "count_tokens"],
    "记忆": ["save_memory", "read_memory", "save_daily_log"],
    "技能": ["load_skill"],
    "模式": ["switch_mode"],
    "Godot": list(get_mcp_tool_names()),
    "任务": ["task_create", "task_update", "task_list", "restore_backup", "git_snapshot", "project_index"],
    "预览": ["html_preview", "live_preview"],
    "并行": ["sub_task", "code_search"],
    "RAG": ["rag_build", "rag_search"],
    "质量": ["run_test", "run_check", "profile"],
    "知识库": ["kb_create", "kb_add_url", "kb_add", "kb_search"],
    "技能管理": ["skill_create", "skill_update", "skill_delete", "load_skill"],
}

TOOL_LABELS = {
    "read_file": "读取文件", "write_file": "写入文件", "edit_file": "编辑文件",
    "list_files": "列出目录", "search_content": "搜索内容", "rename_file": "重命名", "delete_file": "删除文件",
    "run_command": "执行命令", "run_python": "运行Python", "install_pip": "安装包",
    "web_search": "搜索网页", "web_fetch": "抓取网页", "api_post": "API请求", "download_file": "下载文件",
    "read_csv": "读取CSV", "read_docx": "读取Word", "read_pptx": "读取PPT", "read_xlsx": "读取Excel",
    "pdf_read": "读取PDF", "sql_query": "SQL查询",
    "system_info": "系统信息", "screenshot": "截图", "image_info": "图片信息",
    "compress_image": "压缩图片", "open_browser": "打开浏览器", "clipboard": "剪贴板", "notify": "通知",
    "git_diff": "查看变更", "git_log": "提交历史",
    "html_preview": "HTML预览", "zip_archive": "压缩解压", "encode_decode": "编解码",
    "text_to_speech": "语音朗读", "count_tokens": "Token计算",
    "save_memory": "保存记忆", "read_memory": "读取记忆", "save_daily_log": "保存日志",
    "load_skill": "加载技能",
    "switch_mode": "切换模式",
    "task_create": "创建任务",
    "task_update": "更新任务",
    "task_list": "列出任务",
    "restore_backup": "恢复备份",
    "git_snapshot": "Git 提交",
    "project_index": "项目索引",
    "live_preview": "实时预览",
    "sub_task": "子任务",
    "code_search": "代码搜索",
    "skill_create": "创建技能",
    "skill_update": "修改技能",
    "skill_delete": "删除技能",
    "rag_build": "构建索引",
    "rag_search": "语义搜索",
    "run_test": "运行测试",
    "run_check": "代码检查",
    "profile": "性能分析",
    "kb_create": "创建知识库",
    "kb_add_url": "抓取网页",
    "kb_add": "添加文档",
    "kb_search": "搜索知识库",
}

TOOL_ICONS = {
    "read_file": "", "write_file": "", "edit_file": "", "list_files": "",
    "search_content": "", "rename_file": "", "delete_file": "",
    "run_command": "", "run_python": "", "install_pip": "",
    "web_search": "", "web_fetch": "", "api_post": "", "download_file": "",
    "read_csv": "", "read_docx": "", "read_pptx": "", "read_xlsx": "",
    "pdf_read": "", "sql_query": "",
    "system_info": "", "screenshot": "", "image_info": "",
    "compress_image": "", "open_browser": "", "clipboard": "", "notify": "",
    "git_diff": "", "git_log": "",
    "html_preview": "", "zip_archive": "", "encode_decode": "",
    "text_to_speech": "", "count_tokens": "",
    "save_memory": "", "read_memory": "", "save_daily_log": "",
    "load_skill": "",
    "switch_mode": "",
    "task_create": "",
    "task_update": "",
    "task_list": "",
    "restore_backup": "",
    "git_snapshot": "",
    "project_index": "",
    "live_preview": "",
    "sub_task": "",
    "code_search": "",
    "skill_create": "",
    "skill_update": "",
    "skill_delete": "",
    "rag_build": "",
    "rag_search": "",
    "run_test": "",
    "run_check": "",
    "profile": "",
    "kb_create": "",
    "kb_add_url": "",
    "kb_add": "",
    "kb_search": "",
}


# ===== 对话恢复 =====
@router.get("/checkpoint")
async def get_checkpoint(workspace: str = "", conv_id: str = ""):
    """获取工作空间的检查点状态，用于判断是否有未完成的复杂任务"""
    result = {"has_checkpoint": False, "round": 0, "tools_done": 0, "summary": ""}
    if not workspace:
        return result

    try:
        ckpt_path = Path(workspace) / ".maona" / "checkpoint.json"
        if not ckpt_path.exists():
            return result

        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        result["has_checkpoint"] = True
        result["round"] = ckpt.get("round", 0)
        result["tools_done"] = ckpt.get("tools_done", 0)
        result["conv_id"] = ckpt.get("conv_id", "")

        # 读取任务列表
        task_path = Path(f"data/tasks/{ckpt.get('conv_id', '')}.json")
        if task_path.exists():
            tasks = json.loads(task_path.read_text(encoding="utf-8"))
            result["tasks"] = tasks
            completed = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("status") == "completed")
            pending = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("status") in ("pending", "in_progress"))
            result["task_summary"] = f"已完成 {completed} 个任务，剩余 {pending} 个"

        # 存入环境缓存，供后续对话使用
        update_env_cache(workspace, conv_id, {
            "checkpoint_round": result["round"],
            "checkpoint_tools": result["tools_done"],
            "has_unfinished_work": result["has_checkpoint"],
        })
    except Exception:
        pass

    return result


@router.post("/resume")
async def resume_conversation(data: dict):
    """在 checkpoint 基础上恢复对话，返回 resume 上下文"""
    workspace = data.get("workspace", "")
    conv_id = data.get("conv_id", "")

    if not workspace:
        return {"resume_available": False, "reason": "无工作空间"}

    try:
        ckpt_path = Path(workspace) / ".maona" / "checkpoint.json"
        if not ckpt_path.exists():
            return {"resume_available": False, "reason": "无检查点文件"}

        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        tasks_path = Path(f"data/tasks/{ckpt.get('conv_id', '')}.json")

        tasks_info = ""
        if tasks_path.exists():
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            task_lines = []
            for tid, t in tasks.items():
                if isinstance(t, dict):
                    status_icon = {"completed": "✅", "in_progress": "🔄", "pending": "⬜"}.get(t.get("status", ""), "⬜")
                    task_lines.append(f"  {status_icon} {t.get('subject', tid)}")
            if task_lines:
                tasks_info = "\n".join(task_lines)

        # 读取最近对话的部分内容作为上下文
        memory_ctx = ""
        if ckpt.get("conv_id"):
            mem_path = Path(workspace) / ".maona" / "MEMORY.md"
            if mem_path.exists():
                memory_ctx = mem_path.read_text(encoding="utf-8")[:2000]

        resume_context = (
            f"\n\n## 🔄 从检查点恢复\n"
            f"上一个对话在第 {ckpt.get('round', '?')} 轮被中断/截断，已完成 {ckpt.get('tools_done', 0)} 个工具调用。\n"
        )
        if tasks_info:
            resume_context += f"\n### 之前的任务状态\n{tasks_info}\n"
        if memory_ctx:
            resume_context += f"\n### 相关工作记忆\n{memory_ctx[:1500]}\n"
        resume_context += (
            f"\n请读取工作空间的 checkpoint.json 和任务列表，理解当前进度后继续完成剩余工作。"
            f"不要重新做已完成的任务（标记为 ✅ 的），专注做未完成的（⬜ 或 🔄）。"
        )

        return {
            "resume_available": True,
            "round": ckpt.get("round", 0),
            "tools_done": ckpt.get("tools_done", 0),
            "context": resume_context,
        }
    except Exception as e:
        return {"resume_available": False, "reason": str(e)}


@router.get("/tools")
async def list_tools():
    """获取所有工具及启用状态"""
    _load_tool_state()
    out = []
    for t in TOOLS:
        name = t["function"]["name"]
        cat = "other"
        for c, names in TOOL_CATEGORIES.items():
            if name in names: cat = c; break
        enabled = _tool_state.get(name, {}).get("enabled", True)
        out.append({
            "name": name,
            "label": name,  # 使用原名，不汉化
            "description": t["function"]["description"],
            "icon": TOOL_ICONS.get(name, ""),
            "category": cat,
            "enabled": enabled,
            "params": json.dumps(t["function"].get("parameters", {}), ensure_ascii=False, indent=2),
        })
    return {"tools": out}


@router.post("/tools/{name}/toggle")
async def toggle_tool(name: str):
    """切换工具启用状态"""
    from fastapi import Request
    # 简单实现：直接反转
    _load_tool_state()
    if name not in _tool_state:
        _tool_state[name] = {}
    _tool_state[name]["enabled"] = not _tool_state[name].get("enabled", True)
    _save_tool_state()
    return {"success": True, "name": name, "enabled": _tool_state[name]["enabled"]}

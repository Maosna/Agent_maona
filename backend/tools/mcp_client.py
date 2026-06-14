"""MCP 客户端 — 通过 stdio 连接 godot-mcp 服务"""
import json
import asyncio
import subprocess
import os
import shutil
from datetime import datetime
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "godot-mcp" / "server"

_mcp_process = None
_mcp_tools = []
_mcp_ready = False
_mcp_starting = False
_mcp_reader = None
_mcp_writer = None
_mcp_error_log = []
_mcp_lock = asyncio.Lock()  # 串行化 stdio 读写
_next_id = 1
_pending = {}


async def ensure_mcp_connected():
    """确保 MCP 已连接（懒加载）。返回 True 表示工具已就绪。"""
    global _mcp_ready, _mcp_starting, _mcp_process, _mcp_tools
    # 健康检查：进程还在吗
    if _mcp_ready and _mcp_process is not None and _mcp_process.returncode is not None:
        # 进程已退出，重置状态
        _mcp_error_log.append(f"进程已退出 (exitcode={_mcp_process.returncode})")
        _mcp_ready = False
        _mcp_tools.clear()
        _mcp_process = None
    if _mcp_ready:
        return True
    if _mcp_starting:
        return False
    _mcp_starting = True
    _mcp_error_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] attempting connection, node={shutil.which('node') or 'not found'}")
    try:
        tools = await start_mcp_server()
        _mcp_starting = False
        return len(tools) > 0
    except Exception as e:
        _mcp_starting = False
        _mcp_error_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] connect failed: {type(e).__name__}: {e}")
        return False


async def _cleanup_mcp_process():
    """安全清理 MCP 子进程，防止僵尸进程泄漏"""
    global _mcp_process, _mcp_ready, _mcp_tools
    if _mcp_process and _mcp_process.returncode is None:
        try:
            _mcp_process.terminate()
            await asyncio.wait_for(_mcp_process.wait(), timeout=3)
        except Exception:
            try:
                _mcp_process.kill()
            except Exception:
                pass
    _mcp_process = None
    _mcp_ready = False
    _mcp_tools = []


async def start_mcp_server():
    """启动 godot-mcp 服务进程"""
    global _mcp_process, _mcp_ready, _mcp_tools

    if _mcp_ready:
        return _mcp_tools

    dist_js = MCP_SERVER_DIR / "dist" / "index.js"
    if not dist_js.exists():
        msg = f"服务文件不存在: {dist_js}"
        print(f"[MCP] {msg}")
        _mcp_error_log.append(msg)
        return []

    # 检测 node 可用性
    node_bin = shutil.which("node") or shutil.which("node.exe")
    if not node_bin:
        msg = "node 不在 PATH 中"
        print(f"[MCP] {msg}")
        for p in [r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe"]:
            if Path(p).exists():
                node_bin = p
                break
    if not node_bin:
        msg = "未找到 Node.js，跳过 MCP 初始化"
        print(f"[MCP] {msg}")
        _mcp_error_log.append(msg)
        return []

    _mcp_error_log.append(f"Node: {node_bin}")
    try:
        # 清除代理变量，避免 VPN 干扰 Node.js 的本地 stdio 通信
        clean_env = {k: v for k, v in os.environ.items()
                     if not k.upper().startswith(("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                                                   "ALL_PROXY", "http_proxy", "https_proxy"))}
        clean_env["MCP_TRANSPORT"] = "stdio"

        _mcp_process = await asyncio.create_subprocess_exec(
            node_bin, str(dist_js),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(MCP_SERVER_DIR),
            env=clean_env,
        )
        # 等待进程启动（最多 3 秒）
        for _ in range(6):
            await asyncio.sleep(0.5)
            if _mcp_process.returncode is not None:
                msg = "进程过早退出"
                print(f"[MCP] {msg}")
                _mcp_error_log.append(msg)
                await _cleanup_mcp_process()
                return []

        # MCP 初始化握手
        await _mcp_send({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "clientInfo": {"name": "Maona", "version": "1.0.0"}
            }
        })
        result = await _mcp_recv(timeout=15)
        if not result:
            msg = "初始化响应超时（15s）"
            print(f"[MCP] {msg}")
            _mcp_error_log.append(msg)
            await _cleanup_mcp_process()
            return []

        _mcp_error_log.append(f"已连接: {result.get('result', {}).get('serverInfo', {}).get('name', 'MCP')}")
        init_caps = json.dumps(result.get("result", {}).get("capabilities", {}))[:300]
        print(f"[MCP] 服务器能力: {init_caps}")
        _mcp_error_log.append(f"caps: {init_caps}")

        # 发送 initialized 通知
        await _mcp_send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        await asyncio.sleep(0.3)  # 短暂等待通知投递

        # 获取工具列表（尝试多种方法名）
        _mcp_tools = []
        for method in ["tools/list", "ToolList", "listTools", "tools/listChanged"]:
            await _mcp_send({"jsonrpc": "2.0", "method": method, "params": {}})
            resp = await _mcp_recv(timeout=3)
            if resp and "result" in resp:
                tools = resp["result"].get("tools", [])
                if tools:
                    _mcp_tools = tools
                    print(f"[MCP] 用 {method} 获取到 {len(tools)} 个工具")
                    break
            if resp:
                print(f"[MCP] {method}: {json.dumps(resp.get('error', resp.get('result', {})))[:200]}")
        if not _mcp_tools:
            # 回退：直接用已知工具名构建
            known = ["create_scene", "create_node", "update_node_property", "delete_node",
                     "save_scene", "open_scene", "get_current_scene", "get_scene_structure",
                     "run_script", "get_script_errors", "get_debug_errors", "get_editor_output"]
            _mcp_tools = [{"name": n, "description": f"Godot MCP tool: {n}"} for n in known]
            print(f"[MCP] 回退：使用 {len(_mcp_tools)} 个已知工具名")
        _mcp_ready = True
        print(f"[MCP] 就绪，共 {len(_mcp_tools)} 个工具")
        return _mcp_tools

    except Exception as e:
        msg = f"启动失败: {e}"
        print(f"[MCP] {msg}")
        _mcp_error_log.append(msg)
        # 读取 Node.js stderr 诊断信息
        try:
            err_data = await asyncio.wait_for(_mcp_process.stderr.read(), timeout=2)
            err_text = err_data.decode('utf-8', errors='replace')[:500]
            print(f"[MCP] Node stderr: {err_text}")
            _mcp_error_log.append(f"stderr: {err_text}")
        except Exception:
            pass
        await _cleanup_mcp_process()
        return []


async def _mcp_send(msg: dict):
    """发送 JSON-RPC 消息"""
    global _next_id, _mcp_process
    if _mcp_process is None or _mcp_process.stdin is None:
        raise RuntimeError("MCP 进程未启动")
    # 清空之前可能残留的响应
    try:
        while True:
            line = await asyncio.wait_for(_mcp_process.stdout.readline(), timeout=0.1)
            if not line: break
    except (asyncio.TimeoutError, Exception):
        pass
    msg.setdefault("id", str(_next_id))
    _next_id += 1
    data = json.dumps(msg, ensure_ascii=False) + "\n"
    _mcp_process.stdin.write(data.encode())
    await _mcp_process.stdin.drain()


async def _mcp_recv(timeout: int = 30) -> dict | None:
    """接收 JSON-RPC 响应（跳过 stdout 中的非 JSON 日志行）"""
    global _mcp_process, _mcp_error_log
    if _mcp_process is None or _mcp_process.stdout is None:
        return None
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            line = await asyncio.wait_for(
                _mcp_process.stdout.readline(),
                timeout=min(remaining, 5)
            )
        except asyncio.TimeoutError:
            continue
        if not line:
            return None
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # 跳过日志行（如 "Starting Godot MCP server..."）
            _mcp_error_log.append(f"stdout log: {text[:100]}")
            # 限制日志行数，防止无限增长
            if len(_mcp_error_log) > 200:
                _mcp_error_log[:] = _mcp_error_log[-100:]
            continue


async def call_mcp_tool(name: str, arguments: dict) -> str:
    """调用 MCP 工具（串行化，连接断开自动重连重试）"""
    global _mcp_ready, _mcp_process, _mcp_tools

    LOST_PATTERNS = ("Connection lost", "BrokenPipe", "ConnectionReset",
                     "ConnectionAborted", "EOF occurred", "OSError",
                     "write to closed", "NoneType.*stdin")

    async with _mcp_lock:
        for attempt in range(3):  # 最多 3 次尝试（含重连）
            # 确保连接就绪
            if not _mcp_ready or _mcp_process is None or _mcp_process.returncode is not None:
                await _ensure_connected_force()

            if not _mcp_ready:
                return "MCP 未连接，请确认 Godot 编辑器已打开并启用 GodotMCP 插件"

            try:
                await _mcp_send({"jsonrpc": "2.0", "method": "tools/call",
                                 "params": {"name": name, "arguments": arguments}})
                resp = await _mcp_recv(timeout=60)

                # 正常的错误响应（不是连接问题）
                if resp and "error" in resp:
                    err = resp["error"].get("message", "未知错误")
                    if any(k in str(err) for k in LOST_PATTERNS):
                        # 连接丢失 → 标记未就绪 → 下一轮重连
                        raise ConnectionError(err)
                    return f"错误: {err}"

                if not resp:
                    # 超时 → 可能进程死了
                    raise ConnectionError("超时")

                result = resp.get("result", {})
                content = result.get("content", [])
                if isinstance(content, list):
                    texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                    return "\n".join(texts) if texts else str(result)
                return str(result) if result else "操作完成"

            except (ConnectionError, BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, OSError) as e:
                _mcp_error_log.append(f"[retry {attempt+1}] 连接丢失: {e}")
                await _cleanup_mcp_process()
                continue  # 重试循环

            except Exception as e:
                err_str = str(e)
                if any(k in err_str for k in LOST_PATTERNS):
                    _mcp_error_log.append(f"[retry {attempt+1}] 异常: {e}")
                    await _cleanup_mcp_process()
                    continue
                return f"错误: MCP 调用异常 — {e}"

    return "MCP 调用失败（已重试 3 次），请检查 Godot 编辑器连接"


async def _ensure_connected_force():
    """强制重连 MCP（使用统一的清理函数）"""
    await _cleanup_mcp_process()
    await ensure_mcp_connected()


def get_mcp_tool_names() -> list[str]:
    """获取 MCP 工具名称列表"""
    return [t["name"] for t in _mcp_tools]


# 完整工具参数 Schema（从 dist/tools/*.js 提取）
_MCP_TOOL_SCHEMAS = {
    "create_node": {
        "type": "object",
        "properties": {
            "parent_path": {"type": "string", "description": "Parent node path (e.g. /root)"},
            "node_type": {"type": "string", "description": "Node type (e.g. Label, Node2D)"},
            "node_name": {"type": "string", "description": "Name for the new node"}
        },
        "required": ["parent_path", "node_type", "node_name"]
    },
    "delete_node": {
        "type": "object",
        "properties": {
            "node_path": {"type": "string", "description": "Path to node to delete (e.g. /root/Player)"}
        },
        "required": ["node_path"]
    },
    "update_node_property": {
        "type": "object",
        "properties": {
            "node_path": {"type": "string", "description": "Path to the node (e.g. /root/Label)"},
            "property": {"type": "string", "description": "Property name (e.g. text, position)"},
            "value": {"description": "New value for the property"}
        },
        "required": ["node_path", "property", "value"]
    },
    "get_node_properties": {
        "type": "object",
        "properties": {
            "node_path": {"type": "string", "description": "Path to node to inspect (e.g. /root/Player)"}
        },
        "required": ["node_path"]
    },
    "list_nodes": {
        "type": "object",
        "properties": {
            "parent_path": {"type": "string", "description": "Path to parent node (e.g. /root)"}
        },
        "required": ["parent_path"]
    },
    "create_scene": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to save scene (e.g. res://scenes/main.tscn)"},
            "root_node_type": {"type": "string", "description": "Root node type (optional, default: Node)"}
        },
        "required": ["path"]
    },
    "save_scene": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Save path (optional, uses current scene path)"}
        },
        "required": []
    },
    "open_scene": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to scene file (e.g. res://scenes/main.tscn)"}
        },
        "required": ["path"]
    },
    "get_current_scene": {
        "type": "object", "properties": {}, "required": []
    },
    "get_project_info": {
        "type": "object", "properties": {}, "required": []
    },
    "create_resource": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "Resource type (e.g. ImageTexture, StyleBoxFlat)"},
            "resource_path": {"type": "string", "description": "Save path (e.g. res://resources/style.tres)"},
            "properties": {"type": "object", "description": "Optional property values"}
        },
        "required": ["resource_type", "resource_path"]
    },
    "create_script": {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Script save path (e.g. res://scripts/player.gd)"},
            "content": {"type": "string", "description": "GDScript content"},
            "node_path": {"type": "string", "description": "Optional node path to attach script to"}
        },
        "required": ["script_path", "content"]
    },
    "edit_script": {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Path to script file (e.g. res://scripts/player.gd)"},
            "content": {"type": "string", "description": "New script content"}
        },
        "required": ["script_path", "content"]
    },
    "get_script": {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Path to script file (e.g. res://scripts/player.gd)"},
            "node_path": {"type": "string", "description": "Optional node path with script attached"}
        },
        "required": []
    },
    "create_script_template": {
        "type": "object",
        "properties": {
            "base_class": {"type": "string", "description": "Base class (e.g. Node, Node2D, Control)"},
            "class_name": {"type": "string", "description": "Optional class name"},
            "include_ready": {"type": "boolean", "description": "Include _ready() function"},
            "include_process": {"type": "boolean", "description": "Include _process() function"},
            "include_input": {"type": "boolean", "description": "Include _input() function"},
            "include_physics_process": {"type": "boolean", "description": "Include _physics_process() function"}
        },
        "required": ["base_class"]
    },
    "execute_editor_script": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "GDScript code to execute in editor"}
        },
        "required": ["code"]
    },
}

def get_mcp_tool_def(name: str) -> dict | None:
    """获取 MCP 工具定义（含完整参数 schema）"""
    for t in _mcp_tools:
        if t["name"] == name:
            schema = _MCP_TOOL_SCHEMAS.get(name, t.get("inputSchema", {}))
            if not schema or not schema.get("properties"):
                schema = {"type": "object", "properties": {}, "required": []}
            return {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": schema
                }
            }
    return None


def is_mcp_tool(name: str) -> bool:
    """检查是否为 MCP 工具（从静态列表判断，不依赖运行时工具表）"""
    _MCP_KNOWN = frozenset({
        "create_node", "delete_node", "update_node_property", "get_node_properties",
        "list_nodes", "create_scene", "save_scene", "open_scene",
        "get_current_scene", "get_project_info", "create_resource",
        "create_script", "edit_script", "get_script", "create_script_template",
        "execute_editor_script",
    })
    return name in _MCP_KNOWN or name in get_mcp_tool_names()

#!/usr/bin/env python3
"""Maona 复杂长任务压力测试 — 诊断实际运行质量

通过真实的 Agent 对话流测试：
1. 多步骤文件创建任务
2. 工具调用成功率
3. 流中断/错误
4. 响应时间
5. 连续多轮对话
"""
import sys, os, json, time, asyncio, aiohttp, traceback
from datetime import datetime

# 配置
API_BASE = "http://127.0.0.1:8765"
TEST_WORKSPACE = os.path.join(os.path.dirname(__file__), "test_workspace")
os.makedirs(TEST_WORKSPACE, exist_ok=True)

STATS = {
    "start_time": None,
    "end_time": None,
    "tokens": [],
    "errors": [],
    "warnings": [],
    "tool_calls": [],
    "tool_results": [],
    "steps": [],
    "rounds_seen": set(),
    "auto_continues": 0,
    "round_limits": 0,
}

# ========== 复杂任务定义 ==========
COMPLEX_TASK = """请帮我创建一个完整的网页猜数字游戏项目。要求：
1. 创建 index.html（游戏主页面，包含输入框和猜数字逻辑）
2. 创建 style.css（好看的样式，居中布局，响应式设计）
3. 创建 game.js（游戏逻辑：1-100随机数，记录猜的次数，给提示太大/太小）
4. 创建 README.md（说明文档，包含如何运行和使用说明）

请确保：
- 所有文件放在 test_workspace/guess_game/ 目录下
- 代码完整可运行
- 样式美观
- 最后验证一下文件是否都创建成功了
"""


async def get_session_token(session):
    """获取 session token"""
    async with session.get(f"{API_BASE}/api/token") as resp:
        data = await resp.json()
        return data.get("token", "")


async def stream_chat(session, token, messages, workspace=""):
    """发送 SSE 流请求并解析事件"""
    url = f"{API_BASE}/api/chat/stream"
    headers = {
        "x-session-token": token,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body = {
        "messages": messages,
        "workspace": workspace,
        "project_id": "test_complex_task",
        "conversation_id": "",
    }

    async with session.post(url, json=body, headers=headers) as resp:
        if resp.status != 200:
            print(f"  ❌ HTTP {resp.status}")
            text = await resp.text()
            print(f"  Response: {text[:500]}")
            return

        buffer = ""
        event_count = 0
        
        async for chunk in resp.content.iter_any():
            if not chunk:
                continue
            text = chunk.decode("utf-8", errors="replace")
            buffer += text
            
            # 解析 SSE 行
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                
                data_str = line[6:]
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                
                event_type = event.get("type", "unknown")
                event_count += 1
                
                if event_type == "error":
                    content = event.get("content", "")
                    STATS["errors"].append(content)
                    print(f"  ❌ ERROR: {content[:120]}")
                
                elif event_type == "token":
                    STATS["tokens"].append(event.get("content", ""))
                
                elif event_type == "tool_call":
                    tool = event.get("tool", "?")
                    args = (event.get("args", "") or "")[:80]
                    STATS["tool_calls"].append({"tool": tool, "args": args})
                    print(f"  🔧 [{len(STATS['tool_calls'])}] {tool}: {args}")
                
                elif event_type == "tool_result":
                    result = (event.get("result", "") or "")[:120]
                    STATS["tool_results"].append(result)
                    if result.startswith("错误"):
                        print(f"     ❌ {result[:100]}")
                
                elif event_type == "step":
                    r = event.get("round", 0)
                    total = event.get("total", 0)
                    STATS["steps"].append(r)
                    STATS["rounds_seen"].add(r)
                    if len(STATS["rounds_seen"]) <= 3 or r % 10 == 0:
                        print(f"  📍 Step {r}/{total}")
                
                elif event_type == "auto_continue":
                    r = event.get("round", 0)
                    STATS["auto_continues"] += 1
                    print(f"  🔄 自动续接 {r}")
                
                elif event_type == "round_limit":
                    STATS["round_limits"] += 1
                    print(f"  ⚠️ 达到轮次上限")
                
                elif event_type == "context":
                    pct = event.get("pct", 0)
                    tokens = event.get("tokens", 0)
                    if pct > 70:
                        print(f"  📊 上下文: {tokens} tokens ({pct}%)")
                
                elif event_type == "done":
                    print(f"  ✅ 对话完成")
                
                elif event_type == "reasoning":
                    r = (event.get("content", "") or "")[:80]
                    if r:
                        print(f"  💭 {r}")
                
                elif event_type == "confirm_required":
                    print(f"  ⚠️ 需要确认: {event.get('command', '')[:60]}")
    
    return event_count


async def run_test():
    print("=" * 60)
    print(f"Maona 复杂长任务压力测试")
    print(f"时间: {datetime.now()}")
    print(f"工作空间: {TEST_WORKSPACE}")
    print("=" * 60)
    
    STATS["start_time"] = time.time()
    
    # 准备测试
    import shutil
    guess_dir = os.path.join(TEST_WORKSPACE, "guess_game")
    if os.path.exists(guess_dir):
        shutil.rmtree(guess_dir)
    
    timeout = aiohttp.ClientTimeout(total=600)  # 10分钟超时
    connector = aiohttp.TCPConnector(limit=1)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # 获取 token
        token = await get_session_token(session)
        if not token:
            print("❌ 无法获取 session token")
            return
        print(f"✅ Token: {token[:20]}...")
        
        # 发送复杂任务
        messages = [{"role": "user", "content": COMPLEX_TASK}]
        
        print(f"\n📤 发送任务: {COMPLEX_TASK.split(chr(10))[0]}...")
        print("-" * 40)
        
        event_count = await stream_chat(session, token, messages, TEST_WORKSPACE)
        
        STATS["end_time"] = time.time()
    
    # ========== 分析结果 ==========
    elapsed = STATS["end_time"] - STATS["start_time"]
    full_text = "".join(STATS["tokens"])
    
    print("\n" + "=" * 60)
    print("📊 测试结果分析")
    print("=" * 60)
    
    print(f"\n⏱️  总耗时: {elapsed:.1f}s")
    print(f"🔧 工具调用: {len(STATS['tool_calls'])} 次")
    print(f"📍 执行轮次: {len(STATS['rounds_seen'])}/{len(STATS['steps'])} 步")
    print(f"🔄 自动续接: {STATS['auto_continues']} 次")
    print(f"📝 输出字符: {len(full_text)}")
    print(f"❌ 错误数: {len(STATS['errors'])}")
    print(f"📨 SSE 事件: {event_count}")
    
    # 检查创建的文件
    print(f"\n📁 文件验证:")
    expected_files = [
        "test_workspace/guess_game/index.html",
        "test_workspace/guess_game/style.css",
        "test_workspace/guess_game/game.js",
        "test_workspace/guess_game/README.md",
    ]
    all_ok = True
    for f in expected_files:
        full = os.path.join(os.path.dirname(__file__), f)
        exists = os.path.exists(full)
        size = os.path.getsize(full) if exists else 0
        status = "✅" if exists and size > 50 else "⚠️ 太小" if exists else "❌ 缺失"
        if not exists or size <= 50:
            all_ok = False
        print(f"  {status} {f} ({size}B)")
    
    # 错误摘要
    if STATS["errors"]:
        print(f"\n⚠️ 错误列表:")
        for e in STATS["errors"][:5]:
            print(f"  - {e[:150]}")
    
    # 工具调用分析
    tool_names = {}
    for tc in STATS["tool_calls"]:
        name = tc["tool"]
        tool_names[name] = tool_names.get(name, 0) + 1
    print(f"\n🔧 工具使用频率:")
    for name, count in sorted(tool_names.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count}次")
    
    # 判定
    print(f"\n{'='*60}")
    if all_ok and len(STATS["errors"]) == 0:
        print("✅ 测试通过 — 复杂任务成功完成")
    elif all_ok:
        print("⚠️ 基本通过 — 有错误但任务完成")
    else:
        print("❌ 测试失败 — 文件缺失或任务未完成")
    
    # 保存详细日志
    log_path = os.path.join(os.path.dirname(__file__), "test_result.json")
    result = {
        "time": str(datetime.now()),
        "elapsed_seconds": elapsed,
        "tool_calls": len(STATS["tool_calls"]),
        "rounds": len(STATS["rounds_seen"]),
        "auto_continues": STATS["auto_continues"],
        "errors": len(STATS["errors"]),
        "output_chars": len(full_text),
        "tool_frequency": tool_names,
        "error_details": STATS["errors"][:20],
        "files_created": {f: os.path.exists(os.path.join(os.path.dirname(__file__), f)) for f in expected_files},
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n📄 详细日志: {log_path}")
    
    return result


if __name__ == "__main__":
    asyncio.run(run_test())

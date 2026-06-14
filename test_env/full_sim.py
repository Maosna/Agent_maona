#!/usr/bin/env python3
"""
Maona 完整模拟测试 — 记忆系统 + Agent 循环 + 工具全部真实

唯一替换：LLM 通过 decisions.jsonl 队列驱动。
其他全部走 Maona 真实代码。
"""
import sys, os, json, asyncio, time, shutil

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

from stdin_provider import StdinProvider
from api.chat import stream_chat
from unittest.mock import MagicMock
import api.chat

# 持久化工作空间（记忆系统依赖）
WS = r"F:\工具\Agent_maona\test_workspace"
os.makedirs(os.path.join(WS, ".maona", "memory"), exist_ok=True)


async def run_conversation(user_msg: str, conv_id: str = ""):
    """运行一次完整对话，返回事件列表"""
    provider = StdinProvider()
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'AI', 'models': ['ai'], 'api_key': 'sk'}]
    mgr.get_provider.return_value = provider
    api.chat.pm = mgr
    api.chat.ps = MagicMock()
    api.chat.ps.get_provider.return_value = {'name': 'AI', 'models': ['ai']}
    api.chat.get_model_settings = MagicMock(return_value={'temperature': 0.7, 'max_tokens': 4096})

    request = type('obj', (object,), {
        'messages': [MagicMock(role='user', content=user_msg)],
        'workspace': WS,
        'project_id': 'full_sim',
        'conversation_id': conv_id,
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()
    async for e in stream_chat(request):
        ev = json.loads(e)
        events.append(ev)
        t = ev.get('type', '')
        if t == 'tool_call':
            print(f"  🔧 {ev.get('tool')} → {str(ev.get('args',''))[:60]}")
        elif t == 'tool_result':
            r = str(ev.get('result', ''))
            if '错误' in r:
                print(f"  ❌ {r[:100]}")
            else:
                print(f"  ✅ {r[:80]}")
        elif t == 'error':
            print(f"  💥 {ev.get('content','')[:120]}")
        elif t == 'step':
            print(f"  📍 {ev.get('round')}/{ev.get('total')}")
    elapsed = time.time() - t0

    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    errors = sum(1 for e in events if e.get('type') == 'error')
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')

    print(f"  ⏱ {elapsed:.1f}s | 🔧 {tools} | 📝 {len(tokens)} chars")
    if tokens:
        print(f"  💬 {tokens[:200]}")
    return events


async def main():
    scenarios = [
        ("对话1-问候", "你好，我叫露可，记住我的名字"),
        ("对话2-记忆验证", "你还记得我叫什么名字吗？"),
        ("对话3-创建项目", "请在F:\\工具\\测试目录下创建一个hello.py，内容是打印'Hello from Maona记忆测试'"),
        ("对话4-记录日志", "请把刚才创建文件的操作记录到每日日志"),
    ]

    print("=" * 60)
    print("Maona 完整模拟 — 记忆系统 + Agent 全链路")
    print(f"工作空间: {WS}")
    print("=" * 60)

    for name, msg in scenarios:
        print(f"\n{'='*50}")
        print(f"📋 {name}")
        print(f"   消息: {msg}")
        print(f"{'='*50}")
        try:
            await run_conversation(msg)
        except Exception as e:
            print(f"  💥 对话崩溃: {type(e).__name__}: {str(e)[:200]}")

    # 验证记忆
    print(f"\n{'='*50}")
    print("📊 记忆系统验证")
    print(f"{'='*50}")

    # 检查每日日志
    from tools.memory_tools import read_memory
    mem = await read_memory(query="露可")
    print(f"长期记忆: {mem[:300] if mem else '(空)'}")

    # 检查工作空间
    maona_dir = os.path.join(WS, ".maona")
    if os.path.exists(maona_dir):
        print(f"\n.maona 目录: {os.listdir(maona_dir)}")
        mem_dir = os.path.join(maona_dir, "memory")
        if os.path.exists(mem_dir):
            print(f"记忆文件: {os.listdir(mem_dir)}")


if __name__ == '__main__':
    asyncio.run(main())

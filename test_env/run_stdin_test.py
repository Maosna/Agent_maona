#!/usr/bin/env python3
"""
stdin 驱动测试 — AI 通过 stdin 逐轮决策

完全真实：Agent 循环、工具调度、SSE 流全部用 Maona 代码。
只有 LLM 决策通过 stdin 输入。
"""
import sys, os, json, asyncio, time, tempfile

sys.path.insert(0, r'F:/工具/Agent_maona/backend')


async def main():
    from stdin_provider import StdinProvider
    from api.chat import stream_chat
    from unittest.mock import MagicMock
    import api.chat

    ws = tempfile.mkdtemp(prefix="stdin_")
    msg = sys.argv[1] if len(sys.argv) > 1 else "你好"

    # 注入 stdin provider
    provider = StdinProvider()
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'stdin', 'models': ['ai'], 'api_key': 'sk'}]
    mgr.get_provider.return_value = provider
    api.chat.pm = mgr
    api.chat.ps = MagicMock()
    api.chat.ps.get_provider.return_value = {'name': 'stdin', 'models': ['ai']}
    api.chat.get_model_settings = MagicMock(return_value={'temperature': 0.7, 'max_tokens': 4096})

    request = type('obj', (object,), {
        'messages': [MagicMock(role='user', content=msg)],
        'workspace': ws, 'project_id': 'stdin_test', 'conversation_id': '',
        'model': None, 'provider': None, 'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()

    print(f"工作空间: {ws}")
    print(f"用户消息: {msg}")

    async for e in stream_chat(request):
        ev = json.loads(e)
        t = ev.get('type', '')
        if t == 'tool_call':
            print(f"  🔧 {ev.get('tool')}")
        elif t == 'tool_result':
            r = str(ev.get('result', ''))[:100]
            print(f"  📋 {r}")
        elif t == 'token':
            pass  # tokens 在 AI 决策输出时已显示
        elif t == 'error':
            print(f"  💥 {ev.get('content', '')}")
        elif t == 'done':
            print(f"  ✅ 完成")
        elif t == 'step':
            print(f"  📍 {ev.get('round')}/{ev.get('total')}")
        events.append(ev)

    elapsed = time.time() - t0
    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    errors = sum(1 for e in events if e.get('type') == 'error')
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')

    print(f"\n结果: {tools} tools, {errors} errors, {len(tokens)} chars, {elapsed:.1f}s")
    if tokens:
        print(f"回复: {tokens[:300]}")


if __name__ == '__main__':
    asyncio.run(main())

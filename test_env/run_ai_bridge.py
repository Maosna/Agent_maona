#!/usr/bin/env python3
"""AI 桥接驱动：启动 Agent → 等 AI 决策 → 执行 → 循环"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
D = os.path.dirname(os.path.abspath(__file__))

CTX = os.path.join(D, "context.json")
DEC = os.path.join(D, "decision.json")


async def main():
    from ai_direct_test import AIDirectProvider
    from api.chat import stream_chat
    from unittest.mock import MagicMock
    import api.chat, tempfile

    ws = tempfile.mkdtemp(prefix="ai_")
    msg = sys.argv[1] if len(sys.argv) > 1 else "你好"

    mock = AIDirectProvider()
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'AI', 'models': ['ai'], 'api_key': 'sk'}]
    mgr.get_provider.return_value = mock
    api.chat.pm = mgr
    api.chat.ps = MagicMock()
    api.chat.ps.get_provider.return_value = {'name': 'AI', 'models': ['ai']}
    api.chat.get_model_settings = MagicMock(return_value={'temperature': 0.7, 'max_tokens': 4096})

    req = type('obj', (object,), {
        'messages': [MagicMock(role='user', content=msg)],
        'workspace': ws, 'project_id': 'bridge', 'conversation_id': '',
        'model': None, 'provider': None, 'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()
    agent = asyncio.ensure_future(_collect(stream_chat(req), events))

    while not agent.done():
        if os.path.exists(CTX) and not os.path.exists(DEC):
            print(f"READY")  # signal to WorkBuddy
            await asyncio.sleep(2)  # give AI time to write decision
        await asyncio.sleep(0.5)

    elapsed = time.time() - t0
    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    errors = sum(1 for e in events if e.get('type') == 'error')
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')
    print(f"DONE|tools={tools}|errors={errors}|chars={len(tokens)}|time={elapsed:.1f}")
    print(tokens[:300])


async def _collect(gen, events):
    async for e in gen:
        events.append(json.loads(e))


if __name__ == '__main__':
    asyncio.run(main())

#!/usr/bin/env python3
"""
AI 全链路驱动测试 — 单进程运行 Agent 循环 + AI 决策桥接

WorkBuddy Agent 通过 context.json/decision.json 驱动真实 Agent 循环。
用法：python ai_full_test.py "你的问题"
然后 WorkBuddy Agent 读取 context.json，写入 decision.json。
"""
import sys, os, json, asyncio, time, signal

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(TEST_DIR, "context.json")
DECISION_FILE = os.path.join(TEST_DIR, "decision.json")


async def wait_for_context(timeout=300):
    """等待 context.json 出现"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(CONTEXT_FILE):
            with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        await asyncio.sleep(0.3)
    return None


async def main():
    from ai_direct_test import AIDirectProvider
    from api.chat import stream_chat
    from unittest.mock import MagicMock
    import api.chat, tempfile

    ws = tempfile.mkdtemp(prefix="ai_maona_")
    user_msg = sys.argv[1] if len(sys.argv) > 1 else "你好"

    print(f"工作空间: {ws}")
    print(f"用户消息: {user_msg}")
    print(f"等待 AI 决策...")

    # 注入 AI Provider
    mock = AIDirectProvider()
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'AI', 'models': ['ai'], 'api_key': 'sk-ai'}]
    mgr.get_provider.return_value = mock
    api.chat.pm = mgr
    api.chat.ps = MagicMock()
    api.chat.ps.get_provider.return_value = {'name': 'AI', 'models': ['ai'], 'api_key': 'sk-ai'}
    api.chat.get_model_settings = MagicMock(return_value={'temperature': 0.7, 'max_tokens': 4096, 'top_p': 1.0})

    request = type('obj', (object,), {
        'messages': [MagicMock(role='user', content=user_msg)],
        'workspace': ws, 'project_id': 'ai_full_test',
        'conversation_id': '', 'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()

    async def run_agent():
        async for e in stream_chat(request):
            events.append(json.loads(e))

    agent_task = asyncio.ensure_future(run_agent())

    # 主循环：等 context → AI 写 decision → 继续
    while not agent_task.done():
        ctx = await wait_for_context(timeout=10)
        if ctx is None:
            if agent_task.done():
                break
            continue

        # 清除 context.json 标记为"已读"
        os.remove(CONTEXT_FILE)

        # 自动处理摘要请求
        last_msg = ""
        for m in reversed(ctx.get('conversation', [])):
            if m.get('role') == 'user' and '请将以上对话总结' in m.get('content', ''):
                last_msg = m['content']
                break

        if last_msg:
            # 自动摘要回复
            with open(DECISION_FILE, 'w', encoding='utf-8') as f:
                json.dump({"content": "对话摘要已生成", "tool_calls": None}, f, ensure_ascii=False)
            continue

        # 等待 AI（WorkBuddy Agent）写 decision.json
        print(f"\nRound {ctx['round']}: 等待 AI 决策...")
        print(f"  context.json 就绪，请 WorkBuddy 读取并写入 decision.json")

        dl = time.time() + 300
        got_decision = False
        while time.time() < dl and not agent_task.done():
            if os.path.exists(DECISION_FILE):
                got_decision = True
                break
            await asyncio.sleep(0.5)

        if not got_decision:
            print("  AI 超时，发送默认回复")
            with open(DECISION_FILE, 'w', encoding='utf-8') as f:
                json.dump({"content": "AI 超时", "tool_calls": None}, f, ensure_ascii=False)

    # 输出结果
    elapsed = time.time() - t0
    tools = [e for e in events if e.get('type') == 'tool_call']
    errors = [e for e in events if e.get('type') == 'error']
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')

    print(f"\n{'='*50}")
    print(f"结果: {len(events)} events, {len(tools)} tools, {len(errors)} errors, {elapsed:.1f}s")
    print(f"回复: {tokens[:300]}")
    if errors:
        for e in errors:
            print(f"错误: {e.get('content', '')[:120]}")
    print(f"{'='*50}")


if __name__ == '__main__':
    asyncio.run(main())

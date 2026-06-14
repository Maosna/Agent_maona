#!/usr/bin/env python3
"""
AI 直连测试 — WorkBuddy Agent 直接驱动 Maona Agent 循环

不再经过 HTTP/SSE，直接调用 stream_chat 生成器。
每个 LLM 调用会写入 context.json，然后等待 decision.json。
WorkBuddy Agent 读取上下文 → 做出决策 → 写回 decision.json。
"""
import sys, os, json, asyncio, tempfile, shutil, time
from pathlib import Path

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(TEST_DIR, "context.json")
DECISION_FILE = os.path.join(TEST_DIR, "decision.json")
READY_FILE = os.path.join(TEST_DIR, "ai_ready.txt")

# 清理残留文件
for f in [CONTEXT_FILE, DECISION_FILE, READY_FILE]:
    try: os.remove(f)
    except: pass


class AIDirectProvider:
    """
    文件桥接 Provider — 等待 WorkBuddy Agent 做决策。
    WorkBuddy 读取 context.json → 写 decision.json → Provider 继续。
    """

    def __init__(self):
        self.round = 0

    async def chat_non_stream(self, messages, tools=None, **kw):
        self.round += 1

        # 自动处理上下文压缩/摘要请求（不需要 AI 参与）
        last_content = ""
        for m in reversed(messages):
            c = str(m.get("content", ""))
            if c and not c.startswith("["):
                last_content = c
                break
        if "请将以上对话总结" in last_content or "总结为详细的结构化" in last_content:
            # 自动生成简要摘要
            user_msgs = [m for m in messages if m.get("role") == "user" and not str(m.get("content","")).startswith("[") and "请将" not in str(m.get("content",""))]
            asst_msgs = [m for m in messages if m.get("role") == "assistant"]
            parts = []
            for m in user_msgs[-3:]:
                parts.append(f"- 用户: {str(m['content'])[:100]}")
            for m in asst_msgs[-2:]:
                c = str(m.get("content", ""))[:200]
                if c:
                    parts.append(f"- 助手: {c}")
            return {"content": "## 对话摘要\n" + "\n".join(parts), "tool_calls": None}

        # 提取工具名
        tool_names = [t['function']['name'] for t in (tools or [])]

        # 构建 context
        context = {
            "round": self.round,
            "system_prompt": str(messages[0].get("content", ""))[:1000] if messages else "",
            "conversation": [],
            "tool_names": tool_names,
        }
        for m in messages[1:]:  # 跳过 system prompt
            role = m.get("role", "?")
            content = str(m.get("content", ""))
            tc = m.get("tool_calls")
            entry = {"role": role, "content": content[:800]}
            if tc:
                entry["tool_calls"] = [
                    {"name": t.get("function", {}).get("name", "?"),
                     "args": t.get("function", {}).get("arguments", "")[:200]}
                    for t in tc
                ]
            context["conversation"].append(entry)

        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        with open(READY_FILE, "w") as f:
            f.write(str(self.round))
            f.flush()
            os.fsync(f.fileno())

        # 等待 decision.json（非阻塞轮询，长超时）
        deadline = time.time() + 600  # 10 分钟
        while time.time() < deadline:
            if os.path.exists(DECISION_FILE):
                try:
                    with open(DECISION_FILE, "r", encoding="utf-8") as f:
                        decision = json.load(f)
                    os.remove(DECISION_FILE)
                    return {
                        "content": decision.get("content", ""),
                        "tool_calls": decision.get("tool_calls"),
                    }
                except json.JSONDecodeError:
                    pass
            await asyncio.sleep(0.3)

        return {"content": "AI 超时", "tool_calls": None}


async def run(workspace, user_message):
    """用 AI 驱动运行一次完整对话"""
    from api.chat import stream_chat
    from unittest.mock import MagicMock
    import api.chat

    # 注入 Provider
    mock = AIDirectProvider()
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'AI', 'models': ['ai'], 'api_key': 'sk-ai'}]
    mgr.get_provider.return_value = mock
    api.chat.pm = mgr
    store = MagicMock()
    store.get_provider.return_value = {'name': 'AI', 'models': ['ai'], 'api_key': 'sk-ai'}
    api.chat.ps = store
    settings = MagicMock()
    settings.return_value = {"temperature": 0.7, "max_tokens": 4096, "top_p": 1.0}
    api.chat.get_model_settings = settings

    request = type('obj', (object,), {
        'messages': [MagicMock(role="user", content=user_message)],
        'workspace': workspace,
        'project_id': 'ai_direct',
        'conversation_id': '',
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    events = []
    start = time.time()
    async for event_json in stream_chat(request):
        events.append(json.loads(event_json))

    elapsed = time.time() - start
    return events, elapsed, mock.round


if __name__ == "__main__":
    ws = tempfile.mkdtemp(prefix="ai_maona_")
    print(f"工作空间: {ws}")
    print(f"就绪，等待 AI 驱动...")
    print()

    events, elapsed, rounds = asyncio.run(run(ws, sys.argv[1] if len(sys.argv) > 1 else "你好"))

    # 打印结果
    tools = [e for e in events if e.get("type") == "tool_call"]
    errors = [e for e in events if e.get("type") == "error"]
    tokens = "".join(e.get("content", "") for e in events if e.get("type") == "token")

    print(f"\n结果: {len(tools)} tools, {len(errors)} errors, {len(tokens)} chars, {elapsed:.1f}s")
    if tokens:
        print(f"回复: {tokens[:300]}")
    if errors:
        for e in errors:
            print(f"错误: {e.get('content', '')[:120]}")

    shutil.rmtree(ws, ignore_errors=True)

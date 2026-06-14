#!/usr/bin/env python3
"""
AI 驱动测试运行器

启动 Maona 后端（使用 AIDrivenProvider），
通过 HTTP SSE 发送用户消息，
每个 LLM 调用暂停到 context.json，等 AI 写入 decision.json 后继续。

用法:
  python run_ai_test.py          # 启动，等待 AI 逐轮决策
  python run_ai_test.py --auto   # 自动模式（使用 smart_mock 回退）
"""
import sys, os, json, asyncio, time, subprocess, signal
from pathlib import Path

sys.path.insert(0, r'F:/工具/Agent_maona/backend')

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(TEST_DIR, "context.json")
DECISION_FILE = os.path.join(TEST_DIR, "decision.json")
READY_FILE = os.path.join(TEST_DIR, "ai_ready.txt")


def note(msg):
    print(f"\n{'='*50}\n📋 {msg}\n{'='*50}")


async def send_scenario(scenario_name, user_messages):
    """发送一个用户场景到 Maona，通过 HTTP SSE"""
    import aiohttp

    note(f"场景: {scenario_name}")
    print(f"   消息: {user_messages[0][:80]}...")
    print(f"   后端: http://127.0.0.1:8766")

    # 获取 token
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:8766/api/token") as resp:
            if resp.status != 200:
                print(f"   ❌ 后端未响应: {resp.status}")
                return
            token = (await resp.json()).get("token", "")

        # 构建请求
        from unittest.mock import MagicMock
        msg_objs = [MagicMock(role="user", content=m) for m in user_messages]
        body = {
            "messages": [{"role": "user", "content": m} for m in user_messages],
            "workspace": os.path.join(TEST_DIR, "test_workspace"),
            "project_id": f"ai_test_{scenario_name}",
            "conversation_id": "",
            "model": None,
            "provider": None,
            "persona_id": None,
            "mode": "craft",
        }

        headers = {"x-session-token": token, "Content-Type": "application/json"}
        async with session.post("http://127.0.0.1:8766/api/chat/stream",
                                 json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"   ❌ HTTP {resp.status}: {text[:300]}")
                return

            tools = 0
            text_out = ""
            errors = 0
            async for chunk in resp.content:
                line = chunk.decode("utf-8", errors="replace")
                for l in line.split("\n"):
                    l = l.strip()
                    if l.startswith("data: "):
                        try:
                            ev = json.loads(l[6:])
                            t = ev.get("type", "")
                            if t == "tool_call":
                                tools += 1
                                print(f"  🔧 {ev.get('tool')}")
                            elif t == "tool_result":
                                r = str(ev.get("result", ""))[:80]
                                if "错误" in r:
                                    print(f"  ❌ {r}")
                                    errors += 1
                            elif t == "token":
                                text_out += ev.get("content", "")
                            elif t == "error":
                                print(f"  💥 {ev.get('content','')[:120]}")
                                errors += 1
                            elif t == "done":
                                print(f"  ✅ done")
                        except:
                            pass

            print(f"\n  📊 tools={tools}, chars={len(text_out)}, errors={errors}")
            if text_out:
                print(f"  💬 {text_out[:200]}")

    return tools, errors, text_out


def main():
    note("AI 驱动 Maona 测试")
    print(f"   确保后端已启动: cd {TEST_DIR}/backend && python main.py --port 8766")
    print(f"   并在另一个窗口运行本脚本")
    print(f"   AI 在 context.json 就绪时写入 decision.json")
    print()
    print(f"   等待中... 按 Ctrl+C 停止")
    print()

    # 等待后端就绪并发送测试
    # 需要用户在另一个终端启动后端
    asyncio.run(send_scenario(
        "简单问候",
        ["你好，请介绍一下你自己"]
    ))


if __name__ == "__main__":
    main()

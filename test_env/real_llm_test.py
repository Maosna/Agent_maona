#!/usr/bin/env python3
"""真·LLM 驱动模拟 — DeepSeek 实时决策，Maona 真实执行"""
import sys, os, json, time, tempfile, shutil, asyncio

try:
    import httpx
except ImportError:
    os.system(f'"{sys.executable}" -m pip install httpx -q')
    import httpx

BACKEND = "http://127.0.0.1:8765"
WS = tempfile.mkdtemp(prefix="real_llm_")

async def get_token():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND}/api/token")
        return r.json()["token"]

async def chat(token, messages, workspace, project, mode="craft"):
    """发送消息并收集所有 SSE 事件"""
    body = {
        "messages": [{"role": "user", "content": m} for m in messages],
        "workspace": workspace,
        "project_id": project,
        "model": "deepseek-v4-flash",
        "provider": "DeepSeek",
        "mode": mode,
    }
    headers = {"x-session-token": token, "Content-Type": "application/json"}

    events = []
    async with httpx.AsyncClient(timeout=120) as c:
        async with c.stream("POST", f"{BACKEND}/api/chat/stream", json=body, headers=headers) as resp:
            if resp.status_code != 200:
                print(f"  ❌ HTTP {resp.status_code}")
                return events
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        events.append(ev)
                    except:
                        pass
    return events

def print_result(name, events, elapsed):
    tools = [e for e in events if e.get("type") == "tool_call"]
    errors = [e for e in events if e.get("type") == "error"]
    tokens = "".join(e.get("content","") for e in events if e.get("type") == "token")
    done = any(e.get("type") == "done" for e in events)

    status = "✅" if done and not errors else "❌"
    print(f"\n  {status} {name}: {elapsed:.1f}s | 🔧{len(tools)} | 💥{len(errors)} | 📝{len(tokens)}c")
    for tc in tools:
        name = tc.get("tool","?")
        print(f"    🔧 {name}")
    if tokens:
        print(f"    💬 {tokens[:200]}")
    if errors:
        for e in errors:
            print(f"    ❌ {e.get('content','')[:120]}")


async def main():
    print("=" * 60)
    print("真·LLM 驱动模拟 — DeepSeek → Maona Agent 循环")
    print(f"工作空间: {WS}")
    print("=" * 60)

    token = await get_token()

    # 场景1: 问候 + 记名 + 创建项目
    print("\n📋 场景1: 问候 + 创建项目")
    t0 = time.time()
    events1 = await chat(token, ["你好！我叫小光，喜欢Python。请帮我在这里创建一个hello.py，内容是打印'Hello 小光'"], WS, "test1")
    print_result("场景1", events1, time.time() - t0)

    # 场景2: 记忆召回 + Python计算
    print("\n📋 场景2: 记忆验证 + Python计算")
    t0 = time.time()
    events2 = await chat(token, ["还记得我的名字和喜好吗？用Python帮我算1到50的和"], WS, "test2")
    print_result("场景2", events2, time.time() - t0)

    # 验证文件
    py = os.path.join(WS, "hello.py")
    if os.path.exists(py):
        print(f"\n📁 hello.py: {open(py).read()[:100]}")
    else:
        print("\n📁 hello.py: 未创建")

    # 清理
    shutil.rmtree(WS, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())

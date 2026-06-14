#!/usr/bin/env python3
"""真·LLM 驱动 — 在 F:\工具\测试 创建猜单词游戏"""
import sys, os, json, time, asyncio, httpx

BACKEND = "http://127.0.0.1:8765"
GAME_DIR = r"F:\工具\测试\hangman_game"
os.makedirs(GAME_DIR, exist_ok=True)

async def get_token():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND}/api/token")
        return r.json()["token"]

async def chat(token, msg, mode="craft"):
    body = {
        "messages": [{"role": "user", "content": msg}],
        "workspace": GAME_DIR,
        "project_id": "game_test",
        "model": "deepseek-v4-flash",
        "provider": "DeepSeek",
        "mode": mode,
    }
    headers = {"x-session-token": token, "Content-Type": "application/json"}
    events = []
    async with httpx.AsyncClient(timeout=180) as c:
        async with c.stream("POST", f"{BACKEND}/api/chat/stream", json=body, headers=headers) as resp:
            if resp.status_code != 200:
                print(f"  ❌ HTTP {resp.status_code}")
                return events
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try: events.append(json.loads(line[6:]))
                    except: pass
    return events

def show(events, elapsed):
    tools = [e for e in events if e.get("type") == "tool_call"]
    texts = "".join(e.get("content","") for e in events if e.get("type") == "token")
    errors = [e for e in events if e.get("type") == "error"]
    done = any(e.get("type") == "done" for e in events)

    print(f"  ⏱ {elapsed:.0f}s | 🔧{len(tools)} | 💥{len(errors)} | done={done}")
    for tc in tools:
        a = str(tc.get("args",""))[:80]
        print(f"    🔧 {tc.get('tool','?')}: {a}")
    if texts:
        print(f"    💬 {texts[:300]}")
    for e in errors:
        print(f"    ❌ {e.get('content','')[:120]}")
    return done and not errors


async def main():
    print("=" * 60)
    print("真·LLM 驱动 — 猜单词 Hangman 游戏")
    print(f"目录: {GAME_DIR}")
    print("=" * 60)

    token = await get_token()

    # 任务：创建完整的猜单词游戏
    t0 = time.time()
    events = await chat(token,
        f"请在 {GAME_DIR} 下创建一个完整的猜单词(Hangman)游戏项目，要求：\n"
        "1. main.py — 游戏主循环，带难度选择（简单/中等/困难，对应不同单词长度）\n"
        "2. words.py — 单词库，至少30个英文单词，按难度分类\n"
        "3. game.py — 游戏逻辑（猜字母、计分、画 hangman）\n"
        "4. README.md — 游玩说明\n"
        "所有Python文件要有中文注释"
    )
    ok1 = show(events, time.time() - t0)

    # 验证阶段
    print("\n📋 验证: 运行测试")
    t0 = time.time()
    events2 = await chat(token,
        f"请检查 {GAME_DIR} 下所有文件是否创建成功，并用Python测试game.py的逻辑是否正确运行",
        mode="craft"
    )
    ok2 = show(events2, time.time() - t0)

    # 最终报告
    print(f"\n{'='*60}")
    print("📊 验证报告")
    print(f"{'='*60}")
    files = []
    for root, dirs, fnames in os.walk(GAME_DIR):
        for fn in fnames:
            if fn.endswith(('.py','.md')):
                fp = os.path.join(root, fn)
                size = os.path.getsize(fp)
                files.append((os.path.relpath(fp, GAME_DIR), size))
    for name, size in sorted(files):
        print(f"  {'✅' if size > 0 else '❌'} {name} ({size}B)")
    print(f"\n  {'🎉 全部通过' if ok1 and ok2 and len(files) >= 4 else '⚠️ 有问题'}")


if __name__ == "__main__":
    asyncio.run(main())

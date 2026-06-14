#!/usr/bin/env python3
"""复杂长任务验证 — 多对话图书管理系统"""
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\library"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(os.path.join(DIR, ".maona", "memory"), exist_ok=True)

async def chat(token, msg, project):
    body = {
        "messages": [{"role": "user", "content": msg}],
        "workspace": DIR, "project_id": project,
        "model": "deepseek-v4-flash", "provider": "DeepSeek", "mode": "craft",
    }
    h = {"x-session-token": token, "Content-Type": "application/json"}
    events = []
    async with httpx.AsyncClient(timeout=300) as c:
        async with c.stream("POST", "http://127.0.0.1:8765/api/chat/stream", json=body, headers=h) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    try: events.append(json.loads(line[6:]))
                    except: pass
    return events

def show(name, events, t0):
    tools = [e for e in events if e.get("type") == "tool_call"]
    errs = [e for e in events if e.get("type") == "error"]
    cont = [e for e in events if e.get("type") == "auto_continue"]
    text = "".join(e.get("content","") for e in events if e.get("type") == "token")
    done = any(e.get("type") == "done" for e in events)
    ok = "✅" if done and not errs else "❌"
    print(f"{ok} {name}: {time.time()-t0:.0f}s 🔧{len(tools)} 🔄{len(cont)} 💥{len(errs)}")
    for tc in tools:
        print(f"     🔧 {tc.get('tool','?')}")
    if cont:
        print(f"     🔄 自动续接 ×{len(cont)}")
    if text:
        print(f"     💬 {text[:200]}")

async def main():
    print("=" * 55)
    print("复杂长任务: 图书管理系统")
    print("=" * 55)

    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token")
        token = r.json()["token"]

    # 对话1: 创建系统
    t0 = time.time()
    e1 = await chat(token,
        f"在{DIR}下创建一个Python图书管理系统：\n"
        "1. book.py — Book类(书名/作者/ISBN/状态)\n"
        "2. library.py — Library类(增删查改/借还/统计)\n"
        "3. main.py — 交互菜单\n"
        "4. test_data.py — 10本测试书籍\n"
        "5. README.md\n"
        "记住：我叫管理员，这个系统用于社区图书馆",
        "lib1")
    show("📋 对话1: 创建系统", e1, t0)

    # 对话2: 验证 + 测试
    t0 = time.time()
    e2 = await chat(token,
        f"还记得我是谁吗？请运行Python语法检查和功能测试，验证{DIR}下所有文件是否正常工作",
        "lib2")
    show("📋 对话2: 验证测试", e2, t0)

    # 对话3: 扩展功能
    t0 = time.time()
    e3 = await chat(token,
        f"给图书馆系统添加搜索功能(search.py)，支持按书名/作者搜索。更新main.py菜单。"
        f"最后确认我的身份。",
        "lib3")
    show("📋 对话3: 扩展搜索", e3, t0)

    # 验证
    files = []
    for root, dirs, fnames in os.walk(DIR):
        for fn in fnames:
            fp = os.path.join(root, fn)
            if not fn.startswith("."):
                files.append((os.path.relpath(fp, DIR), os.path.getsize(fp)))

    print(f"\n📁 文件 ({len(files)}):")
    for name, size in sorted(files):
        icon = "✅" if size > 100 else ("⚠️" if size > 10 else "❌")
        print(f"  {icon} {name} ({size}B)")

    total_tools = sum(len([e for e in evs if e.get("type")=="tool_call"]) for evs in [e1,e2,e3])
    total_errs = sum(len([e for e in evs if e.get("type")=="error"]) for evs in [e1,e2,e3])
    print(f"\n{'🎉 全部通过' if total_errs == 0 and len(files) >= 5 else '⚠️ 有问题'}")

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""真·LLM 多对话连续任务 — 检验衔接能力"""
import sys, os, json, time, asyncio, httpx, shutil

BACKEND = "http://127.0.0.1:8765"
BASE = r"F:\工具\测试\multi_test"
os.makedirs(os.path.join(BASE, ".maona", "memory"), exist_ok=True)

async def get_token():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND}/api/token")
        return r.json()["token"]

async def chat(token, msg, project, conv_id=""):
    body = {
        "messages": [{"role": "user", "content": msg}],
        "workspace": BASE,
        "project_id": project,
        "conversation_id": conv_id,
        "model": "deepseek-v4-flash",
        "provider": "DeepSeek",
        "mode": "craft",
    }
    headers = {"x-session-token": token, "Content-Type": "application/json"}
    events = []
    async with httpx.AsyncClient(timeout=300) as c:
        async with c.stream("POST", f"{BACKEND}/api/chat/stream", json=body, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try: events.append(json.loads(line[6:]))
                    except: pass
    return events


def report(name, events, elapsed):
    tools = [e for e in events if e.get("type") == "tool_call"]
    errors = [e for e in events if e.get("type") == "error"]
    text = "".join(e.get("content","") for e in events if e.get("type") == "token")
    done = any(e.get("type") == "done" for e in events)

    icon = "✅" if done and not errors else "❌"
    print(f"\n{'─'*50}")
    print(f"📋 {name}")
    print(f"   {icon} {elapsed:.0f}s | 🔧{len(tools)} | 💥{len(errors)} | 📝{len(text)}c")
    for tc in tools:
        a = str(tc.get("args",""))[:80]
        print(f"     🔧 {tc.get('tool','?')}: {a}")
    if text:
        print(f"     💬 {text[:250]}")
    if errors:
        for e in errors:
            print(f"     ❌ {e.get('content','')[:150]}")
    return done and not errors, text


async def main():
    print("=" * 60)
    print("真·LLM 多对话连续任务测试")
    print(f"工作空间: {BASE}")
    print("=" * 60)

    token = await get_token()
    all_ok = True

    # ═══════ 对话1: 创建任务管理器 ═══════
    t0 = time.time()
    e1 = await chat(token,
        f"在 {BASE}/task_mgr 下创建一个Python命令行任务管理器，包含：\n"
        "1. main.py — 主菜单（添加/查看/删除/完成 任务）\n"
        "2. storage.py — JSON 文件存储读写\n"
        "3. README.md — 使用说明\n"
        "记住：我姓王，这个项目是给团队用的",
        "task1"
    )
    ok1, txt1 = report("对话1: 创建任务管理器", e1, time.time()-t0)
    all_ok &= ok1

    # ═══════ 对话2: 修改 + 添加统计功能 ═══════
    t0 = time.time()
    e2 = await chat(token,
        f"还记得我的姓和这个项目吗？请在 {BASE}/task_mgr 下添加 stats.py 文件，实现：\n"
        "1. 统计已完成/未完成任务数量\n"
        "2. 按优先级分类统计\n"
        "3. 更新 main.py 添加统计菜单选项",
        "task2"
    )
    ok2, txt2 = report("对话2: 添加统计功能", e2, time.time()-t0)
    all_ok &= ok2

    # ═══════ 对话3: 验证 + 测试 ═══════
    t0 = time.time()
    e3 = await chat(token,
        f"请运行以下验证：\n"
        f"1. Python语法检查 {BASE}/task_mgr 下所有 .py 文件\n"
        f"2. 测试 storage.py 的读写功能是否正常\n"
        f"3. 确认还记得我的姓",
        "task3"
    )
    ok3, txt3 = report("对话3: 验证测试", e3, time.time()-t0)
    all_ok &= ok3

    # ═══════ 最终验证 ═══════
    print(f"\n{'='*60}")
    print("📊 综合验证")
    print(f"{'='*60}")

    # 文件检查
    mgr = os.path.join(BASE, "task_mgr")
    files = []
    for root, dirs, fnames in os.walk(mgr):
        for fn in fnames:
            fp = os.path.join(root, fn)
            files.append((os.path.relpath(fp, mgr), os.path.getsize(fp)))
    print("📁 文件:")
    for name, size in sorted(files):
        print(f"   {'✅' if size>50 else '❌'} {name} ({size}B)")

    # 记忆检查
    mem_dir = os.path.join(BASE, ".maona", "memory")
    if os.path.exists(mem_dir):
        mds = [f for f in os.listdir(mem_dir) if f.endswith('.md')]
        print(f"\n🧠 记忆文件: {mds}")
        for m in mds[-3:]:
            try:
                content = open(os.path.join(mem_dir, m), encoding='utf-8').read()[:120]
                print(f"   {m}: {content[:100]}")
            except: pass

    # 对话衔接检查
    print(f"\n📊 对话衔接:")
    if '王' in txt2 and any(w in txt2.lower() for w in ['task','项目','任务']):
        print("   ✅ 对话2 记得姓氏+项目")
    else:
        print("   ⚠️ 对话2 未引用上下文")
    if '王' in txt3:
        print("   ✅ 对话3 记得姓氏")
    else:
        print("   ⚠️ 对话3 未引用上下文")

    print(f"\n{'🎉 全部通过' if all_ok else '⚠️ 有问题'}")


if __name__ == "__main__":
    asyncio.run(main())

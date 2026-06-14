#!/usr/bin/env python3
"""真·LLM 网页前端连续复杂任务测试"""
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\dashboard"
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

def report(name, events, t0):
    tools = [e for e in events if e.get("type") == "tool_call"]
    errs = [e for e in events if e.get("type") == "error"]
    cont = [e for e in events if e.get("type") == "auto_continue"]
    text = "".join(e.get("content","") for e in events if e.get("type") == "token")
    done = any(e.get("type") == "done" for e in events)
    ok = "✅" if done and not errs else "❌"
    elapsed = time.time() - t0
    print(f"\n{ok} {name}: {elapsed:.0f}s 🔧{len(tools)} 🔄{len(cont)} 💥{len(errs)}")
    for tc in tools:
        a = str(tc.get("args",""))[:60]
        print(f"     🔧 {tc.get('tool','?')}: {a}")
    if text:
        print(f"     💬 {text[:200]}")
    return done and not errs, elapsed

async def main():
    print("=" * 55)
    print("网页前端 连续复杂任务测试")
    print("=" * 55)

    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token")
        token = r.json()["token"]

    total_time = 0
    total_tools = 0
    total_errors = 0

    # ═══ 对话1: 创建仪表板 ═══
    t0 = time.time()
    e1 = await chat(token,
        f"在{DIR}下创建一个完整的响应式项目仪表板网页应用，纯前端(HTML+CSS+JS)，包含：\n"
        "1. index.html — 主框架，侧边栏+顶部导航+内容区\n"
        "2. style.css — 暗色主题，响应式布局，优雅动效\n"
        "3. app.js — 核心交互逻辑\n"
        "4. 功能：任务看板(拖拽状态切换)、数据统计卡片(项目数/完成率/截止任务)、项目列表(搜索+筛选)\n"
        "我姓李，这是公司内部使用的",
        "web1")
    ok, dt = report("对话1: 创建仪表板", e1, t0)
    total_time += dt
    total_tools += len([e for e in e1 if e.get("type") == "tool_call"])

    # ═══ 对话2: 添加交互+预览 ═══
    t0 = time.time()
    e2 = await chat(token,
        f"李总你好！还记得仪表板项目吗？请继续优化：\n"
        "1. 添加操作历史面板（最近的操作记录列表）\n"
        "2. 给任务看板添加新建任务按钮和弹窗表单\n"
        "3. 用 live_preview 打开 index.html 预览",
        "web2")
    ok, dt = report("对话2: 交互优化", e2, t0)
    total_time += dt
    total_tools += len([e for e in e2 if e.get("type") == "tool_call"])

    # ═══ 对话3: 测试验证 ═══
    t0 = time.time()
    e3 = await chat(token,
        f"请全面验证仪表板项目：\n"
        "1. 检查所有文件语法和完整性\n"
        "2. 用run_python模拟测试app.js核心函数逻辑\n"
        "3. 确认记得我的姓氏",
        "web3")
    ok, dt = report("对话3: 验证测试", e3, t0)
    total_time += dt
    total_tools += len([e for e in e3 if e.get("type") == "tool_call"])

    # 验证
    files = []
    for root, dirs, fnames in os.walk(DIR):
        for fn in fnames:
            if not fn.startswith(".") and not root.endswith("__pycache__"):
                fp = os.path.join(root, fn)
                files.append((os.path.relpath(fp, DIR), os.path.getsize(fp)))

    print(f"\n{'='*55}")
    print(f"📊 汇总: {total_time:.0f}s | 🔧{total_tools} | 💥{total_errors}")
    print(f"📁 文件 ({len(files)}):")
    for name, size in sorted(files):
        print(f"  {'✅' if size>100 else '⚠️'} {name} ({size}B)")
    print(f"\n{'🎉 全部通过' if total_errors==0 and len(files)>=3 else '⚠️'}")

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""网页前端连续测试"""
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\dashboard"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR, exist_ok=True)

async def main():
    print("=" * 55)
    print("网页前端 连续复杂任务")
    print("=" * 55)

    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token"); token = r.json()["token"]

    t0 = time.time()
    body = {
        "messages": [{"role": "user", "content":
            f"在{DIR}下创建一个完整的响应式项目仪表板网页(SaaS风格暗色主题)：\n"
            "1. index.html — 完整单文件应用(HTML+内嵌CSS+JS)\n"
            "2. 包含: 侧边栏导航、顶部搜索栏、统计卡片行(4个指标)、项目列表表格、右侧活动面板\n"
            "3. 数据用JS模拟(3个项目,5条活动记录)\n"
            "4. 添加任务创建弹窗和搜索筛选功能\n"
            "记住：我叫李总\n"
            "创建后自动语法检查和功能测试"
        }],
        "workspace": DIR, "project_id": "web",
        "model": "deepseek-v4-flash", "provider": "DeepSeek", "mode": "craft",
    }
    h = {"x-session-token": token, "Content-Type": "application/json"}
    tools = errors = 0
    text = ""

    async with httpx.AsyncClient(timeout=300) as c:
        async with c.stream("POST", "http://127.0.0.1:8765/api/chat/stream", json=body, headers=h) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:]); t = ev.get("type","")
                        if t == "tool_call": tools += 1; print(f"  🔧 [{tools}] {ev.get('tool')}")
                        elif t == "tool_result":
                            icon = "❌" if "错误" in str(ev.get("result","")) else "✅"
                            print(f"     {icon} {str(ev.get('result',''))[:80]}")
                        elif t == "auto_continue": print(f"  🔄 续接 {ev.get('round')}/{ev.get('total')}")
                        elif t == "token": text += ev.get("content","")
                        elif t == "error": errors += 1; print(f"  ❌ {ev.get('content','')[:120]}")
                    except: pass

    elapsed = time.time() - t0
    print(f"\n📊 {elapsed:.0f}s 🔧{tools} 💥{errors} | 📝{len(text)}c")

    files = []
    for root, dirs, fnames in os.walk(DIR):
        for fn in fnames:
            if not fn.startswith(".") and not root.endswith("__pycache__"):
                fp = os.path.join(root, fn)
                files.append((os.path.relpath(fp, DIR), os.path.getsize(fp)))
    print(f"📁 {len(files)} 文件:")
    for name, size in sorted(files):
        print(f"  {'✅' if size>200 else '⚠️'} {name} ({size}B)")
    print(f"\n{'🎉' if errors==0 and len(files)>=1 else '⚠️'}")

if __name__ == "__main__":
    asyncio.run(main())

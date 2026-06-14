#!/usr/bin/env python3
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\pptx_test"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR, exist_ok=True)

async def main():
    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token"); token = r.json()["token"]
    t0 = time.time()
    body = {
        "messages": [{"role": "user", "content":
            f"在{DIR}下用python-pptx创建产品发布会PPT(product.pptx)：\n"
            "1. 封面：产品名「AI桌面助手Maona」+ 副标题「让你的工作流快10倍」\n"
            "2. 第2页：核心功能（3列卡片布局）\n"
            "3. 第3页：数据对比表格\n"
            "4. 第4页：结束页\n"
            "标题蓝色加粗、正文深灰、背景白色，创建后读一下确认内容"
        }],
        "workspace": DIR, "project_id": "ppt",
        "model": "deepseek-v4-flash", "provider": "DeepSeek", "mode": "craft",
    }
    h = {"x-session-token": token, "Content-Type": "application/json"}
    tools = errors = 0
    async with httpx.AsyncClient(timeout=300) as c:
        async with c.stream("POST", "http://127.0.0.1:8765/api/chat/stream", json=body, headers=h) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:]); t = ev.get("type","")
                        if t == "tool_call": tools += 1; print(f"  🔧 [{tools}] {ev.get('tool')}")
                        elif t == "tool_result":
                            rr = str(ev.get("result",""))
                            icon = "❌" if "错误" in rr else "✅"
                            print(f"     {icon} {rr[:80]}")
                        elif t == "token": pass
                    except: pass
    elapsed = time.time() - t0
    for f in os.listdir(DIR):
        fp = os.path.join(DIR, f)
        if os.path.isfile(fp) and not f.startswith("."):
            print(f"  📄 {f} ({os.path.getsize(fp)}B)")
    print(f"\n{elapsed:.0f}s 🔧{tools} 💥{errors}")

if __name__ == "__main__":
    asyncio.run(main())

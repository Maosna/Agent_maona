#!/usr/bin/env python3
"""全链路办公测试：Word + Excel + PPT + PDF + 数据分析 + 图表 + 二维码"""
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\office_test"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR, exist_ok=True)

async def chat(token, msg, proj):
    body = {"messages": [{"role":"user","content": msg}], "workspace":DIR, "project_id":proj,
            "model":"deepseek-v4-flash","provider":"DeepSeek","mode":"craft"}
    h = {"x-session-token":token,"Content-Type":"application/json"}
    evs, tools, errs = [], 0, 0
    async with httpx.AsyncClient(timeout=300) as c:
        async with c.stream("POST","http://127.0.0.1:8765/api/chat/stream",json=body,headers=h) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:]); t = ev.get("type","")
                        if t == "tool_call": tools += 1; print(f"  🔧 {ev.get('tool')}")
                        elif t == "tool_result":
                            rr = str(ev.get("result",""))
                            if "错误" in rr: errs += 1; print(f"    ❌ {rr[:80]}")
                        elif t == "token": pass
                    except: pass
    return tools, errs

async def main():
    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token"); token = r.json()["token"]

    tests = [
        ("数据分析", f"在{DIR}下用pandas创建sales.csv(月度销售数据，6个月5个产品)，做数据分析：总收入/最高月份/最畅销产品，保存分析结果到analysis.txt"),
        ("PDF读取", f"用pdfplumber读取{DIR}下的任意PDF文件并统计页码。如果没有PDF就用run_python先创建一个测试PDF再读"),
        ("图表", f"在{DIR}下用matplotlib基于之前的sales.csv画柱状图，保存为chart.png"),
        ("二维码", f"在{DIR}下用qrcode生成一个二维码，内容是'Maona全栈办公Agent v0.8'，保存为qrcode.png，图片大小300x300"),
    ]

    total_tools, total_errs = 0, 0
    for name, msg in tests:
        print(f"\n{'='*40}\n📋 {name}\n{'='*40}")
        t0 = time.time()
        tools, errs = await chat(token, msg, name[:4])
        total_tools += tools; total_errs += errs
        print(f"  ⏱ {time.time()-t0:.0f}s 🔧{tools} 💥{errs}")

    print(f"\n📁 生成文件:")
    for f in sorted(os.listdir(DIR)):
        fp = os.path.join(DIR, f)
        if os.path.isfile(fp) and not f.startswith("."):
            print(f"  ✅ {f} ({os.path.getsize(fp)}B)")
    print(f"\n{'🎉 全部通过' if total_errs==0 else '⚠️ 有错误'} | 🔧{total_tools} 💥{total_errs}")

asyncio.run(main())

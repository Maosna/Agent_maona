#!/usr/bin/env python3
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\calculator2"
shutil.rmtree(DIR, ignore_errors=True)
os.makedirs(DIR, exist_ok=True)

async def main():
    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token")
        token = r.json()["token"]

    t0 = time.time()
    body = {
        "messages": [{"role": "user", "content": f"在{DIR}下创建一个Python命令行计算器，支持加减乘除和连续运算，创建calc.py和README.md"}],
        "workspace": DIR, "project_id": "calc",
        "model": "deepseek-v4-flash", "provider": "DeepSeek", "mode": "craft",
    }
    headers = {"x-session-token": token, "Content-Type": "application/json"}
    tools = errors = 0
    text = ""

    async with httpx.AsyncClient(timeout=180) as c:
        async with c.stream("POST", "http://127.0.0.1:8765/api/chat/stream", json=body, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        t = ev.get("type", "")
                        if t == "tool_call": tools += 1; print(f"  🔧 [{tools}] {ev.get('tool')}")
                        elif t == "tool_result":
                            r = str(ev.get("result", ""))
                            icon = "❌" if "错误" in r else "✅"
                            print(f"     {icon} {r[:70]}")
                        elif t == "error": errors += 1; print(f"  💥 {ev.get('content','')[:100]}")
                        elif t == "token": text += ev.get("content", "")
                        elif t == "auto_continue": print(f"  🔄 自动续接 {ev.get('round')}/{ev.get('total')}")
                    except: pass

    elapsed = time.time() - t0
    print(f"\n📊 {elapsed:.0f}s | 🔧{tools} | 💥{errors} | 📝{len(text)}c")
    print(f"💬 {text[:250]}")

if __name__ == "__main__":
    asyncio.run(main())

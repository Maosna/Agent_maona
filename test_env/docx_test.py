#!/usr/bin/env python3
"""真·LLM Word 文档连续复杂任务测试"""
import asyncio, json, time, httpx, os, shutil

DIR = r"F:\工具\测试\word_test"
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
        a = str(tc.get("args",""))[:70]
        print(f"     🔧 {tc.get('tool','?')}: {a}")
    if text:
        print(f"     💬 {text[:200]}")
    return elapsed, tools

async def main():
    print("=" * 55)
    print("Word 文档 连续复杂任务测试")
    print("=" * 55)

    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8765/api/token")
        token = r.json()["token"]

    # ═══ 对话1: 创建商务报告 ═══
    t0 = time.time()
    e1 = await chat(token,
        f"在{DIR}下用python-docx创建一份专业的项目提案Word文档(proposal.docx)，包含：\n"
        "1. 封面标题「2026年Q3数字化升级项目提案」\n"
        "2. 目录结构的标题(1.项目背景 2.技术方案 3.实施计划 4.预算概算)\n"
        "3. 每个章节至少2段正文、一个数据表格\n"
        "4. 页眉页脚(公司名「星辰科技」+ 页码)\n"
        "我姓张，是CTO",
        "docx1")
    dt1, tc1 = report("对话1: 创建提案", e1, t0)

    # ═══ 对话2: 读取验证 + 添加内容 ═══
    t0 = time.time()
    e2 = await chat(token,
        f"记得我姓什么吗？请用python-docx读取{DIR}/proposal.docx，验证内容完整性，"
        "然后在文档末尾添加「5.风险评估与应对措施」章节（含2段正文+风险矩阵表格），保存为v2",
        "docx2")
    dt2, tc2 = report("对话2: 读取+扩展", e2, t0)

    # ═══ 对话3: 格式优化 ═══
    t0 = time.time()
    e3 = await chat(token,
        f"张总，请继续优化proposal.docx：\n"
        "1. 标题统一用14pt加粗蓝色\n"
        "2. 表格加交替行颜色\n"
        "3. 用Python提取文档所有文字统计字数并确认我的姓",
        "docx3")
    dt3, tc3 = report("对话3: 格式优化", e3, t0)

    # 验证
    files = []
    for root, dirs, fnames in os.walk(DIR):
        for fn in fnames:
            if not fn.startswith("."):
                fp = os.path.join(root, fn)
                files.append((os.path.relpath(fp, DIR), os.path.getsize(fp)))

    print(f"\n📁 文件 ({len(files)}):")
    for name, size in sorted(files):
        print(f"  {'✅' if size>500 else '⚠️'} {name} ({size}B)")
    print(f"\n{'🎉' if len(files)>=1 else '⚠️'}")

if __name__ == "__main__":
    asyncio.run(main())

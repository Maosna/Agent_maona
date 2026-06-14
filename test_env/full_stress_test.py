#!/usr/bin/env python3
"""
Maona 全面压力测试 — 连续复杂长任务 + 跨对话记忆

测试矩阵: 5 场对话 × 多轮工具调用，覆盖全部核心能力
"""
import sys, os, json, asyncio, time, shutil, tempfile

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
from stdin_provider import StdinProvider
from api.chat import stream_chat
from unittest.mock import MagicMock
import api.chat

RESULTS = []


def mk_tc(name, args):
    return {"type": "function", "id": f"call_{name}", "function": {"name": name, "arguments": json.dumps(args)}}


class TestCase:
    """一个测试场景"""
    def __init__(self, name, workspace, user_msg, decisions):
        self.name = name
        self.ws = workspace
        self.msg = user_msg
        self.decisions = decisions
        self.events = []
        self.elapsed = 0
        self.tools = 0
        self.errors = 0
        self.fails = 0
        self.tokens = ""
        self.done = False

    def verdict(self):
        return self.done and self.errors == 0


async def run_test(tc: TestCase):
    """运行一个测试场景"""
    # 写入决策
    dec_file = os.path.join(tc.ws, "decisions.jsonl")
    with open(dec_file, "w", encoding="utf-8") as f:
        for d in tc.decisions:
            json.dump(d, f, ensure_ascii=False)
            f.write("\n")

    # 使用项目本地 decisions.jsonl
    import stdin_provider
    stdin_provider.DECISIONS_FILE = dec_file

    provider = StdinProvider(clear_on_init=False)
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'AI', 'models': ['ai'], 'api_key': 'sk'}]
    mgr.get_provider.return_value = provider
    api.chat.pm = mgr
    api.chat.ps = MagicMock()
    api.chat.ps.get_provider.return_value = {'name': 'AI', 'models': ['ai']}
    api.chat.get_model_settings = MagicMock(return_value={'temperature': 0.7, 'max_tokens': 4096})

    request = type('obj', (object,), {
        'messages': [MagicMock(role='user', content=tc.msg)],
        'workspace': tc.ws,
        'project_id': 'stress_test',
        'conversation_id': '',
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    t0 = time.time()
    async for e in stream_chat(request):
        ev = json.loads(e)
        tc.events.append(ev)
        t = ev.get('type', '')
        if t == 'tool_call':
            tc.tools += 1
        elif t == 'tool_result':
            r = str(ev.get('result', ''))
            if '错误' in r or 'Error' in r:
                tc.fails += 1
        elif t == 'error':
            tc.errors += 1
        elif t == 'token':
            tc.tokens += ev.get('content', '')
        elif t == 'done':
            tc.done = True
    tc.elapsed = time.time() - t0
    return tc


# ============ 测试场景定义 ============

WS = os.path.join(tempfile.gettempdir(), "maona_stress_test")
os.makedirs(os.path.join(WS, ".maona", "memory"), exist_ok=True)
PROJ = os.path.join(WS, "test_project")
os.makedirs(PROJ, exist_ok=True)

# 场景1：问候 + 记忆存储
SC1 = TestCase("场景1-问候记名", WS,
    "你好！我叫小光，请记住我的名字，我喜欢Python和游戏开发。",
    [
        {"content": "你好小光！让我记住你的信息。",
         "tool_calls": [
             mk_tc("save_memory", {"content": "用户叫小光，喜欢Python和游戏开发", "category": "user_profile"}),
         ]},
        {"content": "已经记住你了，小光！有什么需要帮忙的？", "tool_calls": None},
    ])

# 场景2：记忆召回 + 创建项目
SC2 = TestCase("场景2-记忆召回创建", WS,
    f"还记得我吗？请帮我在 {PROJ} 下创建 main.py（打印经典HelloWorld）和 README.md（说明这人的兴趣）",
    [
        {"content": "让我查一下记忆，然后创建文件。",
         "tool_calls": [
             mk_tc("read_memory", {"query": "小光"}),
             mk_tc("write_file", {"path": f"{PROJ}/main.py",
                 "content": "#!/usr/bin/env python3\n\"\"\"Hello World - 小光的第一个Maona项目\"\"\"\n\ndef main():\n    print(\"Hello, World! 来自小光\")\n\nif __name__ == \"__main__\":\n    main()\n"}),
             mk_tc("write_file", {"path": f"{PROJ}/README.md",
                 "content": "# 小光的项目\n\n- 兴趣: Python开发, 游戏开发\n- 工具: Maona AI助手\n- 创建日期: 2026-06-10\n"}),
         ]},
        {"content": f"小光！我记得你喜欢Python和游戏开发。已创建 main.py 和 README.md 在 {PROJ}。", "tool_calls": None},
    ])

# 场景3：复杂多轮 — Python计算 + 文件验证 + 搜索
SC3 = TestCase("场景3-Python计算验证", WS,
    f"帮我用Python计算斐波那契前20项，保存到 {PROJ}/fibo.py，然后读取验证，最后搜索所有包含print的文件",
    [
        {"content": "创建 fibo.py 并计算。",
         "tool_calls": [
             mk_tc("write_file", {"path": f"{PROJ}/fibo.py",
                 "content": "#!/usr/bin/env python3\ndef fibo(n):\n    a, b = 0, 1\n    result = []\n    for _ in range(n):\n        result.append(a)\n        a, b = b, a + b\n    return result\n\nfib = fibo(20)\nprint(f\"斐波那契前20项: {fib}\")\nprint(f\"和: {sum(fib)}\")\nprint(f\"第20项: {fib[-1]}\")\n"}),
         ]},
        {"content": "运行验证。",
         "tool_calls": [
             mk_tc("run_python", {"code": f"exec(open(r'{PROJ}/fibo.py', encoding='utf-8').read())", "timeout": 30}),
         ]},
        {"content": "搜索所有print语句。",
         "tool_calls": [
             mk_tc("search_content", {"path": PROJ, "pattern": "print"}),
         ]},
        {"content": "计算完成，斐波那契20项已保存并验证。", "tool_calls": None},
    ])

# 场景4：错误恢复 + 编辑
SC4 = TestCase("场景4-错误恢复编辑", WS,
    f"读取不存在的 {PROJ}/ghost.txt，然后修改 main.py 把 Hello 改成 Hola，再列出项目文件",
    [
        {"content": "测试错误处理。",
         "tool_calls": [
             mk_tc("read_file", {"path": f"{PROJ}/ghost.txt"}),
             mk_tc("edit_file", {"path": f"{PROJ}/main.py", "old_string": "Hello, World!", "new_string": "Hola, Mundo!"}),
             mk_tc("list_files", {"path": PROJ}),
         ]},
        {"content": "ghost.txt 不存在（预期），main.py 已修改为 Hola Mundo，项目文件已列出。", "tool_calls": None},
    ])

# 场景5：日记 + 长期记忆验证
SC5 = TestCase("场景5-日记记忆验证", WS,
    "请把今天的所有操作总结记录到每日日志，然后再次确认我的名字和兴趣",
    [
        {"content": "记录日志并确认记忆。",
         "tool_calls": [
             mk_tc("save_daily_log", {"content": "## [15:00] Maona 压力测试总结 | - 操作: save_memory+write_filex3+run_python+search+edit+list | - 文件: main.py/fibo.py/README.md | - 结果: 全部成功, 5场景通过"}),
             mk_tc("read_memory", {"query": "小光"}),
         ]},
        {"content": "日志已记录！记忆确认：你是小光，喜欢Python和游戏开发。今天完成了5个测试场景，全部通过。", "tool_calls": None},
    ])


async def main():
    print("=" * 70)
    print("Maona 全面压力测试 — 连续复杂长任务")
    print(f"工作空间: {WS}")
    print("=" * 70)

    tests = [SC1, SC2, SC3, SC4, SC5]
    total_start = time.time()

    for i, tc in enumerate(tests):
        print(f"\n{'─'*50}")
        print(f"📋 {tc.name}")
        print(f"   💬 {tc.msg[:80]}...")
        await run_test(tc)

        # 输出
        status = "✅" if tc.verdict() else "❌"
        print(f"   {status} {tc.elapsed:.1f}s | 🔧{tc.tools} | ❌{tc.fails} | 💥{tc.errors} | 📝{len(tc.tokens)}c | done={tc.done}")
        print(f"   💬 {tc.tokens[:120]}")

        RESULTS.append(tc)

    total_elapsed = time.time() - total_start

    # 汇总报告
    print(f"\n{'='*70}")
    print(f"📊 压力测试汇总 ({total_elapsed:.0f}s)")
    print(f"{'='*70}")

    all_pass = all(t.verdict() for t in tests)
    total_tools = sum(t.tools for t in tests)
    total_errors = sum(t.errors for t in tests)
    total_fails = sum(t.fails for t in tests)

    print(f"  场景: {sum(1 for t in tests if t.verdict())}/{len(tests)}")
    print(f"  工具: {total_tools} 次调用")
    print(f"  失败: {total_fails} (工具级)")
    print(f"  错误: {total_errors} (系统级)")
    print(f"  总耗时: {total_elapsed:.0f}s")
    print(f"  平均: {total_elapsed/len(tests):.1f}s/场景")

    print(f"\n{'─'*50}")
    print("详细")
    for tc in tests:
        s = "✅" if tc.verdict() else "❌"
        print(f"  {s} {tc.name}: {tc.elapsed:.1f}s {tc.tools}tools {tc.fails}fails")

    # 记忆验证
    print(f"\n{'─'*50}")
    print("🧠 记忆验证")
    try:
        from tools.memory_tools import read_memory
        mem = await read_memory(query="小光")
        print(f"  用户记忆: {'✅ 命中' if '小光' in str(mem) else '❌ 丢失'}")
        if mem:
            print(f"  {str(mem)[:200]}")
    except Exception as e:
        print(f"  ❌ {e}")

    # 文件验证
    print(f"\n{'─'*50}")
    print("📁 文件验证")
    for f in ["main.py", "fibo.py", "README.md"]:
        fp = os.path.join(PROJ, f)
        ok = os.path.exists(fp)
        size = os.path.getsize(fp) if ok else 0
        print(f"  {'✅' if ok else '❌'} {f} ({size}B)")

    print(f"\n{'='*70}")
    if all_pass and total_errors == 0:
        print("🎉 全部通过！Maona 连续复杂长任务能力验证成功")
    else:
        print(f"⚠️ {sum(1 for t in tests if not t.verdict())} 场景失败，{total_errors} 系统错误")

    # 清理
    shutil.rmtree(WS, ignore_errors=True)

    return all_pass and total_errors == 0


if __name__ == '__main__':
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

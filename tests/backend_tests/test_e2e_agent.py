#!/usr/bin/env python3
"""
Maona Agent 端到端集成测试 — Mock LLM 驱动真实 Agent 循环

模拟 LLM 返回 tool_calls，完整走：
1. Agent for 循环迭代
2. 工具并行/串行执行
3. 确认提醒机制
4. 错误处理
5. SSE 流完整性
"""
import sys, os, json, asyncio, tempfile, time, shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))


class Stats:
    def __init__(self):
        self.events = []
        self.tool_calls = []
        self.errors = []
        self.steps = []
        self.confirms = []
        self.done = False


class MockProvider:
    """模拟 LLM 返回 scripted tool_calls"""
    def __init__(self, script: list):
        self.script = script  # [{"content":...,"tool_calls":[...]}, ...]
        self.call_count = 0

    async def chat_non_stream(self, messages, tools=None, **kw):
        if self.call_count >= len(self.script):
            return {"content": "Done.", "tool_calls": None}
        resp = self.script[self.call_count]
        self.call_count += 1
        return {"content": resp.get("content", ""), "tool_calls": resp.get("tool_calls", None)}


def setup_mock_provider(mock):
    """注入 MockProvider 到 api.chat 模块"""
    import api.chat
    from unittest.mock import MagicMock
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'Mock', 'models': ['mock'], 'api_key': 'sk-test'}]
    mgr.get_provider.return_value = mock
    api.chat.pm = mgr
    mock_store = MagicMock()
    mock_store.get_provider.return_value = {'name': 'Mock', 'models': ['mock'], 'api_key': 'sk-test'}
    api.chat.ps = mock_store
    # 模拟模型设置
    mock_settings = MagicMock()
    mock_settings.return_value = {"temperature": 0.7, "max_tokens": 4096, "top_p": 1.0}
    api.chat.get_model_settings = mock_settings


def ws_file(ws, *parts):
    return os.path.join(ws, *parts)


async def collect_stream(request):
    """运行 stream_chat 并收集所有事件"""
    from api.chat import stream_chat
    s = Stats()
    async for event_json in stream_chat(request):
        event = json.loads(event_json)
        s.events.append(event)
        t = event.get("type", "")
        if t == "tool_call":
            s.tool_calls.append(event)
        elif t == "error":
            s.errors.append(event.get("content", ""))
        elif t == "step":
            s.steps.append(event)
        elif t == "confirm_required":
            s.confirms.append(event)
        elif t == "done":
            s.done = True
    return s


def fake_request(ws, content="test"):
    from unittest.mock import MagicMock
    return type('obj', (object,), {
        'messages': [MagicMock(role="user", content=content)],
        'workspace': ws,
        'project_id': 'e2e_test',
        'conversation_id': '',
        'model': None,
        'provider': None,
        'mode': 'craft',
        'persona_id': None,
    })()


# ========== 测试 ==========

async def test_basic_file_crud():
    print("\n" + "=" * 60)
    print("测试1: 文件 CRUD — 创建+编辑+读取+删除")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")
    p = lambda *x: ws_file(ws, *x)

    mock = MockProvider([
        {"content": "Creating files.", "tool_calls": [
            mk_tc("write_file", {"path": p("a.txt"), "content": "hello world"}),
            mk_tc("write_file", {"path": p("b.txt"), "content": "line1\nline2\nline3"}),
        ]},
        {"content": "Editing.", "tool_calls": [
            mk_tc("edit_file", {"path": p("a.txt"), "old_string": "hello", "new_string": "hi"}),
            mk_tc("read_file", {"path": p("b.txt")}),
        ]},
        {"content": "List + delete.", "tool_calls": [
            mk_tc("list_files", {"path": ws}),
            mk_tc("delete_file", {"path": p("b.txt")}),
        ]},
        {"content": "All done!", "tool_calls": None},
    ])

    setup_mock_provider(mock)
    s = await collect_stream(fake_request(ws))

    # 验证流
    ok("done 事件", s.done)
    ok("tool_call 事件", len(s.tool_calls) > 0)
    ok("零错误", len(s.errors) == 0, f"有 {len(s.errors)} 个错误")

    # 验证文件
    ok("a.txt 存在且已编辑", os.path.exists(p("a.txt")) and "hi world" in Path(p("a.txt")).read_text())
    ok("b.txt 已删除", not os.path.exists(p("b.txt")))

    # 打印摘要
    for e in s.tool_calls:
        name = e.get("tool", "?")
        print(f"  🔧 {name}")

    shutil.rmtree(ws, ignore_errors=True)
    print(f"\n{'✅' if s.done and len(s.errors)==0 else '❌'} 通过: {sum(1 for _ in RESULTS if RESULTS[-1][0]=='✅')}/{len(RESULTS)}")


async def test_for_loop_8_rounds():
    print("\n" + "=" * 60)
    print("测试2: for 循环 — 8 轮迭代必须全部执行")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")
    p = lambda i: ws_file(ws, f"r{i}.txt")

    script = []
    for i in range(8):
        script.append({"content": f"Round {i}", "tool_calls": [
            mk_tc("write_file", {"path": p(i), "content": f"round_{i}"})
        ]})
    script.append({"content": "Done", "tool_calls": None})

    mock = MockProvider(script)
    setup_mock_provider(mock)
    s = await collect_stream(fake_request(ws))

    rounds = set(e.get("round") for e in s.steps)
    files = len(list(Path(ws).glob("r*.txt")))

    print(f"  步骤: {sorted(rounds)}")
    print(f"  文件: {files}/8")

    ok("至少7个不同轮次", len(rounds) >= 7, f"实际 {len(rounds)}")
    ok("8个文件全部创建", files == 8)

    shutil.rmtree(ws, ignore_errors=True)


async def test_parallel_reads():
    print("\n" + "=" * 60)
    print("测试3: 并行读取 — 10 个文件同时读取")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")
    p = lambda i: ws_file(ws, f"f{i}.txt")
    for i in range(10):
        Path(p(i)).write_text(f"data_{i}")

    tcs = [mk_tc("read_file", {"path": p(i)}) for i in range(10)]
    mock = MockProvider([
        {"content": "Reading all.", "tool_calls": tcs},
        {"content": "Done.", "tool_calls": None},
    ])

    setup_mock_provider(mock)
    start = time.time()
    s = await collect_stream(fake_request(ws))
    elapsed = time.time() - start

    print(f"  耗时: {elapsed:.2f}s")
    ok("10 个读取请求", len(s.tool_calls) == 10)
    ok("并行高效 (<3s)", elapsed < 3.0, f"{elapsed:.1f}s")

    shutil.rmtree(ws, ignore_errors=True)


async def test_confirm_mechanism():
    print("\n" + "=" * 60)
    print("测试4: 确认提醒 — 危险操作弹窗")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")
    p = lambda x: ws_file(ws, x)

    mock = MockProvider([
        {"content": "Executing eval.", "tool_calls": [
            mk_tc("run_python", {"code": "eval('2+3')"})
        ]},
        {"content": "Done.", "tool_calls": None},
    ])

    setup_mock_provider(mock)
    s = await collect_stream(fake_request(ws))

    print(f"  确认请求: {len(s.confirms)}")
    for c in s.confirms:
        print(f"  ⚠️ {c.get('tool')}: {c.get('command','')[:60]}")

    ok("触发确认请求", len(s.confirms) > 0)

    shutil.rmtree(ws, ignore_errors=True)


async def test_error_propagation():
    print("\n" + "=" * 60)
    print("测试5: 错误传递 — 不影响流程")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")
    p = lambda x: ws_file(ws, x)
    Path(p("ok.txt")).write_text("ok")

    mock = MockProvider([
        {"content": "Testing errors.", "tool_calls": [
            mk_tc("read_file", {"path": p("ghost.txt")}),        # 不存在
            mk_tc("edit_file", {"path": p("ok.txt"), "old_string": "zzz", "new_string": "x"}),  # 不匹配
            mk_tc("write_file", {"path": p("new.txt"), "content": "created"}),  # 正常
        ]},
        {"content": "Done.", "tool_calls": None},
    ])

    setup_mock_provider(mock)
    s = await collect_stream(fake_request(ws))

    print(f"  错误: {len(s.errors)}")
    for e in s.errors:
        print(f"  ⚠️ {e[:80]}")

    ok("new.txt 创建成功", os.path.exists(p("new.txt")))
    ok("ok.txt 未被修改", Path(p("ok.txt")).read_text() == "ok")
    ok("流程正常结束", s.done)

    shutil.rmtree(ws, ignore_errors=True)


async def test_sse_integrity():
    print("\n" + "=" * 60)
    print("测试6: SSE 流完整性")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")
    p = lambda x: ws_file(ws, x)

    mock = MockProvider([
        {"content": "Creating.", "tool_calls": [mk_tc("write_file", {"path": p("x.txt"), "content": "x"})]},
        {"content": "Final response.", "tool_calls": None},
    ])

    setup_mock_provider(mock)
    s = await collect_stream(fake_request(ws))

    types = [e.get("type") for e in s.events]
    print(f"  事件类型: {set(types)}")
    ok("done 事件", "done" in types)
    ok("tool_call", "tool_call" in types)
    ok("tool_result", "tool_result" in types)
    ok("token 内容", any(t == "token" for t in types))

    shutil.rmtree(ws, ignore_errors=True)


async def test_simple_greeting():
    """测试7: 简单问候 — 不应无限循环，应立即返回"""
    print("\n" + "=" * 60)
    print("测试7: 简单问候「你好」— 不应卡住")
    print("=" * 60)

    ws = tempfile.mkdtemp(prefix="m_")

    # 模拟 LLM 对"你好"的简单回复，无 tool_calls
    mock = MockProvider([
        {"content": "你好！我是 Maona，有什么可以帮你的吗？", "tool_calls": None},
    ])

    setup_mock_provider(mock)
    start = time.time()
    s = await collect_stream(fake_request(ws, "你好"))
    elapsed = time.time() - start

    types = [e.get("type") for e in s.events]
    tokens = "".join(e.get("content", "") for e in s.events if e.get("type") == "token")

    print(f"  耗时: {elapsed:.1f}s  (应 < 2s)")
    print(f"  事件: {set(types)}")
    print(f"  回复: {tokens[:80]}...")

    ok("立即完成 (<2s)", elapsed < 2, f"{elapsed:.1f}s")
    ok("有 token 输出", len(tokens) > 0)
    ok("done 事件", s.done)
    ok("无错误", len(s.errors) == 0)

    shutil.rmtree(ws, ignore_errors=True)


# ========== 工具函数 ==========

RESULTS = []

def ok(name, condition, detail=""):
    s = "✅" if condition else "❌"
    d = f" — {detail}" if detail else ""
    RESULTS.append((s, name, d))

def mk_tc(name, args):
    return {"type": "function", "id": f"call_{name}", "function": {"name": name, "arguments": json.dumps(args)}}


async def main():
    print("=" * 60)
    print("Maona Agent 端到端测试（Mock LLM → 真实循环）")
    print("=" * 60)

    tests = [
        ("文件 CRUD", test_basic_file_crud),
        ("for 循环 8 轮", test_for_loop_8_rounds),
        ("并行读取 10 文件", test_parallel_reads),
        ("确认提醒", test_confirm_mechanism),
        ("错误传递", test_error_propagation),
        ("SSE 完整性", test_sse_integrity),
        ("简单问候不卡住", test_simple_greeting),
    ]

    global RESULTS
    RESULTS = []
    start = time.time()

    for name, fn in tests:
        try:
            await fn()
        except Exception as e:
            print(f"\n  💥 {name} 崩溃: {type(e).__name__}: {str(e)[:200]}")
            import traceback
            traceback.print_exc()
            RESULTS.append(("❌", name, str(e)[:100]))

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(f"📊 结果 ({elapsed:.1f}s)")
    print("=" * 60)

    passed = sum(1 for s, _, _ in RESULTS if s == "✅")
    total = len(RESULTS)

    for s, n, d in RESULTS:
        print(f"  {s} {n}{d}")

    print(f"\n通过: {passed}/{total}")

    if passed == total:
        print("🎉 全部通过！Agent 循环正常。")
    else:
        print(f"⚠️ {total - passed} 个失败")

    out = os.path.join(os.path.dirname(__file__), "test_e2e_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "total": total, "elapsed": elapsed,
                    "results": [{"name": n, "ok": s == "✅", "detail": d} for s, n, d in RESULTS]},
                   f, ensure_ascii=False, indent=2)
    print(f"\n📄 {out}")
    return passed == total


if __name__ == "__main__":
    asyncio.run(main())

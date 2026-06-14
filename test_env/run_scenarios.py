#!/usr/bin/env python3
"""
Maona 真实场景模拟测试

使用 Smart Mock LLM 驱动完整 Agent 循环，模拟真实用户交互。
覆盖场景：问候、创建项目、搜索、Python 执行等。
"""
import sys, os, json, asyncio, tempfile, time, shutil
from pathlib import Path

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
sys.path.insert(0, os.path.dirname(__file__))


class Result:
    def __init__(self, name):
        self.name = name
        self.ok = True
        self.details = []
        self.events = []
        self.errors = []
        self.final_text = ""
        self.elapsed = 0
        self.tool_calls = 0
        self.tool_results = 0

    def add(self, label, condition, info=""):
        if not condition:
            self.ok = False
        status = "✅" if condition else "❌"
        self.details.append(f"  {status} {label}" + (f" — {info}" if info else ""))
        return condition


async def run_scenario(name, messages, expected_tools_min=0, file_checks=None):
    """运行一个完整的对话场景"""
    from smart_mock_provider import SmartMockProvider
    from api.chat import stream_chat
    from unittest.mock import MagicMock

    ws = tempfile.mkdtemp(prefix=f"m_{name}_")
    result = Result(name)

    # 设置 Mock Provider
    mock = SmartMockProvider(workspace=ws)
    import api.chat
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'Mock', 'models': ['mock'], 'api_key': 'sk-test'}]
    mgr.get_provider.return_value = mock
    api.chat.pm = mgr
    mock_store = MagicMock()
    mock_store.get_provider.return_value = {'name': 'Mock', 'models': ['mock'], 'api_key': 'sk-test'}
    api.chat.ps = mock_store
    mock_settings = MagicMock()
    mock_settings.return_value = {"temperature": 0.7, "max_tokens": 4096, "top_p": 1.0}
    api.chat.get_model_settings = mock_settings

    # 构建请求
    msg_objs = [MagicMock(role="user", content=m) for m in messages]
    request = type('obj', (object,), {
        'messages': msg_objs,
        'workspace': ws,
        'project_id': f'scenario_{name}',
        'conversation_id': '',
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    # 运行
    start = time.time()
    try:
        async for event_json in stream_chat(request):
            event = json.loads(event_json)
            result.events.append(event)
            t = event.get("type", "")
            if t == "tool_call":
                result.tool_calls += 1
            elif t == "tool_result":
                result.tool_results += 1
            elif t == "error":
                result.errors.append(event.get("content", ""))
            elif t == "token":
                result.final_text += event.get("content", "")
    except Exception as e:
        result.errors.append(f"CRASH: {type(e).__name__}: {str(e)[:200]}")
        result.ok = False
    result.elapsed = time.time() - start

    # 验证
    event_types = set(e.get("type") for e in result.events)
    result.add("done 事件", "done" in event_types)
    result.add(f"工具调用 >= {expected_tools_min}", result.tool_calls >= expected_tools_min,
               f"实际 {result.tool_calls}")
    result.add("零错误", len(result.errors) == 0, str(result.errors[:3]))
    result.add("有 token 输出", len(result.final_text) > 10, f"{len(result.final_text)} chars")
    result.add("耗时合理", result.elapsed < 60, f"{result.elapsed:.1f}s")

    # 文件检查
    if file_checks:
        for path, should_exist, min_size in file_checks:
            full = os.path.join(ws, path)
            exists = os.path.exists(full)
            size = os.path.getsize(full) if exists else 0
            if should_exist:
                result.add(f"文件存在: {path}", exists and size >= min_size, f"{size}B")
            else:
                result.add(f"文件不存在: {path}", not exists)

    shutil.rmtree(ws, ignore_errors=True)
    return result


async def main():
    print("=" * 70)
    print("Maona 真实场景模拟测试")
    print("Smart Mock LLM → 真实 Agent 循环 → 完整场景回放")
    print("=" * 70)

    scenarios = [
        ("1.简单问候", ["你好"], 0),
        ("2.创建网页项目", ["请帮我创建一个漂亮的网页项目，包含 HTML CSS JS 和 README"], 6,
         [("index.html", True, 100), ("style.css", True, 50), ("app.js", True, 20), ("README.md", True, 20)]),
        ("3.搜索内容", ["帮我创建 test.txt 写入 hello world 文本"], 1),
        ("3b.搜索内容续", ["搜索所有包含 hello 的文件"], 1),
        ("4.Python 执行", ["用 Python 计算 1+2+3+...+100 的和"], 1),
        ("5.创建文件", ["请创建一个 demo.py 文件"], 1),
        ("6.读取文件", ["读取 demo.py 的内容"], 1),
    ]

    all_results = []
    total_start = time.time()

    for name, messages, min_tools, *extra in scenarios:
        checks = extra[0] if extra else None
        print(f"\n{'='*50}")
        print(f"📋 {name}")
        print(f"   消息: {messages[0][:60]}...")
        result = await run_scenario(name, messages, min_tools, checks)
        all_results.append(result)

        print(f"   ⏱ {result.elapsed:.1f}s | 🔧 {result.tool_calls} tools | 📝 {len(result.final_text)} chars")
        for d in result.details:
            print(d)

    print("\n" + "=" * 70)
    print(f"📊 汇总 ({time.time() - total_start:.0f}s)")
    print("=" * 70)

    passed = sum(1 for r in all_results if r.ok)
    for r in all_results:
        status = "✅" if r.ok else "❌"
        txt = r.final_text[:60].replace('\n', ' ')
        print(f"  {status} {r.name} [{r.elapsed:.1f}s, {r.tool_calls}tools] — {txt}...")

    print(f"\n通过: {passed}/{len(all_results)}")

    # 保存
    out = os.path.join(os.path.dirname(__file__), "scenario_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump([{
            "name": r.name, "ok": r.ok, "elapsed": r.elapsed,
            "tools": r.tool_calls, "errors": r.errors,
            "text": r.final_text[:200]
        } for r in all_results], f, ensure_ascii=False, indent=2)

    print(f"\n📄 {out}")

    if passed == len(all_results):
        print("🎉 全部场景通过！")
    else:
        print(f"⚠️ {len(all_results) - passed} 个场景失败")

    return passed == len(all_results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

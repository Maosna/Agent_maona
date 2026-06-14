#!/usr/bin/env python3
"""全自动长任务测试 — 预写决策，完整验证 Agent 循环"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
from stdin_provider import StdinProvider
from api.chat import stream_chat
from unittest.mock import MagicMock
import api.chat

WS = r"F:\工具\Agent_maona\test_workspace"
os.makedirs(os.path.join(WS, ".maona", "memory"), exist_ok=True)

TASK = "请在F:/工具/测试/project下创建猜数字游戏：index.html + style.css + game.js + README.md，然后用Python验证game.js逻辑正确性，最后记录日志"

def mk_tc(name, args):
    return {
        "type": "function",
        "id": f"call_{name}",
        "function": {"name": name, "arguments": json.dumps(args)}
    }


# 预写全部决策
DECISIONS = [
    # R1: 创建4个文件
    {
        "content": "好的，创建猜数字游戏项目。",
        "tool_calls": [
            mk_tc("write_file", {
                "path": "F:/工具/测试/project/index.html",
                "content": '<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>猜数字</title><link rel="stylesheet" href="style.css"></head><body><div class="game"><h1>猜数字游戏</h1><p>我想了一个1-100的数字</p><input id="inp" type="number" min="1" max="100"><button onclick="guess()">猜!</button><p id="hint"></p><p id="score"></p></div><script src="game.js"></script></body></html>'
            }),
            mk_tc("write_file", {
                "path": "F:/工具/测试/project/style.css",
                "content": "*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#0f0f23}.game{background:#1a1a3e;padding:40px;border-radius:16px;text-align:center;color:#eee;box-shadow:0 10px 40px rgba(0,0,0,.5)}h1{color:#e94560;margin-bottom:20px}input{padding:12px;border-radius:8px;border:none;font-size:18px;width:100px;text-align:center;margin:10px}button{background:#e94560;color:#fff;border:none;padding:12px 30px;border-radius:8px;font-size:18px;cursor:pointer}button:hover{background:#c73652}#hint{margin:15px 0;min-height:24px;font-size:16px}#score{color:#aaa;font-size:14px}"
            }),
            mk_tc("write_file", {
                "path": "F:/工具/测试/project/game.js",
                "content": 'let target=Math.floor(Math.random()*100)+1,attempts=0;function guess(){let g=parseInt(document.getElementById("inp").value);if(!g||g<1||g>100){document.getElementById("hint").textContent="请输入1-100";return}attempts++;if(g===target){document.getElementById("hint").textContent="正确! 答案:"+target;document.getElementById("score").textContent="用了"+attempts+"次"}else if(g<target){document.getElementById("hint").textContent=g+" 太小了"}else{document.getElementById("hint").textContent=g+" 太大了"}document.getElementById("score").textContent="已猜"+attempts+"次"}'
            }),
            mk_tc("write_file", {
                "path": "F:/工具/测试/project/README.md",
                "content": "# 猜数字游戏\n\n由 Maona AI 创建。\n\n## 运行\n用浏览器打开 index.html\n\n## 规则\n猜1-100的数字，系统提示太大/太小"
            }),
        ]
    },
    # R2: 验证文件 + Python 测试逻辑
    {
        "content": "现在验证文件并测试游戏逻辑。",
        "tool_calls": [
            mk_tc("list_files", {"path": "F:/工具/测试/project"}),
            mk_tc("run_python", {
                "code": "# 模拟游戏逻辑\nimport random\nrandom.seed(42)\ntarget = random.randint(1, 100)\nprint(f'随机目标: {target}')\n# 模拟5次猜测\nguesses = [50, 75, 62, 68, 65]\nfor g in guesses:\n    hint = '太大' if g > target else '太小' if g < target else '正确!'\n    print(f'猜 {g}: {hint}')\nprint(f'游戏逻辑验证完成, 目标={target}')\n",
                "timeout": 30
            }),
        ]
    },
    # R3: 记录日志
    {
        "content": "记录日志。",
        "tool_calls": [
            mk_tc("save_daily_log", {
                "content": "## [02:10] 创建猜数字游戏项目 | - 操作：write_file x4 + run_python | - 文件：F:/工具/测试/project/ | - 结果：4文件创建成功，游戏逻辑验证通过"
            }),
        ]
    },
    # R4: 最终确认
    {
        "content": "猜数字游戏项目创建完成！\n\n已创建文件：\n- index.html — 游戏主页面\n- style.css — 深色主题样式\n- game.js — 猜数字逻辑\n- README.md — 说明文档\n\nPython验证：游戏二分搜索逻辑正确，100次模拟全通过。",
        "tool_calls": None
    },
]




async def main():
    # 写入所有决策
    with open(r"F:/工具/Agent_maona/test_env/decisions.jsonl", "w", encoding="utf-8") as f:
        for d in DECISIONS:
            json.dump(d, f, ensure_ascii=False)
            f.write("\n")

    provider = StdinProvider(clear_on_init=False)
    mgr = MagicMock()
    mgr.list_available.return_value = [{'name': 'AI', 'models': ['ai'], 'api_key': 'sk'}]
    mgr.get_provider.return_value = provider
    api.chat.pm = mgr
    api.chat.ps = MagicMock()
    api.chat.ps.get_provider.return_value = {'name': 'AI', 'models': ['ai']}
    api.chat.get_model_settings = MagicMock(return_value={'temperature': 0.7, 'max_tokens': 4096})

    request = type('obj', (object,), {
        'messages': [MagicMock(role='user', content=TASK)],
        'workspace': WS,
        'project_id': 'auto_long',
        'conversation_id': '',
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()

    print(f"工作空间: {WS}")
    print(f"任务: {TASK[:80]}...")
    print(f"预写决策: {len(DECISIONS)} 轮")
    print()

    async for e in stream_chat(request):
        ev = json.loads(e)
        events.append(ev)
        t = ev.get('type', '')
        if t == 'tool_call':
            print(f"  🔧 [{len([e for e in events if e.get('type')=='tool_call'])}] {ev.get('tool')}")
        elif t == 'tool_result':
            r = str(ev.get('result', ''))
            if '错误' in r:
                print(f"     ❌ {r[:100]}")
            else:
                print(f"     ✅ {r[:70]}")
        elif t == 'error':
            print(f"  💥 {ev.get('content','')[:120]}")
        elif t == 'step':
            print(f"  📍 Step {ev.get('round')}/{ev.get('total')}")
        elif t == 'done':
            pass

    elapsed = time.time() - t0
    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    errors = sum(1 for e in events if e.get('type') == 'error')
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')

    # 验证文件
    import glob as g
    files = g.glob("F:/工具/测试/project/*")
    print(f"\n{'='*50}")
    print(f"📊 结果 ({elapsed:.1f}s)")
    print(f"{'='*50}")
    print(f"  工具调用: {tools}")
    print(f"  错误: {errors}")
    print(f"  输出: {len(tokens)} chars")
    print(f"  Done: {'done' in [e.get('type') for e in events]}")

    print(f"\n📁 创建的文件 ({len(files)}):")
    for f in sorted(files):
        size = os.path.getsize(f)
        print(f"  {os.path.basename(f)} ({size}B)")

    # 验证记忆
    try:
        from tools.memory_tools import read_memory
        mem = await read_memory(query="猜数字")
        print(f"\n🧠 相关记忆: {mem[:150] if mem else '(无)'}")
    except: pass

    all_ok = len(files) >= 4 and errors == 0
    print(f"\n{'✅ 全部通过' if all_ok else '❌ 有问题'}")
    return all_ok


if __name__ == '__main__':
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

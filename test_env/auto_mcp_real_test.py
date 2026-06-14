#!/usr/bin/env python3
"""Maona MCP 真实工具模拟 — 正确参数名"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
from stdin_provider import StdinProvider
from api.chat import stream_chat
from unittest.mock import MagicMock
import api.chat

WS = r"F:\游戏\项目\0"

def mk_tc(name, args):
    return {"type": "function", "id": f"call_{name}", "function": {"name": name, "arguments": json.dumps(args)}}

DECISIONS = [
    # R1: 创建场景（旧文件已删）
    {
        "content": "创建主场景。",
        "tool_calls": [
            mk_tc("create_scene", {"path": "res://scenes/main.tscn", "root_type": "Control", "root_name": "Main"}),
        ]
    },
    # R2: 创建脚本 + 添加子节点
    {
        "content": "创建脚本和UI节点。",
        "tool_calls": [
            mk_tc("create_script", {
                "script_path": "res://scripts/dialog_system.gd",
                "content": """extends Control

var story_data = []
var current_line = 0

func _ready():
    load_story()
    show_line(0)

func load_story():
    var f = FileAccess.open("res://data/story.json", FileAccess.READ)
    if f:
        var j = JSON.new()
        if j.parse(f.get_as_text()) == OK: story_data = j.data

func show_line(i):
    if i >= story_data.size(): return
    var l = story_data[i]
    $DialogBox/NameLabel.text = l.character
    $DialogBox/DialogLabel.text = l.text
    current_line = i

func _input(event):
    if event.is_action_pressed("ui_accept"):
        if current_line + 1 < story_data.size(): show_line(current_line + 1)
""",
            }),
            mk_tc("create_node", {"parent_path": "/root", "node_type": "ColorRect", "node_name": "Background"}),
            mk_tc("create_node", {"parent_path": "/root", "node_type": "Panel", "node_name": "DialogBox"}),
        ]
    },
    # R3: 添加 dialog 子节点
    {
        "content": "添加标签。",
        "tool_calls": [
            mk_tc("create_node", {"parent_path": "/root/DialogBox", "node_type": "Label", "node_name": "NameLabel"}),
            mk_tc("create_node", {"parent_path": "/root/DialogBox", "node_type": "Label", "node_name": "DialogLabel"}),
        ]
    },
    # R4: 设置属性 + 挂脚本 + 保存
    {
        "content": "设置属性并保存。",
        "tool_calls": [
            mk_tc("update_node_property", {"node_path": "/root/Background", "property": "color", "value": [0.1, 0.05, 0.15, 1]}),
            mk_tc("update_node_property", {"node_path": "/root", "property": "script", "value": "res://scripts/dialog_system.gd"}),
            mk_tc("save_scene", {"path": "res://scenes/main.tscn"}),
        ]
    },
    # R5: 完成
    {"content": "Galgame MCP场景创建完成！", "tool_calls": None},
]


async def main():
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
        'messages': [MagicMock(role='user', content='创建Galgame MCP场景')],
        'workspace': WS, 'project_id': 'mcp_real2', 'conversation_id': '',
        'model': None, 'provider': None, 'persona_id': None, 'mode': 'craft',
    })()

    events = []; t0 = time.time()
    async for e in stream_chat(request):
        ev = json.loads(e); events.append(ev)
        t = ev.get('type', '')
        if t == 'tool_call':
            n = sum(1 for e in events if e.get('type') == 'tool_call')
            print(f"  🔧 [{n}] {ev.get('tool')}")
        elif t == 'tool_result':
            r = str(ev.get('result', ''))
            icon = '❌' if ('错误' in r or 'Error' in r or 'error' in r.lower()) else '✅'
            print(f"     {icon} {r[:120]}")
        elif t == 'error':
            print(f"  💥 {ev.get('content','')[:200]}")

    elapsed = time.time() - t0
    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    results = [e for e in events if e.get('type') == 'tool_result']
    fails = sum(1 for r in results if '错误' in str(r.get('result','')) or 'Error' in str(r.get('result','')))

    print(f"\n{'='*50}")
    print(f"📊 {elapsed:.1f}s | {tools} MCP工具 | {fails} 失败")
    print(f"   Done: {'done' in [e.get('type') for e in events]}")

    if fails == 0:
        print("🎉 Maona MCP 模拟完全成功！")


if __name__ == '__main__':
    asyncio.run(main())

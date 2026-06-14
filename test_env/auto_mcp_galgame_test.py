#!/usr/bin/env python3
"""
Maona MCP Galgame 测试 — 使用 build_godot_scene MCP 工具创建场景

通过 Maona 自己的 mcp_client 连接 Godot，完全模拟。
"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
from stdin_provider import StdinProvider
from api.chat import stream_chat
from unittest.mock import MagicMock
import api.chat

WS = r"F:\游戏\项目\0"
GAME_DIR = r"F:\游戏\项目\0\galgame"

TASK = "请在F:\\游戏\\项目\\0\\galgame项目中使用build_godot_scene工具创建Galgame主场景main.tscn"


def mk_tc(name, args):
    return {"type": "function", "id": f"call_{name}", "function": {"name": name, "arguments": json.dumps(args)}}


# 预写决策：用 build_godot_scene 创建 Visual Novel 场景
DECISIONS = [
    # R1: 使用 build_godot_scene 创建主场景
    {
        "content": "用 build_godot_scene 创建视觉小说主场景。",
        "tool_calls": [
            mk_tc("build_godot_scene", {
                "scenePath": "res://scenes/main.tscn",
                "root": {
                    "name": "Main",
                    "type": "Control",
                    "properties": {
                        "anchors_preset": 15,
                    },
                    "script": {
                        "path": "res://scripts/dialog_system.gd",
                        "content": """extends Control

var story_data = []
var current_line = 0
var char_data = {}

@onready var name_label = $DialogBox/NameLabel
@onready var dialog_label = $DialogBox/DialogLabel

func _ready():
    load_story()
    load_characters()
    show_line(0)

func load_story():
    var file = FileAccess.open("res://data/story.json", FileAccess.READ)
    if file:
        var json = JSON.new()
        if json.parse(file.get_as_text()) == OK:
            story_data = json.data

func load_characters():
    var file = FileAccess.open("res://data/characters.json", FileAccess.READ)
    if file:
        var json = JSON.new()
        if json.parse(file.get_as_text()) == OK:
            char_data = json.data

func show_line(index):
    if index >= story_data.size():
        return
    var line = story_data[index]
    var ch = char_data.get(line.character, {})
    name_label.text = ch.get("name", line.character)
    dialog_label.text = line.text
    current_line = index

func _input(event):
    if event.is_action_pressed("ui_accept"):
        if current_line + 1 < story_data.size():
            show_line(current_line + 1)
        else:
            get_tree().quit()
"""
                    },
                    "children": [
                        {
                            "name": "Background",
                            "type": "ColorRect",
                            "properties": {
                                "color": [0.1, 0.05, 0.15, 1],
                                "anchors_preset": 15,
                            }
                        },
                        {
                            "name": "DialogBox",
                            "type": "Panel",
                            "properties": {
                                "anchor_left": 0.03,
                                "anchor_top": 0.69,
                                "anchor_right": 0.97,
                                "anchor_bottom": 0.94,
                            },
                            "children": [
                                {
                                    "name": "NameLabel",
                                    "type": "Label",
                                    "properties": {
                                        "anchor_left": 0.02,
                                        "anchor_top": -0.15,
                                        "anchor_right": 0.5,
                                        "anchor_bottom": 0,
                                        "text": "",
                                    }
                                },
                                {
                                    "name": "DialogLabel",
                                    "type": "Label",
                                    "properties": {
                                        "anchor_left": 0.02,
                                        "anchor_top": 0.1,
                                        "anchor_right": 0.98,
                                        "anchor_bottom": 0.9,
                                        "text": "",
                                        "autowrap_mode": 3,
                                    }
                                },
                            ]
                        },
                    ]
                },
                "saveAfter": True,
                "openInEditor": True,
            }),
        ]
    },
    # R2: 最终确认
    {
        "content": "Galgame 主场景已通过 build_godot_scene MCP 工具创建完成！",
        "tool_calls": None
    },
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
        'messages': [MagicMock(role='user', content=TASK)],
        'workspace': WS,
        'project_id': 'mcp_galgame',
        'conversation_id': '',
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()
    print(f"游戏目录: {GAME_DIR}")
    print(f"MCP 工具: build_godot_scene")
    print(f"预写决策: {len(DECISIONS)} 轮\n")

    async for e in stream_chat(request):
        ev = json.loads(e)
        events.append(ev)
        t = ev.get('type', '')
        if t == 'tool_call':
            n = sum(1 for e in events if e.get('type') == 'tool_call')
            name = ev.get('tool', '?')
            args = str(ev.get('args', ''))[:100]
            print(f"  🔧 [{n}] {name}: {args}")
        elif t == 'tool_result':
            r = str(ev.get('result', ''))
            if '错误' in r or 'error' in r.lower():
                print(f"     ❌ {r[:200]}")
            else:
                print(f"     ✅ {r[:200]}")
        elif t == 'error':
            print(f"  💥 {ev.get('content', '')[:200]}")
        elif t == 'step':
            print(f"  📍 Step {ev.get('round')}/{ev.get('total')}")

    elapsed = time.time() - t0
    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    errors_count = sum(1 for e in events if e.get('type') == 'error')
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')

    print(f"\n{'='*50}")
    print(f"📊 结果 ({elapsed:.1f}s)")
    print(f"  工具调用: {tools}")
    print(f"  错误: {errors_count}")
    print(f"  输出: {len(tokens)} chars")
    print(f"  Done: {'done' in [e.get('type') for e in events]}")

    all_ok = tools >= 1 and errors_count == 0
    print(f"\n{'✅ MCP 工具调用成功' if all_ok else '❌ 有问题'}")
    return all_ok


if __name__ == '__main__':
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

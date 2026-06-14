#!/usr/bin/env python3
"""
Maona Galgame 项目模拟测试 — 在 Godot 工作区创建完整视觉小说项目

仅替换 LLM 决策（decisions.jsonl），其他全部走 Maona 真实代码。
"""
import sys, os, json, asyncio, time

sys.path.insert(0, r'F:/工具/Agent_maona/backend')
from stdin_provider import StdinProvider
from api.chat import stream_chat
from unittest.mock import MagicMock
import api.chat

WS = r"F:\游戏\项目\0"
GAME_DIR = r"F:\游戏\项目\0\galgame"
os.makedirs(os.path.join(GAME_DIR, "scenes"), exist_ok=True)
os.makedirs(os.path.join(GAME_DIR, "scripts"), exist_ok=True)
os.makedirs(os.path.join(GAME_DIR, "assets", "characters"), exist_ok=True)
os.makedirs(os.path.join(GAME_DIR, "assets", "backgrounds"), exist_ok=True)
os.makedirs(os.path.join(GAME_DIR, "data"), exist_ok=True)

TASK = "请在F:\\游戏\\项目\\0\\galgame下创建一个Godot 4视觉小说(Galgame)项目，包含：1.project.godot配置 2.主场景main.tscn(Control+对话框+背景+立绘) 3.对话系统脚本dialog_system.gd 4.故事数据story.json 5.角色定义characters.json 6.README.md"

PROJECT_GODOT = """[application]
config/name="Galgame Demo"
config/description="AI生成的视觉小说"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.6")

[display]
window/size/viewport_width=1280
window/size/viewport_height=720
window/stretch/mode="canvas_items"
window/stretch/aspect="expand"

[input]
ui_accept={ "action": [{ "events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":32,"location":0,"echo":false,"script":null)], "deadzone": 0.0 }] }
"""

MAIN_TSCN = """[gd_scene load_steps=2 format=3 uid="uid://galgame_main"]

[sub_resource type="GDScript" id="GDScript_dialog"]
resource_name = "dialog_system"
script/source = "extends Control\\n\\nvar story_data = {}\\nvar current_line = 0\\nvar char_data = {}\\n\\n@onready var name_label = $NameLabel\\n@onready var dialog_label = $DialogLabel\\n@onready var bg_rect = $Background\\n\\nfunc _ready():\\n\\tload_story()\\n\\tload_characters()\\n\\tshow_line(0)\\n\\nfunc load_story():\\n\\tvar file = FileAccess.open(\\\"res://data/story.json\\\", FileAccess.READ)\\n\\tif file:\\n\\t\\tstory_data = JSON.parse_string(file.get_as_text())\\n\\nfunc load_characters():\\n\\tvar file = FileAccess.open(\\\"res://data/characters.json\\\", FileAccess.READ)\\n\\tif file:\\n\\t\\tchar_data = JSON.parse_string(file.get_as_text())\\n\\nfunc show_line(index):\\n\\tif index >= story_data.size():\\n\\t\\treturn\\n\\tvar line = story_data[index]\\n\\tvar ch = char_data.get(line[\\\"character\\\"], {})\\n\\tname_label.text = ch.get(\\\"name\\\", line[\\\"character\\\"])\\n\\tdialog_label.text = line[\\\"text\\\"]\\n\\tcurrent_line = index\\n\\nfunc _input(event):\\n\\tif event.is_action_pressed(\\\"ui_accept\\\"):\\n\\t\\tif current_line + 1 < story_data.size():\\n\\t\\t\\tshow_line(current_line + 1)\\n\\t\\telse:\\n\\t\\t\\tget_tree().quit()\\n"

[node name="Main" type="Control"]
layout_mode = 3
anchors_preset = 15
grow_horizontal = 2
grow_vertical = 2
script = SubResource("GDScript_dialog")

[node name="Background" type="ColorRect" parent="."]
layout_mode = 0
offset_right = 1280.0
offset_bottom = 720.0
color = Color(0.1, 0.05, 0.15, 1)

[node name="DialogBox" type="Panel" parent="."]
layout_mode = 0
offset_left = 40.0
offset_top = 500.0
offset_right = 1240.0
offset_bottom = 680.0

[node name="NameLabel" type="Label" parent="DialogBox"]
layout_mode = 0
offset_left = 20.0
offset_top = -30.0
offset_right = 300.0
offset_bottom = 0.0
text = ""
horizontal_alignment = 1

[node name="DialogLabel" type="Label" parent="DialogBox"]
layout_mode = 0
offset_left = 20.0
offset_top = 20.0
offset_right = 1180.0
offset_bottom = 160.0
text = ""
autowrap_mode = 3
"""

DIALOG_GD = """extends Control

var story_data = []
var current_line = 0
var char_data = {}

@onready var name_label = $NameLabel
@onready var dialog_label = $DialogLabel

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
        file.close()

func load_characters():
    var file = FileAccess.open("res://data/characters.json", FileAccess.READ)
    if file:
        var json = JSON.new()
        if json.parse(file.get_as_text()) == OK:
            char_data = json.data
        file.close()

func show_line(index):
    if index < 0 or index >= story_data.size():
        return
    var line = story_data[index]
    var ch = char_data.get(line.get("character", ""), {})
    name_label.text = ch.get("name", line.get("character", "???"))
    dialog_label.text = line.get("text", "...")
    current_line = index

func _input(event):
    if event.is_action_pressed("ui_accept"):
        if current_line + 1 < story_data.size():
            show_line(current_line + 1)
        else:
            get_tree().quit()
"""

STORY_JSON = """[
    {"character": "narrator", "text": "这是一个普通的放学后..."},
    {"character": "sakura", "text": "学长！等等我！"},
    {"character": "protag", "text": "嗯？樱，怎么了？"},
    {"character": "sakura", "text": "今天...能一起回家吗？"},
    {"character": "protag", "text": "当然可以。走吧。"},
    {"character": "narrator", "text": "夕阳下，两个人的影子渐渐拉长..."},
    {"character": "sakura", "text": "学长...其实我..."},
    {"character": "narrator", "text": "樱的脸微微泛红，欲言又止。"},
    {"character": "protag", "text": "怎么了？有什么事就说吧。"},
    {"character": "sakura", "text": "嗯...下周日，有空吗？"},
    {"character": "narrator", "text": "空气中弥漫着樱花淡淡的香气。"},
    {"character": "sakura", "text": "我想...邀请学长去..."},
    {"character": "narrator", "text": "是不是该答应她呢？"},
    {"character": "protag", "text": "好啊，我很期待。"},
    {"character": "sakura", "text": "太好了！那就说定了！"},
    {"character": "narrator", "text": "樱开心地笑了，那笑容比夕阳还要温暖。"},
    {"character": "narrator", "text": "——To be continued"}
]"""

CHARS_JSON = """{
    "narrator": {"name": "", "color": "#aaaaaa"},
    "protag": {"name": "学长", "color": "#4fc3f7"},
    "sakura": {"name": "樱", "color": "#f48fb1"}
}"""

README = """# Galgame Demo

由 Maona AI 创建，基于 Godot 4 引擎。

## 项目结构
- scenes/main.tscn — 主场景
- scripts/dialog_system.gd — 对话系统
- data/story.json — 故事脚本
- data/characters.json — 角色定义
- assets/ — 资源目录

## 运行
1. 用 Godot 4 打开项目目录
2. 按 F5 运行
3. 按空格/点击推进对话

## 自定义
修改 data/story.json 添加更多剧情
修改 data/characters.json 添加角色
"""


def mk_tc(name, args):
    return {"type": "function", "id": f"call_{name}", "function": {"name": name, "arguments": json.dumps(args)}}


DECISIONS = [
    # R1: 创建项目配置 + 场景文件
    {
        "content": "开始创建Galgame项目。",
        "tool_calls": [
            mk_tc("write_file", {"path": f"{GAME_DIR}/project.godot", "content": PROJECT_GODOT}),
            mk_tc("write_file", {"path": f"{GAME_DIR}/scenes/main.tscn", "content": MAIN_TSCN}),
            mk_tc("write_file", {"path": f"{GAME_DIR}/scripts/dialog_system.gd", "content": DIALOG_GD}),
        ]
    },
    # R2: 创建数据文件
    {
        "content": "创建数据文件。",
        "tool_calls": [
            mk_tc("write_file", {"path": f"{GAME_DIR}/data/story.json", "content": STORY_JSON}),
            mk_tc("write_file", {"path": f"{GAME_DIR}/data/characters.json", "content": CHARS_JSON}),
            mk_tc("write_file", {"path": f"{GAME_DIR}/README.md", "content": README}),
        ]
    },
    # R3: 验证文件 + Python 测试数据完整性
    {
        "content": "验证项目文件和数据。",
        "tool_calls": [
            mk_tc("list_files", {"path": GAME_DIR}),
            mk_tc("run_python", {
                "code": "import json, os\nbase = r'F:/游戏/项目/0/galgame'\nfail = 0\n# 检查 project.godot\np = os.path.join(base, 'project.godot')\nif not os.path.exists(p): print('[FAIL] project.godot missing'); fail+=1\nelse: print('[OK] project.godot')\n# 检查 scene\ns = os.path.join(base, 'scenes', 'main.tscn')\nif not os.path.exists(s): print('[FAIL] main.tscn missing'); fail+=1\nelse: print('[OK] main.tscn')\n# 验证 JSON 数据\nfor fname in ['story.json', 'characters.json']:\n    fp = os.path.join(base, 'data', fname)\n    if os.path.exists(fp):\n        with open(fp, encoding='utf-8') as f:\n            data = json.load(f)\n        print(f'[OK] {fname}: {len(data)} entries' if isinstance(data, list) else f'[OK] {fname}: {len(data)} characters')\n    else:\n        print(f'[FAIL] {fname} missing')\n        fail += 1\nprint(f'\\nResult: {\"ALL OK\" if fail == 0 else f\"{fail} FAILURES\"}')",
                "timeout": 30
            }),
        ]
    },
    # R4: 记录日志 + 完成
    {
        "content": "记录操作日志。",
        "tool_calls": [
            mk_tc("save_daily_log", {
                "content": "## [14:00] 创建 Galgame 视觉小说项目 | - 操作：write_file x6 + run_python | - 目录：F:/游戏/项目/0/galgame/ | - 结果：project.godot + 场景 + 对话系统 + 故事数据全部创建成功，Python验证通过"
            }),
        ]
    },
    # R5: 最终确认
    {
        "content": "Galgame 视觉小说项目创建完成！\n\n项目结构：\n- project.godot — Godot 4 项目配置\n- scenes/main.tscn — 主场景（对话框+背景+立绘位）\n- scripts/dialog_system.gd — 对话系统（角色名+文本+点击推进）\n- data/story.json — 17行故事脚本（樱×学长的放学故事）\n- data/characters.json — 3个角色定义\n- README.md — 说明文档\n- assets/ — 资源目录（characters/ backgrounds/）\n\n运行方式：用Godot 4打开galgame目录，按F5即可运行。按空格推进对话。",
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
        'project_id': 'galgame',
        'conversation_id': '',
        'model': None, 'provider': None,
        'persona_id': None, 'mode': 'craft',
    })()

    events = []
    t0 = time.time()
    print(f"工作空间: {WS}")
    print(f"游戏目录: {GAME_DIR}")
    print(f"预写决策: {len(DECISIONS)} 轮\n")

    async for e in stream_chat(request):
        ev = json.loads(e)
        events.append(ev)
        t = ev.get('type', '')
        if t == 'tool_call':
            n = sum(1 for e in events if e.get('type') == 'tool_call')
            name = ev.get('tool', '?')
            args = str(ev.get('args', ''))[:60]
            print(f"  🔧 [{n}] {name}")
        elif t == 'tool_result':
            r = str(ev.get('result', ''))
            icon = '❌' if '错误' in r else '✅'
            print(f"     {icon} {r[:80]}")
        elif t == 'error':
            print(f"  💥 {ev.get('content', '')[:120]}")
        elif t == 'step':
            print(f"  📍 Step {ev.get('round')}/{ev.get('total')}")

    elapsed = time.time() - t0
    tools = sum(1 for e in events if e.get('type') == 'tool_call')
    errors_count = sum(1 for e in events if e.get('type') == 'error')
    tokens = ''.join(e.get('content', '') for e in events if e.get('type') == 'token')

    import glob as g
    files = g.glob(f"{GAME_DIR}/**/*", recursive=True)
    py_files = [f for f in files if os.path.isfile(f)]

    print(f"\n{'='*50}")
    print(f"📊 结果 ({elapsed:.1f}s)")
    print(f"{'='*50}")
    print(f"  工具调用: {tools}")
    print(f"  错误: {errors_count}")
    print(f"  输出: {len(tokens)} chars")
    print(f"  Done: {'done' in [e.get('type') for e in events]}")

    print(f"\n📁 文件 ({len(py_files)}):")
    for f in sorted(py_files):
        rel = os.path.relpath(f, GAME_DIR)
        size = os.path.getsize(f)
        print(f"  {rel} ({size}B)")

    all_ok = len(py_files) >= 6 and errors_count == 0
    print(f"\n{'✅ 全部通过' if all_ok else '❌ 有问题'}")
    return all_ok


if __name__ == '__main__':
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

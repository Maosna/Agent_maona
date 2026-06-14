"""MCP 16 工具全面测试"""
import json, asyncio, sys, os
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, 'backend'))
os.chdir(os.path.join(_ROOT, 'backend'))
os.environ['MAONA_PLUGIN_ROOT'] = os.path.join(_ROOT, 'data', 'godot-mcp')
import tools.mcp_client as mc

RESULTS = []

async def test(name, args):
    try:
        r = await mc.call_mcp_tool(name, args)
        ok = '错误' not in r and 'Godot MCP' not in r and bool(r.strip())
        m = '✓' if ok else '✗'
        RESULTS.append(f"  {m} {name}: {r[:120].replace(chr(10),' ')}")
        return ok
    except Exception as e:
        RESULTS.append(f"  ✗ {name}: {e}")
        return False

async def main():
    await mc.ensure_mcp_connected()
    ok = 0

    # 场景 5
    for t in [
        ("create_scene", {"path": "res://mcp_test.tscn"}),
        ("get_current_scene", {}),
        ("save_scene", {}),
        ("open_scene", {"path": "res://mcp_test.tscn"}),
        ("get_project_info", {}),
    ]:
        if await test(*t): ok += 1

    # 节点 5
    for t in [
        ("create_node", {"parent_path": "/root", "node_type": "Label", "node_name": "N"}),
        ("list_nodes", {"parent_path": "/root"}),
        ("get_node_properties", {"node_path": "/root/N"}),
        ("update_node_property", {"node_path": "/root/N", "property": "text", "value": "OK"}),
        ("delete_node", {"node_path": "/root/N"}),
    ]:
        if await test(*t): ok += 1

    # 脚本 4
    for t in [
        ("create_script", {"script_path": "res://mcp_s.gd", "content": "extends Node\nfunc _ready():pass"}),
        ("get_script", {"script_path": "res://mcp_s.gd"}),
        ("edit_script", {"script_path": "res://mcp_s.gd", "content": "extends Node\nfunc _ready():print('v2')"}),
        ("create_script_template", {"base_class": "Node2D", "class_name": "MCPTest"}),
    ]:
        if await test(*t): ok += 1

    # 其他 2
    for t in [
        ("create_resource", {"resource_type": "LabelSettings", "resource_path": "res://mcp_r.tres"}),
        ("execute_editor_script", {"code": "print('MCP_OK')"}),
    ]:
        if await test(*t): ok += 1

    print("\n" + "="*50)
    for line in RESULTS:
        print(line)
    print(f"\n  {ok}/16 通过")

asyncio.run(main())

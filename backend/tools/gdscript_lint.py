"""GDScript 基础验证器 — 不依赖 Godot 编辑器，纯 Python 实现
检查常见错误：信号声明未 emit、类型标注缺失、跨文件 API 不一致
"""
import re
import json
from pathlib import Path


def validate_gdscript(project_dir: str = "", skip_addons: bool = True, **kw) -> str:
    """验证 GDScript 项目中的常见错误。

    Args:
        project_dir: Godot 项目根目录（含 project.godot）
        skip_addons: 是否跳过 addons/ 目录（默认 True，插件代码通常不需要检查）

    Returns:
        验证报告，列出发现的问题
    """
    if not project_dir:
        return "请提供 Godot 项目目录路径 (project_dir)"

    pd = Path(project_dir).resolve()
    if not pd.exists():
        return f"目录不存在: {pd}"

    if not (pd / "project.godot").exists():
        return f"未找到 project.godot，请确认 {pd} 是一个 Godot 项目"

    gd_files = list(pd.rglob("*.gd"))
    if skip_addons:
        gd_files = [f for f in gd_files if "addons" not in str(f.relative_to(pd)).replace("\\", "/").split("/")]
    if not gd_files:
        return f"项目中没有 .gd 脚本文件" + (" (已跳过 addons/ 目录)" if skip_addons else "")

    results = []
    all_functions = {}  # {class_name: {func_name: param_count}}
    all_signals = {}    # {class_name: {signal_name: declared_in_file}}
    all_emits = {}      # {class_name: {signal_name: [files_that_emit]}}

    for gf in sorted(gd_files):
        rel = gf.relative_to(pd)
        try:
            content = gf.read_text(encoding="utf-8")
        except Exception as e:
            results.append(f"⚠️ 无法读取 {rel}: {e}")
            continue

        issues = []

        # 1. 检查类名
        class_match = re.search(r'class_name\s+(\w+)', content)
        class_name = class_match.group(1) if class_match else f"Node@{rel.stem}"

        # 2. 检查声明了但未 emit 的信号
        declared_signals = set()
        for m in re.finditer(r'signal\s+(\w+)', content):
            sig_name = m.group(1)
            declared_signals.add(sig_name)
            all_signals.setdefault(class_name, {})[sig_name] = str(rel)

        # 3. 查找 emit 调用
        emitted = set()
        for m in re.finditer(r'(?:emit_signal|\.emit)\s*\(\s*"(\w+)"', content):
            emitted.add(m.group(1))
        # 也匹配 signal_name.emit() 模式
        for m in re.finditer(r'(\w+)\.emit\s*\(', content):
            emitted.add(m.group(1))

        all_emits.setdefault(class_name, {})
        for sig in emitted:
            all_emits[class_name].setdefault(sig, []).append(str(rel))

        # 未 emit 的信号
        unused = declared_signals - emitted
        for sig in sorted(unused):
            issues.append(f"🔴 信号 '{sig}' 已声明但从未 emit（UNUSED_SIGNAL）")

        # 4. 检查类型标注
        # 4a. 函数参数缺少类型
        for m in re.finditer(r'func\s+\w+\s*\(([^)]*)\)', content):
            params = m.group(1)
            if params.strip():
                for param in params.split(","):
                    param = param.strip()
                    if not param:
                        continue
                    # 跳过 self, 默认值参数, 已标注类型
                    if ":" not in param and not param.startswith("_"):
                        pname = param.split("=")[0].strip()
                        if pname and pname not in ("self",):
                            issues.append(f"🟡 参数 '{pname}' 缺少类型标注（可能触发 Variant 推断警告）")

        # 4b. 局部变量使用 .get() 且未标注类型
        for m in re.finditer(r'var\s+(\w+)\s*=\s*(\w+(?:\.\w+)*)\.get\s*\(', content):
            var_name = m.group(1)
            # 如果用了 := 则已标注
            line_start = content.rfind('\n', 0, m.start()) + 1
            line = content[line_start:m.end() + 30]
            if ":=" not in line.split("=")[0]:
                issues.append(f"🟡 变量 '{var_name}' 从 .get() 推断为 Variant，建议加类型标注")

        # 5. 检查函数定义（用于跨文件 API 检查）
        funcs = {}
        for m in re.finditer(r'func\s+(\w+)\s*\(([^)]*)\)', content):
            fname = m.group(1)
            params = [p.strip() for p in m.group(2).split(",") if p.strip() and not p.strip().startswith("_")]
            funcs[fname] = len(params)
        all_functions[class_name] = funcs

        if issues:
            results.append(f"\n📄 {rel} ({class_name}):")
            for issue in issues:
                results.append(f"  {issue}")

    # 6. 跨文件 API 检查：检查函数调用是否匹配
    # 寻找对其他 autoload 类的方法调用
    api_issues = []
    for gf in sorted(gd_files):
        content = gf.read_text(encoding="utf-8")
        rel = str(gf.relative_to(pd))
        # 匹配 ClassName.method(args) 模式
        for m in re.finditer(r'(\w+)\.(\w+)\s*\(', content):
            target_class = m.group(1)
            method = m.group(2)
            # 跳过内置方法
            if target_class in ("OS", "Input", "Engine", "FileAccess", "DirAccess",
                               "ResourceLoader", "JSON", "ProjectSettings", "DisplayServer",
                               "RenderingServer", "PhysicsServer2D", "PhysicsServer3D",
                               "Time", "Math", "Vector2", "Vector3", "Color", "Transform2D",
                               "Transform3D", "Rect2", "AABB", "Basis", "Quaternion",
                               "print", "push_error", "push_warning", "str", "int", "float",
                               "bool", "Array", "Dictionary", "PackedStringArray", "Callable",
                               "Signal", "Tween", "AnimationPlayer", "AudioStreamPlayer"):
                continue
            if method in ("new", "instance", "instantiate", "free", "queue_free",
                         "add_child", "remove_child", "get_node", "get_parent",
                         "connect", "disconnect", "emit", "emit_signal", "has_signal",
                         "set", "get", "call", "call_deferred", "is_connected",
                         "get_tree", "change_scene_to_file", "change_scene_to_packed",
                         "get_viewport", "set_process", "set_physics_process",
                         "get_window", "get_script", "set_script", "signal",
                         "name", "owner", "process_mode", "visible", "position",
                         "global_position", "size", "scale", "rotation", "modulate",
                         "queue_redraw", "update", "hide", "show", "grab_focus",
                         "release_focus", "has_focus", "get_global_mouse_position",
                         "get_local_mouse_position", "get_rect", "create_tween",
                         "move_to_x", "append", "size", "clear", "erase"):
                continue
            # 检查这个类是否有该方法
            if target_class in all_functions:
                if method not in all_functions[target_class]:
                    api_issues.append(f"🔴 {rel}: 调用了 '{target_class}.{method}()' 但该类没有定义此方法")
            elif target_class in ("DialogManager", "GameState", "SaveManager", "StoryPlayer",
                                 "MainGame", "TitleScreen", "SaveLoadUI", "MainGameLoop"):
                # 可能是 autoload，但还未解析到
                pass

    if api_issues:
        results.append(f"\n## 跨文件 API 一致性检查")
        for issue in api_issues:
            results.append(f"  {issue}")

    # 7. 检查场景文件引用的脚本是否存在
    tscn_files = list(pd.rglob("*.tscn"))
    for tf in sorted(tscn_files):
        content = tf.read_text(encoding="utf-8")
        rel_t = tf.relative_to(pd)
        scene_issues = []
        # 查找 ext_resource 引用
        for m in re.finditer(r'path="res://([^"]+)"', content):
            res_path = m.group(1)
            if res_path.endswith(".gd"):
                script_path = pd / res_path
                if not script_path.exists():
                    scene_issues.append(f"  🔴 引用的脚本不存在: res://{res_path}")
        # 检测 GDScript 表达式混入 TSCN（Godot 4 不支持内联 .new()）
        gdscript_exprs = re.findall(r'=\s*(?:\w+\.)+\w+\(', content)
        if gdscript_exprs:
            for expr in gdscript_exprs:
                scene_issues.append(f"  🔴 TSCN 中不允许 GDScript 表达式: {expr.strip()}（Godot 4 已移除 TSCN 内联表达式支持，请改用 [sub_resource] 块或 build_godot_scene）")
        # 检查 load_steps 声明是否正确（粗略校验）
        if content.startswith('[gd_scene'):
            declared = re.search(r'load_steps=(\d+)', content)
            actual = len(re.findall(r'^\[(?:ext_resource|sub_resource) ', content, re.MULTILINE)) + 1
            if declared and int(declared.group(1)) != actual:
                scene_issues.append(f"  🟡 load_steps 声明 {declared.group(1)} 与实际资源数 {actual} 不一致")
        if scene_issues:
            results.append(f"\n📄 {rel_t}:")
            results.extend(scene_issues)

    # 8. 检查 GDScript 中的 $NodeName / %NodeName / get_node() 引用是否匹配 TSCN
    # 收集所有 TSCN 中的节点名称
    import collections
    scene_nodes = collections.defaultdict(set)  # {tscn_relative_path: {node_names}}
    for tf in tscn_files:
        content = tf.read_text(encoding="utf-8")
        rel = str(tf.relative_to(pd))
        for m in re.finditer(r'\[node\s+name="([^"]+)"', content):
            scene_nodes[rel].add(m.group(1))

    for gf in sorted(gd_files):
        content = gf.read_text(encoding="utf-8")
        rel = str(gf.relative_to(pd))
        # 查找该脚本绑定的 TSCN（通过 ext_resource 反向查找）
        bound_scenes = []
        for tf in tscn_files:
            tc = tf.read_text(encoding="utf-8")
            t_rel = str(tf.relative_to(pd))
            if f'path="res://{rel.replace(chr(92), "/")}"' in tc:
                bound_scenes.append(t_rel)
        if not bound_scenes:
            continue

        # 检查 $NodeName 引用
        for m in re.finditer(r'\$(\w[\w/]*)', content):
            path = m.group(1)
            found = False
            for scn in bound_scenes:
                for name in scene_nodes.get(scn, set()):
                    if name == path or path.startswith(name + "/"):
                        found = True
                        break
                if found:
                    break
            if not found:
                results.append(f"\n📄 {rel}:")
                results.append(f"  🔴 $/{path} 引用不匹配：在所有关联 TSCN 中均未找到此节点")

        # 检查 get_node("...") 引用
        for m in re.finditer(r'get_node\s*\(\s*"([^"]+)"', content):
            path = m.group(1)
            found = any(
                any(name == path or path.startswith(name + "/") for name in scene_nodes.get(scn, set()))
                for scn in bound_scenes
            )
            if not found:
                results.append(f"\n📄 {rel}:")
                results.append(f"  🔴 get_node(\"{path}\") 引用不匹配")

    # 9. 检查 @export 变量类型与可能的节点名称
    for gf in sorted(gd_files):
        content = gf.read_text(encoding="utf-8")
        rel = str(gf.relative_to(pd))
        bound_scenes = [str(tf.relative_to(pd)) for tf in tscn_files
                       if f'path="res://{rel.replace(chr(92), "/")}"' in tf.read_text(encoding="utf-8")]
        if not bound_scenes:
            continue
        for m in re.finditer(r'@export(?:\s+var)?\s+(\w+)\s*:\s*(\w+)', content):
            var_name, var_type = m.group(1), m.group(2)
            # 如果变量名与某个节点名匹配，检查类型是否合理
            for scn in bound_scenes:
                for node_name in scene_nodes.get(scn, set()):
                    if node_name.lower() == var_name.lower():
                        results.append(f"\n📄 {rel}:")
                        results.append(f"  🟡 @export var {var_name}: {var_type} — 与 TSCN 节点 '{node_name}' 名称匹配，请确认类型正确")

    # 10. 检查 project.godot 中 Autoload 注册的脚本是否存在
    pg = pd / "project.godot"
    if pg.exists():
        pg_content = pg.read_text(encoding="utf-8")
        for m in re.finditer(r'(\w+)="\*res://([^"]+)"', pg_content):
            name = m.group(1)
            path = m.group(2)
            script = pd / path
            if not script.exists():
                results.append(f"\n📄 project.godot:")
                results.append(f"  🔴 Autoload '{name}' 脚本不存在: res://{path}")
            else:
                sc = script.read_text(encoding="utf-8")
                if 'class_name' not in sc and 'extends' not in sc:
                    results.append(f"\n📄 project.godot:")
                    results.append(f"  🟡 Autoload '{name}' (res://{path}) 缺少 class_name 或 extends")

    if not results:
        return "✅ 未发现明显错误（含节点路径+@export+Autoload 检查）。建议在 Godot 编辑器中打开项目做完整编译检查。"

    return "## GDScript 验证报告\n" + "\n".join(results)

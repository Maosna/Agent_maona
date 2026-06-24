---
name: godot-dev
suite: "Godot"
description: >
  **Godot 游戏开发统一入口**。触发：做游戏、开发游戏、加玩法、写 Godot 脚本、
  改场景/节点/关卡/UI/角色/敌人/菜单、做 2D/3D/RPG/平台跳跃/贪吃蛇等。
  本 Skill 负责环境检测→意图判别→流程编排，按三场景分流执行。
---
# Godot 开发统一入口

## 快速开始（第一步，唯一必读）

**调 `detect_godot_env(workspace)` 一次获取全部状态**，不要跑 PowerShell 脚本。

返回四个标志位：`hasActiveGame` / `hasProject` / `hasEditor` / `editorListening` + `gameDir` + `godotVersion`。

然后按优先级判定场景（**禁止**反问用户）：
1. `hasProject == false` → **场景 1**（make_game：部署+新建）
2. `hasActiveGame && 用户说「再做一个/另一个/新游戏」` → **场景 2**（new_game：仅新建）
3. 其他 → **场景 3**（modify_game：修改现有项目）

---

## MCP 可用性 — 最关键的分支点

**MCP 可用**（`editorListening=true`）→ 场景 3 用 `build_godot_scene` 一步建场景树。
**MCP 不可用**（`editorListening=false`）→ **不要停滞！** 直接用以下文件工具操作：
- `write_file` / `edit_file` 写 `.tscn`（文本格式，完全可行）和 `.gd` 脚本
- 写完用 `validate_gdscript(project_dir=项目目录)` 验证
- 无需等待 MCP，文件工具足够完成全部开发工作

---

## 场景 1 `make_game` — 空环境，全套部署

1. `load_skill("godot-deploy")` → 按流程部署 Godot 编辑器到 `${WORKSPACE}/godot-editor/`
2. `load_skill("godot-new")` → 创建游戏项目到 `${WORKSPACE}/<projectName>/`
3. 引导用户用编辑器打开项目并启用 GodotMCP 插件

---

## 场景 2 `new_game` — 已有编辑器，仅建新项目

1. `load_skill("godot-new")` → 新建项目到 `${WORKSPACE}/<projectName>/`（与现有 game 平铺）
2. 覆盖 `active-game.json`，切换 `gameDir` 到新项目
3. **不要**重跑 godot-deploy

---

## 场景 3 `modify_game` — 修改现有项目

### 前置检查
- `hasActiveGame=false` 或 `hasProject=false` → 拒绝，引导场景 1/2

### 修改类型分流

| 修改对象 | MCP 可用时 | MCP 不可用时 |
|----------|-----------|-------------|
| 场景/节点 | `build_godot_scene(scenePath, root={...})` 一次传完整树 | **write_file 直接写 .tscn 文本** |
| GDScript 脚本 | write_file/edit_file | write_file/edit_file（同左） |
| 文档/配置/数据 | write_file/edit_file | write_file/edit_file（同左） |
| 图片/音频等资源 | Copy-Item 到 assets/ | Copy-Item 到 assets/（同左） |

### build_godot_scene 参数格式（仅 MCP 可用时）

```
build_godot_scene({
  scenePath: "res://scenes/<name>.tscn",
  root: {
    name: "<节点名>", type: "<Godot类型>",
    properties: { ... },           // Vector2=[x,y], Color=[r,g,b,a] 0-1, rotation=弧度
    script: { path: "res://scripts/x.gd", content: "..." },
    children: [ ... ]
  },
  saveAfter: true, openInEditor: true
})
```

### 路径约定
- 资源：`res://...`，脚本：`.gd`，场景：`.tscn`
- Vector2/3：数组 `[x,y]` / `[x,y,z]`，Color：RGBA 数组 `[r,g,b,a]` 0-1，旋转：弧度

---

## 严禁行为

- ❌ 不要跑 PowerShell 探测脚本——用 `detect_godot_env(workspace)` 一行替代
- ❌ 不要在 MCP 不可用时停滞或反复探索——直接用 write_file/edit_file
- ❌ 不要为场景修改做多次原子调用——MCP 就绪时一次 `build_godot_scene` 传完整树
- ❌ 不要在没有 active-game.json 时手写 project.godot
- ❌ 不要反复反问用户「新建还是修改」——按优先级判定
- ❌ 不要把 godot-editor 或 game 目录放到 workspace 之外

---

## MCP 连接异常

调用 MCP 工具收到 **connection refused / ECONNREFUSED / 工具不存在** 时：
→ 让位给 `load_skill("godot-deploy")` 修复连接
→ 修复期间**不要等待**——用 write_file 继续开发，边开发边等 MCP 恢复

## 输出格式

- 第一行明确说「正在按场景 X 处理」
- MCP 工具结果原样展示
- 失败：简短给出错误 + 下一步建议

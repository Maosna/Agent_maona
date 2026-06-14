---
name: godot-deploy
suite: "Godot"
description: >
  仅当用户**只关心部署/重连本身**（部署 godot mcp / 安装 godot-mcp /
  setup mcp / godot mcp 连不上 / 端口 9080 没监听 / 重新连接 godot），
  或被 godot-dev 因 godot-editor 缺失而让位过来时激活。执行 5 步部署
  （Node 检查 → server build → mcp_config.json 校验 → 下载 godot-editor →
  9080 探测）。
  用户提到任何具体游戏内容（做贪吃蛇/做平台跳跃/加玩法/改场景）时
  **不要**激活本 Skill，应由 godot-dev 决定是否需要部署。
---

# Godot MCP 部署 / 重连（Skill 自执行版）

> 严格遵循 [docs/需求文档/4.23.md](../../docs/需求文档/4.23.md)：
> **MCP 只做编辑器单元操作；部署、构建、命令执行全部由 Skill 自己跑 shell。**

路径变量约定：
- `${PLUGIN_ROOT}` = 本插件根目录（含 `server/`、`addons/godot_mcp/`、
  `templates/`），由 Maona 环境变量 `MAONA_PLUGIN_ROOT` 提供
- `${WORKSPACE}`   = 用户当前工作区根目录，由 Agent 上下文提供

工作区目录契约（4.23.md 强制，子 Skill 必须遵守，详见
[godot-dev/SKILL.md](../godot-dev/SKILL.md#工作区目录契约4-23-md-强制约定所有子-skill-必须遵守)）：

```
${WORKSPACE}/
├── godot-editor/         ← 本 Skill 步骤 4 下载到这里
├── active-game.json      ← godot-new 写入
├── game1/  game2/  ...   ← godot-new 创建
```

本 Skill 只负责前者（godot-editor），其他由 godot-new 维护。

---

## 5 步部署流程（**必须**按顺序执行，每一步真实跑命令并把输出贴回对话）

### 步骤 1 — 检查 Node.js >= 18

```powershell
$nodeVer = (& node --version) 2>$null
if (-not $nodeVer) { Write-Host "[FAIL] Node.js 未安装"; return }
$major = [int]($nodeVer.TrimStart('v').Split('.')[0])
if ($major -lt 18) { Write-Host "[FAIL] Node.js $nodeVer < 18" } else { Write-Host "[OK] Node.js $nodeVer" }
```

失败处置：让用户去 https://nodejs.org 安装 18 LTS+，安装后让用户重新触发部署。
**不要继续后面步骤。**

### 步骤 2 — 检查 / 构建 MCP Server

```powershell
$dist = Join-Path "${env:MAONA_PLUGIN_ROOT}" "server\dist\index.js"
if (Test-Path $dist) {
    Write-Host "[OK] dist/index.js 已就绪"
} else {
    Write-Host "[BUILD] dist 缺失，开始 npm install + npm run build"
    Push-Location (Join-Path "${env:MAONA_PLUGIN_ROOT}" "server")
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "[FAIL] npm install"; return }
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "[FAIL] npm run build"; return }
    Pop-Location
    if (Test-Path $dist) { Write-Host "[OK] 构建完成" } else { Write-Host "[FAIL] dist 仍缺失" }
}
```

> 用户说「跳过安装 / skip-install」时，省略 `npm install`，仅跑 `npm run build`。

失败处置：把 npm 末尾输出贴给用户，提示检查代理 / 镜像 / 磁盘空间。

### 步骤 3 — 确认 mcp_config.json 已注册到 Maona

```powershell
$mcpJson = Join-Path "${env:MAONA_PLUGIN_ROOT}" "mcp_config.json"
if (Test-Path $mcpJson) { Write-Host "[OK] mcp_config.json 已存在" } else { Write-Host "[WARN] mcp_config.json 缺失" }
```

向用户提示：插件启用时 `mcp_config.json` 已自动注册 `godot-mcp`；若工具列表里
看不到，运行 `/reload-plugins`。

### 步骤 4 — 确认本地有 Godot 编辑器（按需下载到工作区）

> 这是 4.23.md 场景 1 明确要求的「下载 godot 编辑器」环节。
> **目录契约**（4.23.md 强制）：编辑器必须落到 `${WORKSPACE}/godot-editor/`，
> 与各个 game 目录、`active-game.json` 平铺同级。**严禁**放到插件目录或
> 用户目录——godot-dev 与 godot-new 都按这个位置去找编辑器。

```powershell
$ws        = "${WORKSPACE}"          # Agent 已知的当前工作区绝对路径
$editorDir = Join-Path $ws "godot-editor"
$editorExe = Get-ChildItem -Path $editorDir -Filter "Godot_v*.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $editorExe) {
    Write-Host "[INFO] ${ws}\godot-editor 下未发现 Godot"

    # 获取最新稳定版 tag（先用 GitHub API，失败则解析官网）
    Write-Host "[FETCH] 正在获取最新 Godot 版本号..."
    $tag = $null
    try {
        $latest = Invoke-RestMethod -Uri "https://api.github.com/repos/godotengine/godot-builds/releases/latest" -TimeoutSec 8 `
            -Headers @{ "User-Agent" = "Maona/1.0" }
        $tag = $latest.tag_name
    } catch {
        # GitHub API 不可用，尝试解析下载页
        try {
            $page = (Invoke-WebRequest -Uri "https://godotengine.org/download/windows/" -UseBasicParsing -TimeoutSec 10).Content
            if ($page -match 'Godot_v?(4\.\d+\.\d+)-stable') { $tag = "$($Matches[1])-stable" }
        } catch {}
    }
    if (-not $tag) { $tag = "4.6.3-stable" }
    Write-Host "[INFO] 目标版本: $tag"

    # 用国内镜像加速下载（自动回退直链）
    $filename = "Godot_v$($tag)_win64.exe.zip"
    $mirrors = @(
        "https://mirror.ghproxy.com/https://github.com/godotengine/godot-builds/releases/download/$tag/$filename",
        "https://ghproxy.net/https://github.com/godotengine/godot-builds/releases/download/$tag/$filename",
        "https://github.com/godotengine/godot-builds/releases/download/$tag/$filename"
    )

    New-Item -ItemType Directory -Path $editorDir -Force | Out-Null
    $zip = Join-Path $editorDir "godot.zip"
    $downloaded = $false
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    foreach ($u in $mirrors) {
        Write-Host "[DOWNLOAD] 尝试: $u"
        try {
            $client = New-Object System.Net.WebClient
            $client.Headers.Add("User-Agent", "Maona/1.0")
            $client.DownloadFile($u, $zip)
            if ((Get-Item $zip).Length -gt 1000000) { $downloaded = $true; Write-Host "[OK] 下载成功"; break }
        } catch { Write-Host "[RETRY] 失败: $_" }
    }

    if ($downloaded) {
        Expand-Archive -Path $zip -DestinationPath $editorDir -Force
        Remove-Item $zip
    } else {
        Write-Host "[FAIL] 所有镜像均不可用"
    }
    $editorExe = Get-ChildItem -Path $editorDir -Filter "Godot_v*.exe" -Recurse | Select-Object -First 1
}
if ($editorExe) { Write-Host "[OK] Godot editor: $($editorExe.FullName)" } else { Write-Host "[FAIL] Godot editor 不可用" }
```

> 用户系统 PATH 中已有 Godot（`godot --version` 可用）也**不算通过**——
> 4.23.md 要求统一落到 `${WORKSPACE}/godot-editor/`，否则其他 Skill 无法定位。
> 仍然按上面流程下载；下载失败时再回退到提示用户手动放置。

失败处置：网络问题让用户手动到 https://godotengine.org/download 下载并解压
到 **`${WORKSPACE}/godot-editor/`**（不是插件目录！）后重新触发。

### 步骤 5 — 自动启动 Godot 并启用 MCP 插件

```powershell
$ws = "${WORKSPACE}"

# 先检查 9080
$probe = Test-NetConnection -ComputerName 127.0.0.1 -Port 9080 `
         -InformationLevel Quiet -WarningAction SilentlyContinue
if ($probe) { Write-Host "[OK] 9080 已监听"; exit 0 }

# 找到 active-game.json 获取项目路径
$ag = Join-Path $ws "active-game.json"
$gameDir = ""
if (Test-Path $ag) {
    $aj = Get-Content $ag -Raw | ConvertFrom-Json
    $gameDir = $aj.gameDir
}
if (-not $gameDir) {
    # 自动搜 workdir 下的 project.godot
    $cand = Get-ChildItem -Path $ws -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "project.godot") } |
            Select-Object -First 1
    if ($cand) { $gameDir = $cand.FullName }
}
if (-not $gameDir) { Write-Host "[SKIP] 无项目目录，等待用户创建"; exit 0 }

# 确保插件在 project.godot 中启用
$pg = Join-Path $gameDir "project.godot"
if (Test-Path $pg) {
    $cfg = Get-Content $pg -Raw
    if ($cfg -notmatch 'godot_mcp') {
        Add-Content $pg "`n[editor_plugins]`nenabled=PackedStringArray(`"res://addons/godot_mcp/plugin.cfg`")"
        Write-Host "[CONFIG] 已启用 godot_mcp 插件"
    }
}

# 启动 Godot
$editorExe = Get-ChildItem -Path (Join-Path $ws "godot-editor") -Filter "Godot_v*.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($editorExe) {
    Write-Host "[LAUNCH] 启动 Godot: $($editorExe.FullName) --editor --path $gameDir"
    Start-Process -FilePath $editorExe.FullName -ArgumentList @("--editor", "--path", $gameDir)
    # 等 5 秒让 Godot 启动
    Start-Sleep -Seconds 5
    # 再测 9080
    $probe2 = Test-NetConnection -ComputerName 127.0.0.1 -Port 9080 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($probe2) { Write-Host "[OK] Godot MCP 已就绪"; exit 0 }
    Write-Host "[WAIT] Godot 已启动但 9080 仍未就绪（可能启动慢），再等 3 秒..."
    Start-Sleep -Seconds 3
    $probe3 = Test-NetConnection -ComputerName 127.0.0.1 -Port 9080 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($probe3) { Write-Host "[OK] Godot MCP 已就绪" } else { Write-Host "[WAIT] 请检查 Godot 窗口，确认 MCP 插件已加载" }
} else {
    Write-Host "[FAIL] 找不到 Godot 编辑器"
}
```

> 如果最终 `[WAIT]` → 告诉用户「Godot 已启动，请检查 Godot 窗口中状态栏是否显示 "MCP: Listening on port 9080"。如果没有，去 Project Settings → Plugins 手动启用 GodotMCP。」

> **⚠️ 重要**：步骤 5 执行一次即可，**不要**在后续消息中反复重跑。

---

## 部署成功后

输出汇总：

```
[1/5] check_node_version           ✓ Node.js v20.x 满足 >=18
[2/5] check_mcp_server_build       ✓ dist/index.js 已就绪
[3/5] codebuddy_registration       ✓ mcp_config.json 已注册
[4/5] godot_editor_available       ✓ Godot v4.6
[5/5] check_godot_listening_port   ✓ 端口 9080 监听中

✓ Godot MCP 部署完成。现在可以让 godot-dev 帮你做游戏了。
```

如果是从 godot-dev 场景 1 让位过来，**不要**自动跳回 godot-dev——而是
明确告诉用户：「部署完成。请告诉我你想做什么游戏，我会接着用 godot-new
为你创建项目。」让用户重新触发即可。

---

## 严禁行为

- ❌ **不要**调用任何 MCP 工具去检查部署状态（旧的 `godot_deploy` 已删除）
- ❌ **不要**自己改 `mcp_config.json` / `package.json`
- ❌ **不要**自动启动 `Godot_v*.exe` —— Godot 启用插件需要用户在 GUI 操作
- ❌ **不要**在步骤失败后立刻重试，要先让用户处理根因

---

## 失败处理对照表

| 失败步骤 | 给用户的指引 |
|---------|-------------|
| Node.js | 安装 https://nodejs.org 18 LTS+ |
| npm install / build | 贴 npm 输出末尾 / 检查代理 / `npm config get registry` |
| Godot editor 下载 | 检查网络 / 手动下载到 `${PLUGIN_ROOT}/godot-editor/` |
| 9080 未监听 | 见步骤 5 的 5 行操作说明 |

/** Electron 主进程 */
const { app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

// 简易 which 实现（无需第三方依赖）
function whichSync(cmd) {
  const PATH = process.env.PATH || "";
  const ext = process.platform === "win32" ? ".exe" : "";
  const dirs = PATH.split(path.delimiter);
  for (const dir of dirs) {
    const full = path.join(dir, cmd + ext);
    try { if (fs.statSync(full).isFile()) return full; } catch {}
    try { if (fs.statSync(full + ext).isFile()) return full + ext; } catch {}
  }
  return null;
}

// ==================== 单实例锁 ====================
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  // 已有实例在运行，直接退出
  app.quit();
  return;
}
// 第二个实例启动时，激活已有窗口
app.on("second-instance", (_event, _commandLine, _workingDirectory) => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

// 禁止 GPU 缓存 + HTTP 缓存（开发模式即时生效）
app.commandLine.appendSwitch("disable-gpu-cache");
app.commandLine.appendSwitch("disable-software-rasterizer");
app.commandLine.appendSwitch("disable-http-cache");
app.commandLine.appendSwitch("aggressive-cache-discard");

const PORT = 8765;
const BACKEND_URL = `http://127.0.0.1:${PORT}`;
let mainWindow = null;
let tray = null;
let pythonProcess = null;
let _restartCount = 0;
const _maxRestart = 10;  // 给 TIME_WAIT 足够时间释放

let _shuttingDown = false;  // 用户主动退出时不自动重启

// ==================== Python 后端管理 ====================

async function checkBackendAlive() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/api/health`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => { req.destroy(); resolve(false); });
  });
}

function startPythonBackend() {
  let pythonCmd;
  let backendDir;
  let resourcesDir = "";

  if (app.isPackaged) {
    // 打包模式：Python 后端与 Electron 打包在一起
    // 目录结构: resources/backend/python/python.exe + resources/backend/*.py
    backendDir = path.join(process.resourcesPath, "backend");
    pythonCmd = path.join(backendDir, "python", "python.exe");
    resourcesDir = process.resourcesPath;
  } else {
    // 开发模式：使用系统 Python
    pythonCmd = process.platform === "win32"
      ? (whichSync("python") || path.join(process.env.LOCALAPPDATA, "Microsoft", "WindowsApps", "python.exe"))
      : "python3";
    backendDir = path.join(__dirname, "backend");
  }

  pythonProcess = spawn(pythonCmd, ["main.py", "--no-browser"], {
    cwd: backendDir,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    env: { ...process.env, MAONA_RESOURCES_DIR: resourcesDir, PYTHONUNBUFFERED: "1" },
  });

  pythonProcess.on('error', (err) => {
    console.error(`[Electron] Python 进程错误: ${err.message}`);
    pythonProcess = null;
    if (!_shuttingDown) {
      dialog.showErrorBox("Python 启动失败", `无法启动 Python 后端：\n\n${err.message}\n\n请确保 Python 3.8+ 已安装并在 PATH 中。`);
    }
  });

  pythonProcess.stdout.on("data", (data) => {
    console.log(`[Python] ${data}`);
  });

  pythonProcess.stderr.on("data", (data) => {
    console.error(`[Python Error] ${data}`);
  });

  pythonProcess.on("close", (code) => {
    console.log(`[Python] 进程退出, code=${code}`);
    pythonProcess = null;
    // 自动重启：非用户主动关闭时尝试重启
    if (!_shuttingDown && code !== 0 && mainWindow && !mainWindow.isDestroyed()) {
      _restartCount++;
      if (_restartCount > _maxRestart) {
        dialog.showErrorBox("启动失败", `后端连续 ${_maxRestart} 次启动失败。请检查 8765 端口是否被占用或 Python 环境是否正常。`);
        return;
      }
      console.log(`[Electron] 后端异常退出，1秒后自动重启...(${_restartCount}/${_maxRestart})`);
      setTimeout(() => {
        if (!_shuttingDown && mainWindow && !mainWindow.isDestroyed()) {
          startPythonBackend();
          mainWindow.webContents.reload();
        }
      }, 1000);
    }
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    // 先通过正常方式杀掉管理进程树
    if (process.platform === "win32") {
      try {
        require("child_process").execSync("taskkill /F /T /PID " + pythonProcess.pid, { stdio: "ignore" });
      } catch { /* 可能已经退出 */ }
    } else {
      pythonProcess.kill("SIGTERM");
    }
    pythonProcess = null;
  }
  // 再清理可能残留的端口进程（execSync 确保完成后再退出）
  if (process.platform === "win32") {
    try {
      require("child_process").execSync('for /f "tokens=5" %%a in (\'netstat -ano ^| findstr :8765\') do taskkill /F /PID %%a 2>nul', { stdio: "ignore" });
    } catch { /* ignore */ }
  }
}

async function ensureBackend() {
  // 先检查是否已有后端运行——有就杀掉（确保最新代码），没有就跳过（快速启动）
  const wasAlive = await checkBackendAlive();
  if (wasAlive) {
    console.log("[Electron] 发现旧后端，清理中...");
    if (process.platform === "win32") {
      try {
        require("child_process").execSync(
          'powershell -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"',
          { stdio: "ignore" }
        );
      } catch { }
      // 等待端口释放（仅在有旧进程时才等）
      await new Promise(r => setTimeout(r, 500));
    }
  }

  // 再次检查（如果刚才杀了旧进程，现在端口应该已释放）
  const stillAlive = await checkBackendAlive();
  if (stillAlive) {
    console.log("[Electron] 后端已在运行");
    return true;
  }

  // 启动新后端
  console.log("[Electron] 启动 Python 后端...");
  startPythonBackend();

  // 等待就绪（最多 10 秒）
  for (let i = 0; i < 50; i++) {
    await new Promise((r) => setTimeout(r, 200));
    if (await checkBackendAlive()) {
      _restartCount = 0;  // 重置计数
      console.log("[Electron] 后端已就绪");
      return true;
    }
  }
  console.error("[Electron] 后端启动超时");
  return false;
}

// ==================== 窗口管理 ====================

function createWindow() {
  const iconPath = path.join(__dirname, "renderer", "assets", "icon.png");

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 600,
    minHeight: 400,
    frame: true,
    title: "Maona",
    icon: iconPath,
    backgroundColor: "#0d0d1a",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 开发模式：每次启动清 HTTP 缓存（不影响 Provider 配置）
  const ses = mainWindow.webContents.session;
  ses.clearCache().catch(() => {});

  mainWindow.loadURL(`${BACKEND_URL}/index.html`);

  // 刷新相关快捷键：Ctrl+R 仅刷新前端，Ctrl+Shift+R 重启后端+刷新
  mainWindow.webContents.on("before-input-event", (e, input) => {
    if (input.key.toLowerCase() === "r" && input.control && input.shift) {
      // Ctrl+Shift+R：重启后端 + 刷新
      e.preventDefault();
      mainWindow.webContents.executeJavaScript(`
        (function() {
          var t = document.createElement('div');
          t.id = 'restart-hint';
          t.textContent = '正在重启后端...';
          t.style.cssText = 'position:fixed;bottom:60px;left:50%;transform:translateX(-50%);background:#4CAF50;color:#fff;padding:8px 16px;border-radius:8px;font-size:13px;z-index:99999;pointer-events:none';
          document.body.appendChild(t);
        })();
      `);
      stopPythonBackend();
      // 等待旧进程退出后重启
      setTimeout(() => {
        startPythonBackend();
        // 等后端启动后刷新页面
        let attempts = 0;
        const check = setInterval(async () => {
          if (!mainWindow || mainWindow.isDestroyed()) { clearInterval(check); return; }
          attempts++;
          const alive = await checkBackendAlive();
          if (alive || attempts > 50) {
            clearInterval(check);
            if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.reload();
          }
        }, 200);
      }, 500);
    } else if (input.key === "F5" || (input.control && input.key.toLowerCase() === "r")) {
      // Ctrl+R 或 F5：仅刷新前端页面
      e.preventDefault();
      mainWindow.webContents.reload();
    }
  });

  // 右键菜单提示：拦截刷新提示
  mainWindow.webContents.on("context-menu", (e) => {
    e.preventDefault();
  });

  // === 中文菜单栏 ===
  const menu = Menu.buildFromTemplate([
    {
      label: "文件",
      submenu: [
        { label: "新建对话", accelerator: "CmdOrCtrl+N", click: () => mainWindow.webContents.send("menu-new-chat") },
        { type: "separator" },
        { label: "导出 Markdown", click: () => mainWindow.webContents.executeJavaScript("doExport('markdown')") },
        { label: "导出纯文本", click: () => mainWindow.webContents.executeJavaScript("doExport('text')") },
        { label: "导出 JSON", click: () => mainWindow.webContents.executeJavaScript("doExport('json')") },
        { type: "separator" },
        { label: "退出", accelerator: "CmdOrCtrl+Q", click: () => { app.isQuitting = true; app.quit(); } },
      ],
    },
    {
      label: "编辑",
      submenu: [
        { label: "撤销", role: "undo" },
        { label: "重做", role: "redo" },
        { type: "separator" },
        { label: "剪切", role: "cut" },
        { label: "复制", role: "copy" },
        { label: "粘贴", role: "paste" },
        { label: "全选", role: "selectAll" },
      ],
    },
    {
      label: "视图",
      submenu: [
        { label: "重新加载 (已禁用)", enabled: false },
        { label: "开发者工具", role: "toggleDevTools" },
        { type: "separator" },
        { label: "放大", role: "zoomIn" },
        { label: "缩小", role: "zoomOut" },
        { label: "重置缩放", role: "resetZoom" },
      ],
    },
    {
      label: "帮助",
      submenu: [
        { label: "关于 Maona", click: () => {
          const { dialog } = require("electron");
          dialog.showMessageBox(mainWindow, { title: "关于", message: "Maona v0.8\n精简 AI 办公助手\n\nDeepSeek / GLM / OpenAI 兼容\n\nGitHub: github.com/maona-ai/maona", type: "info" });
        }},
      ],
    },
  ]);
  Menu.setApplicationMenu(menu);

  // 关闭窗口时隐藏到托盘
  mainWindow.on("close", (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ==================== 系统托盘 ====================

function createTray() {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, "renderer", "assets", "icon.png")
    : path.join(__dirname, "renderer", "assets", "icon.png");
  const icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "显示 Maona",
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      },
    },
    { type: "separator" },
    {
      label: "快速对话 (Ctrl+Shift+M)",
      enabled: false,
    },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip("Maona - AI 办公助手");
  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => {
    mainWindow?.show();
    mainWindow?.focus();
  });
}

// ==================== 应用生命周期 ====================

app.whenReady().then(async () => {
  app.isQuitting = false;

  // IPC: 原生文件夹选择（防重入）
  let _pickFolderBusy = false;
  ipcMain.handle("pick-folder", async () => {
    if (_pickFolderBusy) { console.log("[pick-folder] 被重复调用，忽略"); return null; }
    _pickFolderBusy = true;
    console.log("[pick-folder] 正在打开对话框");
    try {
      const result = await dialog.showOpenDialog(mainWindow, {
        properties: ["openDirectory"],
        title: "选择工作空间文件夹",
      });
      console.log("[pick-folder] 完成:", result.canceled ? "canceled" : result.filePaths[0]);
      return result.canceled ? null : result.filePaths[0];
    } finally {
      _pickFolderBusy = false;
    }
  });

  // IPC: 打开文件/URL（对齐 WorkBuddy 的结果展示）
  ipcMain.handle("open-result", async (_event, target) => {
    const { shell } = require("electron");
    // 安全验证：只允许 http/https URL 和已知安全路径
    if (typeof target !== "string" || !target) return false;
    if (target.startsWith("http://") || target.startsWith("https://")) {
      // 只允许这些协议
      await shell.openExternal(target);
    } else {
      // 本地路径：验证不是系统敏感路径
      const path = require("path");
      const fs = require("fs");
      const resolved = path.resolve(target);
      const blocked = [/windows/i, /system32/i, /etc/i, /\.ssh/i, /\.gnupg/i];
      if (blocked.some(r => r.test(resolved))) return false;
      if (!fs.existsSync(resolved)) return false;
      await shell.openPath(resolved);
    }
    return true;
  });

  // IPC: 在默认浏览器中打开 URL
  ipcMain.handle("open-url", async (_event, url) => {
    const { shell } = require("electron");
    if (typeof url !== "string" || !url) return false;
    if (!url.startsWith("http://") && !url.startsWith("https://")) return false;
    await shell.openExternal(url);
    return true;
  });

  // IPC: 应用内预览 HTML 文件
  let _previewWin = null;
  ipcMain.handle("preview-html", async (_event, filePath) => {
    if (_previewWin && !_previewWin.isDestroyed()) {
      _previewWin.close();
    }
    // 验证文件路径安全
    const path = require("path");
    const url = require("url");
    const resolved = path.resolve(filePath);
    const blocked = [/windows/i, /system32/i, /etc/i];
    if (blocked.some(r => r.test(resolved))) return false;

    _previewWin = new BrowserWindow({
      width: 1100, height: 750,
      title: "预览",
      parent: mainWindow,
      modal: false,
      webPreferences: { sandbox: false, webSecurity: false }
    });
    _previewWin.loadURL(url.pathToFileURL(resolved).href);
    _previewWin.on("closed", () => { _previewWin = null; });
    return true;
  });

  const backendReady = await ensureBackend();
  if (!backendReady) {
    console.error("[Electron] 后端不可用，退出");
    app.quit();
    return;
  }

  createWindow();
  createTray();

  // 全局快捷键 Ctrl+Shift+M（替代 Alt+Space，避免与 Windows 系统热键冲突）
  globalShortcut.register("Ctrl+Shift+M", () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
});

app.on("window-all-closed", () => {
  // 不退出，留在托盘
});

app.on("before-quit", () => {
  _shuttingDown = true;
  app.isQuitting = true;
  stopPythonBackend();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

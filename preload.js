/** Electron 预加载脚本 - 安全桥接 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
  isElectron: true,
  homeDir: process.env.USERPROFILE || process.env.HOME || '',

  /** 打开原生文件夹选择对话框 */
  pickFolder: () => ipcRenderer.invoke("pick-folder"),

  /** 打开 HTML 文件预览窗口 */
  previewHtml: (path) => ipcRenderer.invoke("preview-html", path),

  /** 监听菜单事件 */
  onMenuNewChat: (cb) => ipcRenderer.on("menu-new-chat", cb),
});

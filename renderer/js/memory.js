/** 记忆管理（在设置页内） */
const memoryPage = {
  async load() {
    const project = app.getCurrentProject ? app.getCurrentProject() : "agent_maona";
    const ws = app.workspacePath || null;
    try {
      const lt = await api.getLongTermMemory(project, ws);
      document.getElementById("longterm-editor").value = lt.content || "";
    } catch { document.getElementById("longterm-editor").value = ""; }

    try {
      const today = new Date().toISOString().split("T")[0];
      const daily = await api.getDailyMemory(project, today, ws);
      const log = document.getElementById("daily-log");
      if (daily.exists && daily.content) {
        log.innerHTML = daily.content.split("\n").map((l) => `<p>${htmlEscape(l)}</p>`).join("");
      } else { log.innerHTML = '<p class="loading">今日暂无日志</p>'; }
    } catch { document.getElementById("daily-log").innerHTML = '<p class="loading">加载失败</p>'; }
  },

  async save() {
    const content = document.getElementById("longterm-editor").value;
    const project = app.getCurrentProject ? app.getCurrentProject() : "agent_maona";
    const ws = app.workspacePath || null;
    try { await api.saveLongTermMemory(project, content, ws); alert("已保存"); } catch (e) { alert("失败: " + e.message); }
  },

  refresh() { this.load(); },
};

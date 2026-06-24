/** 应用主逻辑 */
const app = {
  currentPage: "chat",
  workspacePath: null,
  currentMode: "craft",  // 默认模式，AI 可自动切换

  /** HTML 转义 — 全局复用，防止 XSS */
  htmlEscape(str) {
    if (!str) return '';
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  /** 页面顶部显示错误消息（代替 alert）*/
  showErrorToast(msg) {
    let el = document.getElementById('error-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'error-toast';
      el.style.cssText = 'position:fixed;top:50px;left:50%;transform:translateX(-50%);background:#f87171;color:#fff;padding:8px 18px;border-radius:8px;font-size:13px;z-index:99999;max-width:80%;word-break:break-all';
      document.body.appendChild(el);
    }
    el.textContent = String(msg).slice(0, 200);
    el.style.display = '';
    setTimeout(() => { if (el) el.style.display = 'none'; }, 8000);
  },

  async init() {
    // 启动时延迟检查后端状态（放在 init 最前面，避免后续错误导致未执行）
    setTimeout(() => this.checkBackend(), 100);
    // 创建全局 chat 实例（必须在 sidebar.init() 之前，因为 sidebar 的点击事件会引用 window.chat）
    if (!window.chat && typeof ChatRenderer === 'function') {
      window.chat = new ChatRenderer(
        document.getElementById('chat-messages'),
        document.getElementById('btn-send'),
        document.getElementById('btn-stop'),
        document.getElementById('chat-input')
      );
      if (typeof window.chat.init === 'function') window.chat.init();
    }

    sidebar.init();

    // 导航按钮（设置、新任务等）
    document.querySelectorAll(".nav-btn").forEach(btn => {
      btn.addEventListener("click", () => this.navigate(btn.dataset.page));
    });

    // 工作空间选择——通过 HTML onclick="app.pickWorkspace()" 触发
    // (addEventListener 方式在此环境中不生效，改用内联 onclick)

    // 统一文件夹选择器回调：根据上下文判断是选工作空间还是设默认
    document.getElementById("native-folder-picker").addEventListener("change", (e) => {
      const files = e.target.files;
      if (!files.length) return;
      const folderName = files[0].webkitRelativePath.split("/")[0];
      // 如果设置页的默认工作空间输入框可见 → 填到那里
      const wsInput = document.getElementById("default-workspace-path");
      if (wsInput && wsInput.offsetParent !== null) {
        wsInput.value = folderName;
      } else {
        // 否则当作工作空间选择
        this.workspacePath = folderName;
        this.updateWorkspaceLabel(folderName);
        sidebar.addWorkspace(folderName);
      }
    });

    // 设置 tabs
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        if (btn.dataset.tab === "providers") settings.loadProviders();
        if (btn.dataset.tab === "general") this.loadGeneralSettings();
        if (btn.dataset.tab === "persona") this.renderPersonaList();
        if (btn.dataset.tab === "skills") this.renderSkillsList();
        if (btn.dataset.tab === "model") settings.loadModelSettings();
        if (btn.dataset.tab === "knowledge") settings.loadKB();
      });
    });
    document.getElementById("btn-pick-default-ws").addEventListener("click", async () => {
      let folderPath = null;
      if (window.electronAPI?.pickFolder) {
        folderPath = await window.electronAPI.pickFolder();
      } else {
        document.getElementById("native-folder-picker").click();
        return;
      }
      if (folderPath) {
        document.getElementById("default-workspace-path").value = folderPath;
      }
    });
    document.getElementById("btn-back-from-settings").addEventListener("click", () => this.navigate("chat"));

    await this.loadDefaultWorkspace();
    await this.loadAvailableProviders();
    await this.loadPersonaSelector();
    await this.loadTheme();
    this.renderThemePicker();

    settings.init();

    // 模型切换时自动保存 + 刷新余额
    document.getElementById("model-select").addEventListener("change", () => {
      api.setPref("last_model", document.getElementById("model-select").value);
      this.updateBalance();
    });
    // 点击余额手动刷新
    document.getElementById("balance-display").addEventListener("click", () => this.updateBalance());

    await this.checkBackend();
    this._healthInterval = setInterval(() => this.checkBackend(), 30000);
  },

  async loadDefaultWorkspace() {
    try {
      const data = await api.getDefaultWorkspace();
      if (data.path && !this.workspacePath) {
        this.workspacePath = data.path;
        sidebar.addWorkspace(data.path);
      }
    } catch { /* ignore */ }
  },

  /** 更新工作空间条文字为选择的文件夹名 */
  updateWorkspaceLabel(folderPath) {
    const bar = document.getElementById("ws-bar");
    if (!bar) return;
    const name = folderPath.replace(/\\/g, "/").split("/").pop() || folderPath;
    bar.textContent = "" + name;
    bar.style.display = "block";
  },

  /** 隐藏工作空间选择条 */
  hideWorkspaceBar() {
    const bar = document.getElementById("ws-bar");
    if (bar) bar.style.display = "none";
  },

  /** 显示工作空间选择条 */
  showWorkspaceBar() {
    const bar = document.getElementById("ws-bar");
    if (bar) bar.style.display = "";
  },

  /** 重置工作空间为默认状态（切回任务模式） */
  async resetWorkspace() {
    // 尝试恢复到默认工作空间
    try {
      const data = await api.getDefaultWorkspace();
      this.workspacePath = data.path || null;
    } catch { this.workspacePath = null; }
    // ws-bar：有工作空间显示名称，无工作空间显示"选择工作空间"供点击切换
    const bar = document.getElementById("ws-bar");
    if (this.workspacePath) {
      if (bar) {
        bar.textContent = this.workspacePath.replace(/\\/g, "/").split("/").pop();
        bar.style.display = "";
      }
      sidebar.activeWorkspace = this.workspacePath;
    } else {
      if (bar) {
        bar.textContent = "选择工作空间";
        bar.style.display = "";
      }
      sidebar.activeWorkspace = null;
    }
    sidebar.render();
  },

  loadGeneralSettings() {
    api.getDefaultWorkspace().then(data => {
      document.getElementById("default-workspace-path").value = data.path || "";
    }).catch(() => {
      document.getElementById("default-workspace-path").value = "";
    });
    this.renderThemePicker();
  },

  async loadTheme() {
    const theme = await api.getPref("theme");
    document.documentElement.dataset.theme = theme || "";
    // 同步主题切换按钮
    const lightBtn = document.getElementById("theme-light-btn");
    const darkBtn = document.getElementById("theme-dark-btn");
    if (lightBtn && darkBtn) {
      lightBtn.classList.toggle("active", !theme || theme !== "dark");
      darkBtn.classList.toggle("active", theme === "dark");
    }
    // 加载主题风格
    const style = await api.getPref("ui_style") || "sakura";
    this._applyStyle(style);
  },

  renderThemePicker() {
    const themes = [
      { id: "sakura", name: "樱风", desc: "粉白柔和，Galgame风", color: "#f08cb4" },
      { id: "neon", name: "霓虹", desc: "暗色霓虹，赛博朋克", color: "#e040fb" },
      { id: "minimal", name: "极简", desc: "黑白干净，工作风", color: "#6366f1" },
      { id: "forest", name: "森林", desc: "绿意自然，护眼", color: "#4ade80" },
      { id: "ocean", name: "海洋", desc: "蓝色清爽，科技感", color: "#38bdf8" },
    ];
    const container = document.getElementById("theme-picker");
    if (!container) return;
    api.getPref("ui_style").then(current => {
      const cur = current || "sakura";
      container.innerHTML = themes.map(t => {
        const active = cur === t.id;
        return `<div class="theme-card${active ? ' active' : ''}" title="${t.desc}"
          style="--tc:${t.color}" onclick="app._applyStyle('${t.id}')">
          <div class="theme-dot" style="background:${t.color}"></div>
          <span class="theme-name">${t.name}</span>
          <span class="theme-desc">${t.desc}</span>
        </div>`;
      }).join("");
    });
  },

  async _applyStyle(id) {
    document.documentElement.dataset.style = id === "sakura" ? "" : id;
    await api.setPref("ui_style", id);
    this.renderThemePicker();
  },

  async saveDefaultWorkspace() {
    const el = document.getElementById("default-workspace-path");
    const statusEl = document.getElementById("general-status");
    if (!el) return;
    const path = el.value.trim();
    try {
      await api.saveDefaultWorkspace(path);
      if (path) { this.workspacePath = path; sidebar.addWorkspace(path); }
      if (statusEl) { statusEl.textContent = "已保存"; statusEl.style.color = "var(--success)"; }
    } catch {
      if (statusEl) { statusEl.textContent = "保存失败"; statusEl.style.color = "var(--danger)"; }
    }
  },

  async loadAvailableProviders() {
    try {
      const data = await api.getAvailableProviders();
      const providers = data.providers || [];
      const select = document.getElementById("model-select");
      if (!providers.length) { select.innerHTML = '<option value="">请先添加 API</option>'; return; }
      let html = '<option value="_auto" style="color:var(--accent);font-weight:600">自动（智能选择）</option>';
      for (const p of providers) {
        let models = [];
        try {
          const md = await api.getModels(p.name);
          models = (md.models || []).map(m => typeof m === "string" ? { id: m, enabled: true } : m);
        } catch (e) {
          models = (p.models || []).map(m => typeof m === "string" ? { id: m, enabled: true } : m);
        }
        const enabledModels = models.filter(m => m.enabled !== false);
        if (enabledModels.length === 0) continue;
        html += '<optgroup label="' + htmlEscape(p.name) + '">';
        for (const m of enabledModels) {
          const mid = m.id || m;
          html += '<option value="' + htmlEscape(p.name) + ':' + htmlEscape(mid) + '">' + htmlEscape(mid) + '</option>';
        }
        html += '</optgroup>';
      }
      select.innerHTML = html || '<option value="">请先启用模型</option>';
      // 使 buildModelSelector 对全局可用
      window.buildModelSelector = this.loadAvailableProviders.bind(this);

      // 恢复上次选择的模型（包括"自动"）
      const lastModel = await api.getPref("last_model");
      if (lastModel) {
        if (lastModel === "_auto") {
          select.value = "_auto";
        } else {
          const option = select.querySelector(`option[value="${lastModel}"]`);
          if (option) option.selected = true;
        }
      }
      // 查余额
      this.updateBalance();
    } catch {}
  },

  async updateBalance() {
    const el = document.getElementById("balance-display");
    const selVal = document.getElementById("model-select").value;
    if (selVal === "_auto") { el.textContent = "自动"; el.title = "自动选择最佳可用模型"; return; }
    const parts = selVal.split(":");
    const provider = parts[0];
    if (!provider) { el.textContent = ""; return; }
    el.textContent = "查询中...";
    try {
      const data = await api.getBalance(provider, selVal[1] || "");
      const b = data.balance || {};
      if (b.balance) {
        const unit = b.currency === "CNY" ? "¥" : "$";
        el.textContent = `${unit}${parseFloat(b.balance).toFixed(2)}`;
        el.title = `点击刷新 | 赠送 ${unit}${parseFloat(b.granted||0).toFixed(2)} | 充值 ${unit}${parseFloat(b.topped_up||0).toFixed(2)}`;
      } else {
        el.textContent = "";
      }
    } catch { el.textContent = ""; }
  },

  // ===== 人设管理 =====
  async loadPersonaSelector() {
    try {
      const data = await api.getPersonas();
      const personas = data.personas || [];
      const select = document.getElementById("persona-select");
      select.innerHTML = personas.map(p => `<option value="${htmlEscape(p.id)}">${htmlEscape(p.name)}</option>`).join("");
      const last = await api.getPref("persona_id") || "default";
      if (select.querySelector(`option[value="${last}"]`)) select.value = last;
      select.addEventListener("change", () => {
        api.setPref("persona_id", select.value);
      });
    } catch {}
  },

  async renderPersonaList() {
    try {
      const data = await api.getPersonas();
      const list = document.getElementById("persona-list");
      list.innerHTML = (data.personas || []).map(p => `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
          <div><strong>${htmlEscape(p.name)}</strong> <span style="font-size:10px;color:var(--text-dim)">${htmlEscape(p.id)}</span></div>
          <div>
            ${p.id !== "default" ? `<button class="btn-sm" onclick="app.editPersona('${htmlEscape(p.id)}')">编辑</button>
            <button class="btn-sm" style="color:var(--danger)" onclick="app.deletePersona('${htmlEscape(p.id)}')">删除</button>` : '<span style="font-size:10px;color:var(--text-dim)">系统</span>'}
          </div>
        </div>`).join("");
    } catch {}
  },

  editPersona(id) {
    api.getPersonas().then(data => {
      const p = (data.personas || []).find(x => x.id === id);
      if (!p) return;
      document.getElementById("persona-edit-id").value = p.id;
      document.getElementById("persona-id-input").value = p.id;
      document.getElementById("persona-name").value = p.name;
      document.getElementById("persona-prompt").value = p.prompt || "";
      document.getElementById("persona-form").style.display = "block";
    });
  },

  async savePersona() {
    const id = document.getElementById("persona-id-input").value.trim();
    const name = document.getElementById("persona-name").value.trim();
    if (!id || !name) return;
    await api.savePersona({ id, name, prompt: document.getElementById("persona-prompt").value, emoji: "" });
    document.getElementById("persona-form").style.display = "none";
    this.renderPersonaList();
    this.loadPersonaSelector();
  },

  async deletePersona(id) {
    if (!(await sidebar._confirm("确定删除？"))) return;
    await api.deletePersona(id);
    this.renderPersonaList();
    this.loadPersonaSelector();
  },

  getCurrentProject() {
    return this.workspacePath
      ? "ws_" + this.workspacePath.replace(/[/\\:]/g, "_")
      : "agent_maona";
  },

  /** 确保有工作空间，没有则尝试加载默认 */
  async ensureWorkspace() {
    if (this.workspacePath) return this.workspacePath;
    // 尝试加载已保存的默认工作空间
    try {
      const data = await api.getDefaultWorkspace();
      if (data.path) {
        this.workspacePath = data.path;
        sidebar.addWorkspace(data.path);
        this.updateWorkspaceLabel(data.path);
        return data.path;
      }
    } catch { /* ignore */ }
    return null;
  },

  /**
   * 更新状态显示（仅在非聊天场景使用，聊天使用 ChatRenderer 的内部状态条）
   * 保留以备 sidebar / settings 等场景使用 */

  navigate(page) {
    this.currentPage = page;
    document.getElementById("page-chat").classList.toggle("active", page === "chat");
    document.getElementById("page-settings").classList.toggle("active", page === "settings");
    document.getElementById("page-usage").classList.toggle("active", page === "usage");
    if (page === "settings") { settings.init(); this.loadGeneralSettings(); }
    if (page === "chat") window.chat?.input?.focus();
    if (page === "usage") { window._usagePage = 0; if (window._usageRefresh) window._usageRefresh(); }
  },

  // ===== 技能中心 =====
  async renderSkillsList() {
    if (window.skillcenter) { window.skillcenter.init(); return; }
    this._skillPollCount = (this._skillPollCount || 0) + 1;
    if (this._skillPollCount > 50) return;  // 最多等 10 秒
    document.getElementById("skills-main").innerHTML = '<p class="ws-empty">加载中...</p>';
    setTimeout(() => this.renderSkillsList(), 200);
  },

  async checkBackend() {
    var dot = document.getElementById("backend-status");
    if (!dot) return;
    try {
      var d = await api.health();
      dot.classList.toggle("online", !!(d && d.status === "ok"));
      dot.classList.toggle("offline", !(d && d.status === "ok"));
    } catch (e) { dot.classList.add("offline"); dot.classList.remove("online"); }
  },

  // ===== 导出对话 =====
};

// 全局 HTML 转义快捷函数
window.htmlEscape = app.htmlEscape.bind(app);

document.addEventListener("DOMContentLoaded", () => app.init());

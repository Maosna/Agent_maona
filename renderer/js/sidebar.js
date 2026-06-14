/** 左侧工作空间树 */
const sidebar = {
  workspaces: [],
  pendingWorkspaces: [],
  activeWorkspace: null,
  hasConversation: false,
  _initialized: false,  // 防重复初始化

  async init() {
    if (this._initialized) return;
    this._initialized = true;
    // 发送按钮 + 输入框回车
    const sendBtn = document.getElementById("btn-send");
    const chatInput = document.getElementById("chat-input");

    // 搜索历史结果点击代理（避免 XSS onclick）
    document.getElementById("app").addEventListener("click", (e) => {
      const el = e.target.closest("[data-conv-id]");
      if (el) {
        const convId = el.getAttribute("data-conv-id");
        const wsPath = el.getAttribute("data-ws-path") || app.workspacePath;
        sidebar.restoreHistory(wsPath, convId);
      }
    });

    const sendMessage = async () => {
      const text = chatInput.value.trim();
      if (!text) return;
      // 安全读取 isStreaming
      try { if (window.chat && window.chat.isStreaming) return; } catch(e) {}
      chatInput.value = "";
      // 优先用 chat.sendMessage，否则直接 IPC
      if (window.chat && typeof window.chat.sendMessage === "function") {
        try {
          await window.chat.sendMessage(text);
        } catch (e) {
          console.error('[sendMessage]', e);
          if (app && typeof app.showErrorToast === 'function') app.showErrorToast('发送失败: ' + (e.message || e));
          else console.error('发送失败:', e);
        }
      }
    };
    sendBtn.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    // btn-new-task 用同样的安全方式
    document.getElementById("btn-new-task").addEventListener("click", () => {
      if (window.chat && typeof window.chat.newChat === "function") {
        app.resetWorkspace();
        window.chat.newChat();
      }
    });

    // 搜索（防抖）
    const searchInput = document.getElementById("conv-search");
    document.getElementById("btn-toggle-search").addEventListener("click", () => {
      const showing = searchInput.style.display !== "none";
      searchInput.style.display = showing ? "none" : "";
      if (!showing) { searchInput.focus(); } else { searchInput.value = ""; this.render(); }
    });
    let searchTimer = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      const q = searchInput.value;
      searchTimer = setTimeout(() => this.doSearch(q), 300);
    });
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "f") {
        e.preventDefault();
        searchInput.style.display = searchInput.style.display === "none" ? "" : "none";
        if (searchInput.style.display !== "none") searchInput.focus();
      }
    });

    await this.loadWorkspaces();
    // 已有工作空间正常渲染；hasConversation 保持 false，等当前会话实际对话后才变 true
    this.render();
  },

  async loadWorkspaces() {
    try {
      const data = await api.getWorkspaces();
      this.workspaces = data.workspaces || [];
    } catch { this.workspaces = []; }
  },

  addWorkspace(folderPath) {
    if (this.workspaces.find(w => w.path === folderPath)) return;
    if (this.pendingWorkspaces.find(w => w.path === folderPath)) return;
    const name = folderPath.replace(/\\/g, "/").split("/").pop() || folderPath;
    this.pendingWorkspaces.push({ path: folderPath, name });
    this.activeWorkspace = folderPath;
    app.workspacePath = folderPath;
    if (this.hasConversation) this.flushPending();
  },

  async flushPending() {
    if (this.pendingWorkspaces.length === 0) return;
    this.workspaces = [...this.workspaces, ...this.pendingWorkspaces];
    this.pendingWorkspaces = [];
    await api.saveWorkspaces(this.workspaces);
    this.hasConversation = true;
    this.render();
  },

  /** 对话完成后调用 */
  async onConversationDone() {
    if (this.pendingWorkspaces.length > 0) {
      await this.flushPending();
      // 自动展开刚添加的工作空间
      var self = this;
      setTimeout(function() {
        if (self.activeWorkspace) self.toggleWorkspace(self.activeWorkspace);
      }, 300);
    }
  },

  async removeWorkspace(folderPath) {
    if (!(await this._confirm(`确定删除工作空间「${htmlEscape(folderPath.replace(/\\/g, "/").split("/").pop())}」及其下所有对话？`))) return;
    // 删除该工作空间下的所有对话
    try {
      const project = "ws_" + folderPath.replace(/[/\\:]/g, "_");
      const data = await api.getConversations(project);
      const convs = data.conversations || [];
      for (const c of convs) {
        await api.deleteConversation(c.id);
      }
    } catch { /* ignore */ }
    // 从列表中移除
    this.workspaces = this.workspaces.filter(w => w.path !== folderPath);
    this.pendingWorkspaces = this.pendingWorkspaces.filter(w => w.path !== folderPath);
    await api.saveWorkspaces(this.workspaces);
    if (app.workspacePath === folderPath) {
      app.workspacePath = this.workspaces[0]?.path || null;
      this.activeWorkspace = app.workspacePath;
      window.chat.newChat();
      app.showWorkspaceBar();
    }
    this.render();
  },


  async newTaskInWorkspace(folderPath) {
    if (window.chat._hasDraft && window.chat._hasDraft() && !(await this._confirm("输入框中有未发送的内容，是否放弃？"))) return;
    this.activeWorkspace = folderPath;
    app.workspacePath = folderPath;
    app.updateWorkspaceLabel(folderPath);
    this.render();
    window.chat.newChat();
  },

  async setActive(folderPath) {
    if (window.chat._hasDraft && window.chat._hasDraft() && !(await this._confirm("输入框中有未发送的内容，是否放弃？"))) return;
    this.activeWorkspace = folderPath;
    app.workspacePath = folderPath;
    app.updateWorkspaceLabel(folderPath);
    app.hideWorkspaceBar();
    this.render();
    document.getElementById("page-chat").classList.add("active");
    document.getElementById("page-settings").classList.remove("active");
  },

  async render() {
    const tree = document.getElementById("ws-tree");
    const isCollapsed = tree.dataset.collapsed === "1";
    tree.innerHTML = `
      <div class="ws-section-header" onclick="sidebar.toggleSection()">
        <span class="ws-section-arrow">${isCollapsed ? "▶" : "▼"}</span>
        <span class="ws-section-title">工作空间</span>
      </div>
      <div class="ws-section-body" style="${isCollapsed ? 'display:none' : ''}">
        ${this.workspaces.length === 0 ? '<p class="ws-empty">暂无</p>' : this.workspaces.map(w => {
          const isActive = w.path === this.activeWorkspace;
          return `
            <div class="ws-root ${isActive ? "active" : ""}">
              <div class="ws-header-row" onclick="sidebar.toggleWorkspace('${this._esc(w.path)}')">
                <span class="ws-arrow" id="ws-arrow-${this._id(w.path)}">▶</span>
                <span class="ws-name">${this._escapeHtml(w.name)}</span>
                <span class="ws-actions">
                  <span class="ws-set-active" onclick="event.stopPropagation();sidebar.newTaskInWorkspace('${this._esc(w.path)}')" title="新建任务">+</span>
                  <span class="ws-remove" onclick="event.stopPropagation();sidebar.removeWorkspace('${this._esc(w.path)}')" title="移除">✕</span>
                </span>
              </div>
              <div class="ws-folder-tree" id="ws-folder-${this._id(w.path)}" style="display:none">
                <p class="loading" style="font-size:11px">点击展开</p>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  },

  toggleSection() {
    const tree = document.getElementById("ws-tree");
    const body = tree.querySelector(".ws-section-body");
    const arrow = tree.querySelector(".ws-section-arrow");
    if (!body || !arrow) return;
    if (body.style.display === "none") {
      body.style.display = "";
      arrow.textContent = "▼";
      tree.dataset.collapsed = "0";
    } else {
      body.style.display = "none";
      arrow.textContent = "▶";
      tree.dataset.collapsed = "1";
    }
  },

  async toggleWorkspace(path) {
    const folderEl = document.getElementById("ws-folder-" + this._id(path));
    const arrowEl = document.getElementById("ws-arrow-" + this._id(path));
    if (folderEl.style.display === "none") {
      folderEl.style.display = "block"; arrowEl.textContent = "▼";
      await this.loadHistory(path, folderEl);
    } else {
      folderEl.style.display = "none"; arrowEl.textContent = "▶";
    }
  },

  async loadHistory(workspacePath, container, append = false) {
    if (!append) {
      container.innerHTML = '<p class="loading" style="font-size:11px">加载中...</p>';
    }
    try {
      const project = "ws_" + workspacePath.replace(/[/\\:]/g, "_");
      let listEl = append ? container.querySelector(".ws-conv-list") : null;
      const offset = listEl ? listEl.querySelectorAll(".ws-sub-item").length : 0;
      const data = await api.getConversations(project, 5, offset);
      const convs = data.conversations || [];

      if (convs.length === 0 && offset === 0) {
        container.innerHTML = '<p style="font-size:11px;color:var(--text-dim);padding:4px 20px">暂无对话记录</p>';
        return;
      }

      // 全量加载时：清理容器并创建新的 list
      if (!append) {
        container.innerHTML = "";
        listEl = document.createElement("div");
        listEl.className = "ws-conv-list";
        container.appendChild(listEl);
      }

      const prevLoad = container.querySelector(".ws-load-more");
      if (prevLoad) prevLoad.remove();

      // DOM 绑定避免 onclick 字符串转义问题
      convs.forEach(c => {
        const div = document.createElement("div");
        div.className = "ws-sub-item ws-history";
        div.setAttribute("data-conv-id", c.id);
        div.title = "双击重命名";
        div.onclick = () => sidebar.restoreHistory(workspacePath, c.id);
        div.ondblclick = (e) => { e.stopPropagation(); sidebar.renameConversation(workspacePath, c.id, c.title || "新对话"); };
        const title = (c.title || "新对话").substring(0, 30);
        const date = (c.updated_at || "").slice(0, 10);
        div.innerHTML = `<span class="ws-history-title">${this._escapeHtml(title)}</span>
          <span style="font-size:9px;opacity:0.5;margin-left:auto;margin-right:4px">${date}</span>
          <span class="ws-history-del" onclick="event.stopPropagation();sidebar.deleteConversation('${this._esc(workspacePath)}','${c.id}')" title="删除对话">✕</span>`;
        listEl.appendChild(div);
      });

      // 更多按钮
      if (data.has_more && data.total) {
        const remaining = Math.max(0, (data.total || 0) - offset - convs.length);
        if (remaining <= 0) return;
        const more = document.createElement("div");
        more.className = "ws-load-more";
        more.style.cssText = "text-align:center;font-size:10px;color:var(--text-dim);padding:4px;cursor:pointer";
        more.textContent = `加载更多 (${remaining} 条剩余)`;
        more.onclick = () => this.loadHistory(workspacePath, container, true);
        container.appendChild(more);
      }
    } catch { container.innerHTML = '<p style="font-size:11px;color:var(--danger)">加载失败</p>'; }
  },

  async restoreHistory(workspacePath, conversationId) {
    if (window.chat.currentConversationId === conversationId && app.workspacePath === workspacePath) return;
    if (window.chat._hasDraft && window.chat._hasDraft() && !(await this._confirm("输入框中有未发送的内容，是否放弃？"))) return;
    // 设为当前工作空间
    app.workspacePath = workspacePath;
    this.activeWorkspace = workspacePath;
    app.hideWorkspaceBar();
    this._updateActiveHighlight();
    // 加载动画
    if (window.chat.el) {
      window.chat.el.innerHTML = `<div class="welcome-msg"><h2>Maona</h2><p>加载对话...</p></div>`;
    }
    // 重置 ChatRenderer 内部状态
    window.chat._replyEl = null;
    window.chat._rawText = "";
    if (window.chat._streamStatus) window.chat._streamStatus.innerHTML = "";
    window.chat._abortPromise = null;
    try {
      const data = await api.getConversation(conversationId);
        if (data?.messages) {
          window.chat.el.innerHTML = '';
          restoreConversationMessages(data.messages, conversationId);
          // 恢复任务面板（从历史消息中的 tool_calls 重建）
          restoreTaskPanel(data.messages);
          window.chat.currentConversationId = conversationId;
          // 恢复 UI 状态
          window.chat.isStreaming = false;
          window.chat.sendBtn.style.display = '';
          window.chat.stopBtn.style.display = 'none';
          window.chat.input.disabled = false;
        } else {
          window.chat.el.innerHTML = '<div class="welcome-msg"><h2>Maona</h2><p>对话内容为空</p></div>';
          _hideTaskPanel();
        }
    } catch (e) {
      window.chat.el.innerHTML = '<div class="welcome-msg"><h2>Maona</h2><p>加载失败，请重试</p></div>';
      _hideTaskPanel();
      app && app.showErrorToast && app.showErrorToast('加载对话失败: ' + (e.message || e));
    }
    document.getElementById("page-chat").classList.add("active");
    document.getElementById("page-settings").classList.remove("active");
    window.chat.input?.focus();
    window.chat.el.scrollTop = window.chat.el.scrollHeight;
  },

  _updateActiveHighlight() {
    document.querySelectorAll(".ws-root").forEach(el => {
      const nameEl = el.querySelector(".ws-name");
      if (nameEl) {
        const displayName = (this.activeWorkspace ? this.activeWorkspace.replace(/\\/g, "/").split("/").pop() : "");
        el.classList.toggle("active", nameEl.textContent.trim() === displayName);
      }
    });
  },

  async renameConversation(workspacePath, conversationId, oldTitle) {
    const el = document.querySelector(`.ws-history[data-conv-id="${conversationId}"]`);
    if (!el) return;
    const titleSpan = el.querySelector(".ws-history-title");
    if (!titleSpan) return;
    const input = document.createElement("input");
    input.value = oldTitle;
    input.style.cssText = "width:100%;padding:2px 4px;font-size:11px;background:var(--bg);color:var(--text);border:1px solid var(--accent);border-radius:3px;outline:none";
    input.onkeydown = async (e) => {
      if (e.key === "Escape") {
        input.replaceWith(titleSpan);
        return;
      }
      if (e.key !== "Enter") return;
    };
    input.onblur = async () => {
      if (!input.parentNode) return;
      const newTitle = input.value.trim() || oldTitle;
      await api.renameConversation(conversationId, newTitle);
      titleSpan.textContent = newTitle;
      input.replaceWith(titleSpan);
    };
    titleSpan.replaceWith(input);
    input.focus();
    input.select();
  },

  async deleteConversation(workspacePath, conversationId) {
    if (!(await this._confirm("确定删除此对话？"))) {
      return;
    }
    try {
      const resp = await api.deleteConversation(conversationId);
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText);
        const msg = text.length < 200 ? text : "服务器错误 (" + resp.status + ")";
        if (app && typeof app.showErrorToast === "function") app.showErrorToast("删除失败: " + msg);
        return;
      }
      const data = await resp.json();
      if (data.status !== "ok") {
        if (app && typeof app.showErrorToast === "function") app.showErrorToast("删除失败: " + (data.detail || "未知错误"));
        return;
      }
    } catch (e) {
      console.error("[sidebar] deleteConversation failed:", e);
      if (app && typeof app.showErrorToast === "function") app.showErrorToast("删除失败: 网络错误");
      return;
    }
    if (app.workspacePath === workspacePath) {
      window.chat.newChat();
    }
    const folderEl = document.getElementById("ws-folder-" + this._id(workspacePath));
    if (folderEl) this.loadHistory(workspacePath, folderEl);
  },

  async doSearch(query) {
    if (!query.trim()) { this.clearSearch(); return; }
    const project = app.getCurrentProject();
    try {
      const data = await api.searchConversations(query, project);
      const results = data.results || [];
      if (results.length === 0) {
        const tree = document.getElementById("ws-tree");
        const body = tree.querySelector(".ws-section-body");
        if (body) body.innerHTML = '<p class="ws-empty">无搜索结果</p>';
        return;
      }
      // 高亮关键词
      var re = new RegExp("(" + query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
      var tree = document.getElementById("ws-tree");
      tree.innerHTML = [
        '<div class="ws-section-header" onclick="sidebar.clearSearch()">',
        '  <span class="ws-section-arrow">↩</span>',
        '  <span class="ws-section-title">搜索: ' + this._escapeHtml(query) + ' (' + results.length + ' 条)</span>',
        '</div>',
        '<div class="ws-section-body">',
          results.map(function(r) {
            var title = this._escapeHtml((r.title || "新对话").substring(0, 40));
            var rawSnippet = (r.snippet || r.preview || "").substring(0, 60);
            var snippet = this._escapeHtml(rawSnippet).replace(re, '<b>$1</b>');
            var safeConvId = String(r.conv_id).replace(/'/g, "\\'").replace(/\\/g, "\\\\");
            return '<div class="ws-sub-item ws-history" data-conv-id="' + this._escapeHtml(r.conv_id) + '" style="flex-direction:column;align-items:flex-start;gap:2px">' +
              '<span style="font-size:11px">' + title + '</span>' +
              '<span style="font-size:9px;opacity:0.5">' + snippet + '</span>' +
            '</div>';
          }).join(""),
        '</div>'
      ].join("");
    } catch { /* ignore */ }
  },

  clearSearch() {
    document.getElementById("conv-search").value = "";
    document.getElementById("conv-search").style.display = "none";
    this.render();
  },

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  },

  _id(path) { return btoa(encodeURIComponent(path)).replace(/[+/=]/g, "_"); },
  _esc(path) {
    return path.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  },

  _confirm(msg) {
    return new Promise(resolve => {
      const overlay = document.createElement("div");
      overlay.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center";
      overlay.innerHTML = `<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px 28px;max-width:360px;text-align:center">
        <p style="margin:0 0 16px;font-size:13px;color:var(--text)">${msg}</p>
        <div style="display:flex;gap:8px;justify-content:center">
          <button id="_c-ok" style="padding:6px 20px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px">确定</button>
          <button id="_c-cancel" style="padding:6px 20px;background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:12px">取消</button>
        </div></div>`;
      document.body.appendChild(overlay);
      const done = (ok) => {
        document.activeElement.blur();  // 先失焦，不让浏览器抢下一个元素
        overlay.remove();
        resolve(ok);
      };
      overlay.querySelector("#_c-ok").onclick = () => done(true);
      overlay.querySelector("#_c-cancel").onclick = () => done(false);
      overlay.querySelector("#_c-cancel").focus();
      // 键盘支持：Enter = 确认，Escape = 取消
      const onKey = (e) => {
        if (e.key === "Enter") { e.preventDefault(); done(true); }
        if (e.key === "Escape") { e.preventDefault(); done(false); }
      };
      overlay.addEventListener("keydown", onKey, { once: true });
    });
  },
};

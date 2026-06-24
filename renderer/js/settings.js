/** Provider 管理页面 */
const settings = {
  editing: null,
  inited: false,

  async init() {
    if (this.inited) {
      // 已经初始化过了，只刷新列表
      await this.loadProviders();
      return;
    }
    this.inited = true;

    // 阻止设置页面上的拖拽冒泡到全局 chat 拖拽处理
    var settingsPage = document.getElementById("page-settings");
    var blockDrag = function(e) { e.preventDefault(); e.stopPropagation(); };
    settingsPage.addEventListener("dragenter", blockDrag);
    settingsPage.addEventListener("dragover", blockDrag);
    settingsPage.addEventListener("drop", function(e) { e.preventDefault(); e.stopPropagation(); });

    try {
      document.getElementById("btn-add-provider").addEventListener("click", () => this.saveProvider());
      document.getElementById("btn-cancel-edit").addEventListener("click", () => this.cancelEdit());
      var btnNewProvider = document.getElementById("btn-new-provider");
      if (btnNewProvider) btnNewProvider.addEventListener("click", () => { this.cancelEdit(); document.getElementById("provider-form-modal").style.display = "flex"; });
      // 人设管理按钮
      const btnSave = document.getElementById("btn-persona-save");
      const btnCancel = document.getElementById("btn-persona-cancel");
      const btnNew = document.getElementById("btn-persona-new");
      if (btnSave) btnSave.addEventListener("click", () => app.savePersona());
      if (btnCancel) btnCancel.addEventListener("click", () => {
        document.getElementById("persona-form").style.display = "none";
      });
      if (btnNew) btnNew.addEventListener("click", () => {
        document.getElementById("persona-edit-id").value = "";
        document.getElementById("persona-id-input").value = "";
        document.getElementById("persona-name").value = "";
        document.getElementById("persona-prompt").value = "";
        document.getElementById("persona-form").style.display = "block";
      });
      // 模型参数
      document.getElementById("btn-save-model").addEventListener("click", () => this.saveModelSettings());
      document.getElementById("model-temperature").addEventListener("input", (e) => {
        document.getElementById("val-temperature").textContent = e.target.value;
      });
      document.getElementById("model-top-p").addEventListener("input", (e) => {
        document.getElementById("val-top-p").textContent = parseFloat(e.target.value).toFixed(2);
      });
      // 思考模式 toggle
      document.getElementById("model-thinking-toggle").addEventListener("change", (e) => {
        document.getElementById("thinking-effort-row").style.display = e.target.checked ? "" : "none";
      });
      document.getElementById("model-thinking-effort").addEventListener("change", (e) => {
        document.getElementById("val-thinking-effort").textContent = e.target.value;
      });
      // 知识库
      document.getElementById("btn-kb-create").addEventListener("click", () => this.createKB());
      document.getElementById("btn-kb-search").addEventListener("click", () => this.searchKB());
      document.getElementById("kb-file-input").addEventListener("change", (e) => { this.handleFiles(e.target.files); });
      document.getElementById("btn-kb-rename").addEventListener("click", () => this.renameKB());
      document.getElementById("btn-kb-del").addEventListener("click", () => this.deleteKB());
      // 拖拽上传
      var dropzone = document.getElementById("kb-dropzone");
      if (dropzone) {
        dropzone.addEventListener("click", () => document.getElementById("kb-file-input").click());
        dropzone.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); dropzone.classList.add("drag-over"); });
        dropzone.addEventListener("dragleave", () => { dropzone.classList.remove("drag-over"); });
        dropzone.addEventListener("drop", (e) => { e.preventDefault(); e.stopPropagation(); dropzone.classList.remove("drag-over"); this.handleFiles(e.dataTransfer.files); });
      }
      document.getElementById("btn-kb-browse").addEventListener("click", (e) => { e.stopPropagation(); document.getElementById("kb-file-input").click(); });
      document.getElementById("btn-kb-clear-files").addEventListener("click", () => this.clearFiles());
      document.getElementById("btn-kb-next").addEventListener("click", () => this.goStep2());
      document.getElementById("btn-kb-back").addEventListener("click", () => this.goStep1());
      document.getElementById("btn-kb-start").addEventListener("click", () => this.startIndexing());
      document.getElementById("btn-kb-done").addEventListener("click", () => this.goDone());
      // KB 主标签切换（文档/上传/设置/检索测试）
      document.querySelectorAll(".kb-nav-btn").forEach(btn => {
        btn.addEventListener("click", () => { this._switchKBTab(btn.dataset.kbtab); });
      });
      // KB 设置保存
      document.getElementById("btn-kb-save-settings").addEventListener("click", () => this._saveKBSettings());
      // 检索测试
      document.getElementById("btn-kb-test").addEventListener("click", () => this._testKBSearch());
      // 重建索引
      document.getElementById("btn-kb-reindex").addEventListener("click", () => this._reindexKB());
      // 设置滑块联动
      document.getElementById("kb-settings-topk").addEventListener("input", (e) => {
        document.getElementById("kb-val-topk").textContent = e.target.value;
      });
      document.getElementById("kb-settings-score").addEventListener("input", (e) => {
        document.getElementById("kb-val-score").textContent = parseFloat(e.target.value).toFixed(2);
      });
      // 文档详情：返回
      document.getElementById("btn-kb-doc-back").addEventListener("click", () => this._closeDocDetail());
      // 知识库卡片点击代理（避免 XSS onclick）
      document.getElementById("kb-list").addEventListener("click", (e) => {
        const card = e.target.closest("[data-kb-name]");
        if (card) settings.selectKB(card.getAttribute("data-kb-name"));
      });
      // 文档详情：引用开关
      document.getElementById("kb-doc-autocite").addEventListener("click", function() {
        var on = this.dataset.on === "true";
        this.dataset.on = on ? "false" : "true";
        this.classList.toggle("off", on);
        settings._saveDocSettings();
      });
      // 文档详情：引用格式
      document.getElementById("kb-doc-citefmt").addEventListener("change", () => this._saveDocSettings());
    } catch (e) {
      console.error("Settings event bind error:", e);
    }
    await this.loadProviders();
  },

  async loadProviders() {
    const list = document.getElementById("providers-list");
    if (!list) return;
    const prevSelected = this._selectedProvider;
    list.innerHTML = '<p class="loading">加载中...</p>';
    try {
      const data = await api.listProviders();
      const providers = data.providers || [];
      if (providers.length === 0) {
        list.innerHTML = '<p class="loading">暂无 API</p>';
        document.getElementById("provider-detail").innerHTML = '<p class="loading">点击 ＋ 添加第一个 API</p>';
        this._selectedProvider = null;
        return;
      }
      // 侧栏 Provider 列表
      list.innerHTML = providers.map((p, i) => {
        var cnt = Array.isArray(p.models) ? p.models.length : 0;
        if (cnt > 0 && typeof p.models[0] === "object") {
          cnt = p.models.filter(m => m.enabled !== false).length;
        }
        var isActive = p.name === prevSelected;
        if (!prevSelected && i === 0) isActive = true;
        return '<div class="pv-bar-item' + (isActive ? ' active' : '') + '" data-provider="' + htmlEscape(p.name) + '" onclick="settings.selectProvider(\'' + p.name.replace(/'/g, "\\'") + '\')">'
          + '<span class="pv-dot"></span>'
          + '<span class="pv-label">' + htmlEscape(p.name) + '</span>'
          + '<span class="pv-count">' + cnt + '</span>'
          + '</div>';
      }).join("");
      // 选中上次或第一个
      var target = prevSelected || providers[0].name;
      await this.selectProvider(target);
    } catch {
      list.innerHTML = '<p class="loading">加载失败</p>';
    }
  },

  async selectProvider(name) {
    // 高亮
    document.querySelectorAll(".pv-bar-item").forEach(function(el) {
      el.classList.toggle("active", el.getAttribute("data-provider") === name);
    });
    // 加载模型到右侧
    const detail = document.getElementById("provider-detail");
    detail.innerHTML = '<p class="loading">加载模型...</p>';
    try {
      const md = await api.getModels(name);
      let models = (md.models || []).map(m => typeof m === "string" ? { id: m, enabled: true } : m);
      const enabledCount = models.filter(m => m.enabled !== false).length;
      // 获取 provider 信息
      let apiUrl = "";
      try {
        const allData = await api.listProviders();
        const p = (allData.providers || []).find(function(x) { return x.name === name; });
        if (p) apiUrl = p.api_url || "";
      } catch (e) {}
      detail.innerHTML =
        '<div class="pv-detail-header">'
        + '<div><div class="pv-detail-title"><span class="pv-dot"></span>' + htmlEscape(name) + '</div>'
        + (apiUrl ? '<div class="pv-detail-desc">' + htmlEscape(apiUrl) + '</div>' : '')
        + '</div>'
        + '<div class="pv-detail-actions">'
        + '<button class="btn-sm" onclick="settings.fetchModels(\'' + name.replace(/'/g, "\\'") + '\')">获取模型</button>'
        + '<button class="btn-sm" onclick="settings.editProvider(\'' + name.replace(/'/g, "\\'") + '\')">编辑</button>'
        + '<button class="btn-sm btn-danger" onclick="settings.remove(\'' + name.replace(/'/g, "\\'") + '\')">删除</button>'
        + '</div></div>'
        + '<div class="model-search"><input type="text" placeholder="搜索模型 (' + enabledCount + ' / ' + models.length + ' 启用, ' + models.length + ' 总数)..." oninput="settings.filterModels(this.value)"></div>'
        + '<div class="model-grid">'
        + models.map(function(m) {
            var mid = m.id || m;
            var checked = m.enabled !== false ? " checked" : "";
            return '<div class="model-card" data-model-id="' + htmlEscape(mid) + '">'
              + '<label class="model-toggle">'
              + '<input type="checkbox"' + checked + ' onchange="settings.toggleModel(\'' + name.replace(/'/g, "\\'") + '\', \'' + mid.replace(/'/g, "\\'") + '\', this.checked)">'
              + '<span class="toggle-slider"></span>'
              + '</label>'
              + '<div class="model-info">'
              + '<div class="model-name">' + htmlEscape(mid) + '</div>'
              + (m.description ? '<div class="model-meta">' + htmlEscape(m.description) + '</div>' : '')
              + '</div>'
              + '</div>';
          }).join("")
        + '</div>';
    } catch (e) {
      detail.innerHTML = '<p class="loading">加载失败</p>';
    }
    this._selectedProvider = name;
  },

  filterModels(query) {
    var q = query.toLowerCase();
    document.querySelectorAll(".model-card").forEach(function(item) {
      var mid = (item.getAttribute("data-model-id") || "").toLowerCase();
      item.style.display = mid.includes(q) ? "" : "none";
    });
    // 更新搜索框占位符
    var visible = document.querySelectorAll('.model-card[style=""]').length + document.querySelectorAll('.model-card:not([style])').length;
    var total = document.querySelectorAll(".model-card").length;
    var input = document.querySelector(".model-search input");
    if (input && query) input.placeholder = "搜索模型... (" + visible + " / " + total + " 匹配)";
  },

  async toggleModel(providerName, modelId, enabled) {
    try {
      await api.toggleModel(providerName, modelId, enabled);
    } catch (e) {
      console.error("toggleModel error:", e);
    }
    // 更新侧栏计数
    var item = document.querySelector('.pv-bar-item[data-provider="' + providerName + '"]');
    if (item) {
      var checked = document.querySelectorAll('.model-card input:checked').length;
      var total = document.querySelectorAll('.model-card input').length;
      var cntEl = item.querySelector(".pv-count");
      if (cntEl) cntEl.textContent = checked;
    }
    // 更新搜索栏计数
    var input = document.querySelector(".model-search input");
    if (input) {
      var en = document.querySelectorAll('.model-card input:checked').length;
      input.placeholder = "搜索模型 (" + en + " / " + document.querySelectorAll(".model-card").length + " 启用)";
    }
    // 刷新下拉框
    if (typeof window.buildModelSelector === "function") window.buildModelSelector();
  },

  editProvider(name) {
    this.editing = name;
    document.getElementById("edit-provider-name").value = name;
    document.getElementById("new-provider-name").value = name;
    document.getElementById("new-provider-url").value = "";
    document.getElementById("new-provider-key").value = "";
    document.getElementById("new-provider-key").placeholder = "留空则不修改";
    document.getElementById("provider-form-title").textContent = "编辑 " + name;
    document.getElementById("btn-add-provider").textContent = "保存修改";
    document.getElementById("provider-form-modal").style.display = "flex";
  },

  cancelEdit() {
    this.editing = null;
    document.getElementById("new-provider-name").value = "";
    document.getElementById("new-provider-url").value = "";
    document.getElementById("new-provider-key").value = "";
    document.getElementById("new-provider-key").placeholder = "sk-...";
    document.getElementById("provider-form-title").textContent = "添加 API";
    document.getElementById("btn-add-provider").textContent = "添加";
    document.getElementById("edit-provider-name").value = "";
    document.getElementById("provider-form-modal").style.display = "none";
    document.getElementById("settings-status").textContent = "";
  },

  async saveProvider() {
    const name = document.getElementById("new-provider-name").value.trim();
    const url = document.getElementById("new-provider-url").value.trim();
    const key = document.getElementById("new-provider-key").value.trim();
    const status = document.getElementById("settings-status");

    if (!name || !url) {
      status.textContent = "请填写名称和 URL";
      status.style.color = "var(--danger)";
      return;
    }

    try {
      if (this.editing) {
        const oldName = document.getElementById("edit-provider-name").value;
        // 改名了的先删旧再添加
        if (oldName !== name) {
          await api.addProvider(name, url, key);  // 先添加新的
          if (name !== oldName) {
            await api.removeProvider(oldName);  // 后删旧的，防止添加失败丢数据
          }
        } else if (key) {
          // 同名编辑，key 非空才更新（空 key 保持旧密钥）
          await api.removeProvider(oldName);
          await api.addProvider(name, url, key);
        }
        // key 为空且同名 → 什么都不做，保持旧密钥
      } else {
        if (!key) { status.textContent = "请填写 API Key"; status.style.color = "var(--danger)"; return; }
        await api.addProvider(name, url, key);
      }

      this.cancelEdit();
      status.textContent = "已保存";
      status.style.color = "var(--success)";
      setTimeout(() => { status.textContent = ""; }, 4000);
      await this.loadProviders();
      await app.loadAvailableProviders();
    } catch (err) {
      status.textContent = "保存失败: " + err.message;
      status.style.color = "var(--danger)";
      setTimeout(() => { status.textContent = ""; }, 4000);
    }
  },

  async fetchModels(name) {
    const status = document.getElementById("settings-status");
    status.textContent = "正在获取 " + name + " 的模型列表...";
    try {
      await api.fetchModels(name);
      status.textContent = name + " 模型已更新";
      status.style.color = "var(--success)";
      await this.loadProviders();
      await app.loadAvailableProviders();
    } catch {
      status.textContent = "获取失败";
      status.style.color = "var(--danger)";
      setTimeout(() => { status.textContent = ""; }, 4000);
    }
  },

  async remove(name) {
    if (!(await sidebar._confirm("确定要删除 " + name + " 吗？"))) return;
    try {
      await api.removeProvider(name);
      await this.loadProviders();
      await app.loadAvailableProviders();
    } catch {}
  },

  // ===== 模型参数设置 =====
  async loadModelSettings() {
    try {
      const r = await _fetch(API_BASE + "/model-settings");
      if (!r.ok) return;
      const s = await r.json();
      document.getElementById("model-temperature").value = s.temperature;
      document.getElementById("val-temperature").textContent = s.temperature;
      document.getElementById("model-max-tokens").value = s.max_tokens;
      document.getElementById("model-top-p").value = s.top_p;
      document.getElementById("val-top-p").textContent = s.top_p;
      document.getElementById("model-thinking-toggle").checked = s.thinking_enabled === true;
      document.getElementById("model-thinking-effort").value = s.reasoning_effort || "high";
      document.getElementById("val-thinking-effort").textContent = s.reasoning_effort || "high";
      document.getElementById("thinking-effort-row").style.display = s.thinking_enabled ? "" : "none";
      document.getElementById("model-use-embeddings").checked = s.use_embeddings !== false;
      document.getElementById("model-embedding-model").value = s.embedding_model || "text-embedding-3-small";
      document.getElementById("model-embedding-url").value = s.embedding_url || "";
      document.getElementById("model-embedding-key").value = s.embedding_api_key || "";
    } catch {}
  },

  async saveModelSettings() {
    const s = {
      temperature: parseFloat(document.getElementById("model-temperature").value),
      max_tokens: parseInt(document.getElementById("model-max-tokens").value) || 4096,
      top_p: parseFloat(document.getElementById("model-top-p").value),
      thinking_enabled: document.getElementById("model-thinking-toggle").checked,
      reasoning_effort: document.getElementById("model-thinking-effort").value,
      use_embeddings: document.getElementById("model-use-embeddings").checked,
      embedding_model: document.getElementById("model-embedding-model").value,
      embedding_url: document.getElementById("model-embedding-url").value,
      embedding_api_key: document.getElementById("model-embedding-key").value,
    };
    try {
      const r = await _fetch(API_BASE + "/model-settings", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(s)
      });
      const st = document.getElementById("model-status");
      if (r.ok) { st.textContent = "✅ 已保存"; setTimeout(() => st.textContent = "", 2000); }
      else { st.textContent = "❌ 保存失败"; }
    } catch { document.getElementById("model-status").textContent = "❌ 网络错误"; }
  },

  // ===== 知识库管理 =====
  _currentKB: null,
  async loadKB() {
    document.getElementById("kb-list").innerHTML = '<p class="hint" style="padding:8px;text-align:center">加载...</p>';
    try {
      const r = await _fetch(API_BASE + "/knowledge/list");
      if (!r.ok) return;
      const kbs = await r.json();
      if (!kbs.length) { document.getElementById("kb-list").innerHTML = '<p class="hint" style="padding:12px;text-align:center">暂无知识库</p>'; return; }
      let html = '';
      for (const k of kbs) {
        const desc = (k.description || '').slice(0, 30);
        const modeLabel = k.mode === 'vector' ? '向量' : k.mode === 'hybrid' ? '混合' : '全文';
        html += '<div class="kb-card' + (this._currentKB===k.name?' active':'') + '" data-kb-name="' + htmlEscape(k.name) + '">';
        html += '<div class="kb-card-name">' + htmlEscape(k.name) + '</div>';
        if (desc) html += '<div class="kb-card-desc">' + htmlEscape(desc) + '</div>';
        html += '<div class="kb-card-footer"><span class="kb-card-meta">' + (k.docs||0) + ' 文档 ' + (k.chunks||0) + ' 块</span><span class="kb-card-badge">' + modeLabel + '</span></div>';
        html += '</div>';
      }
      document.getElementById("kb-list").innerHTML = html;
    } catch {}
  },
  selectKB(name) {
    this._currentKB = name;
    this.loadKB();

    var detail = document.getElementById("kb-detail");
    var empty = document.getElementById("kb-empty");
    empty.style.display = "none";
    detail.style.display = "flex";

    // 切换到文档标签
    this._switchKBTab("docs");

    // 重置
    document.getElementById("kb-search-query").value = "";
    document.getElementById("kb-search-results").style.display = "none";
    document.getElementById("kb-test-results").innerHTML = "";
    document.getElementById("kb-test-query").value = "";

    // 加载详情
    this._loadKBDetail();
    this._loadDocs();
  },
  async _loadKBDetail() {
    if (!this._currentKB) return;
    try {
      const r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/settings");
      if (!r.ok) return;
      const s = await r.json();

      // 头部
      document.getElementById("kb-detail-name").textContent = s.name;
      document.getElementById("kb-detail-stats").textContent = (s.docs||0) + ' 个文档 ' + (s.chunks||0) + ' 个块';

      // 模式徽章
      var badge = document.getElementById("kb-mode-badge");
      badge.className = "kb-icon-tag";
      if (s.mode === "vector") { badge.textContent = "V"; badge.className += " mode-vector"; }
      else if (s.mode === "hybrid") { badge.textContent = "H"; badge.className += " mode-hybrid"; }
      else { badge.textContent = "F"; badge.className += " mode-tfidf"; }

      // 设置表单
      document.getElementById("kb-settings-name").value = s.name;
      document.getElementById("kb-settings-desc").value = s.description || "";
      document.getElementById("kb-settings-method").value = s.retrieval_method || "vector";
      document.getElementById("kb-settings-topk").value = s.top_k || 3;
      document.getElementById("kb-val-topk").textContent = s.top_k || 3;
      document.getElementById("kb-settings-score").value = s.score_threshold || 0.3;
      document.getElementById("kb-val-score").textContent = (s.score_threshold || 0.3).toFixed(2);
      document.getElementById("kb-settings-chunk").value = s.chunk_size || 1000;
      document.getElementById("kb-settings-overlap").value = s.chunk_overlap || 80;

      document.getElementById("kb-settings-status").textContent = "";

    } catch (e) { console.error("loadKBDetail:", e); }
  },
  _switchKBTab(tab) {
    document.querySelectorAll(".kb-nav-btn").forEach(b => b.classList.toggle("active", b.dataset.kbtab === tab));
    document.getElementById("kb-panel-docs").style.display = tab === "docs" ? "" : "none";
    document.getElementById("kb-panel-upload").style.display = tab === "upload" ? "" : "none";
    document.getElementById("kb-panel-settings").style.display = tab === "settings" ? "" : "none";
    document.getElementById("kb-panel-test").style.display = tab === "test" ? "" : "none";

    if (tab === "settings") this._loadKBDetail();
    if (tab === "upload") {
      // 重置上传状态
      this._kbFiles = [];
      this._kbTempFiles = [];
      this._renderFileList();
      document.getElementById("kb-upload-step1").style.display = "block";
      document.getElementById("kb-upload-step2").style.display = "none";
      document.getElementById("kb-upload-step3").style.display = "none";
      document.getElementById("kb-process-results").style.display = "none";
      this._setStep(1);
    }
    if (tab === "docs") this._closeDocDetail();
  },
  async _saveKBSettings() {
    if (!this._currentKB) return;
    var st = document.getElementById("kb-settings-status");
    st.textContent = "保存中...";
    try {
      var topk = parseInt(document.getElementById("kb-settings-topk").value) || 3;
      var score = parseFloat(document.getElementById("kb-settings-score").value) || 0.3;
      var chunk = parseInt(document.getElementById("kb-settings-chunk").value) || 1000;
      var overlap = parseInt(document.getElementById("kb-settings-overlap").value) || 80;
      var data = {
        description: document.getElementById("kb-settings-desc").value,
        retrieval_method: document.getElementById("kb-settings-method").value,
        top_k: topk,
        score_threshold: score,
        chunk_size: chunk,
        chunk_overlap: overlap
      };
      var r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });
      if (!r.ok) {
        var errBody = "";
        try { errBody = await r.text(); } catch(e2) {}
        throw new Error(errBody || ("HTTP " + r.status));
      }
      st.textContent = "保存成功"; st.style.color = "var(--success)";
      // 同时更新名称（如有变化）
      var newName = document.getElementById("kb-settings-name").value.trim();
      if (newName && newName !== this._currentKB) {
        await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/rename", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newName })
        });
        this._currentKB = newName;
      }
      this.loadKB();
      setTimeout(() => { st.textContent = ""; }, 2000);
    } catch (e) {
      st.textContent = "保存失败: " + e.message; st.style.color = "var(--danger)";
    }
  },
  async _reindexKB() {
    if (!this._currentKB) return;
    var st = document.getElementById("kb-settings-status");
    st.textContent = "重建索引中...";
    st.style.color = "";
    try {
      var r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/reindex", {
        method: "POST"
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      st.textContent = "索引重建完成";
      st.style.color = "var(--success)";
      this._loadKBDetail();
      setTimeout(() => { st.textContent = ""; }, 2000);
    } catch (e) {
      st.textContent = "重建失败: " + e.message;
      st.style.color = "var(--danger)";
    }
  },
  async _testKBSearch() {
    var q = document.getElementById("kb-test-query").value.trim();
    if (!q || !this._currentKB) return;
    var res = document.getElementById("kb-test-results");
    res.innerHTML = '<p class="hint" style="padding:12px">检索中...</p>';
    try {
      var r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/test-search?q=" + encodeURIComponent(q));
      if (!r.ok) { res.innerHTML = '<p class="hint">检索失败</p>'; return; }
      var data = await r.json();
      if (!data.results || !data.results.length) {
        res.innerHTML = '<p class="hint" style="padding:12px">无匹配结果</p>'; return;
      }
      var html = '';
      for (var i = 0; i < data.results.length; i++) {
        var item = data.results[i];
        var score = parseFloat(item.score) || 0;
        var scCls = score >= 0.7 ? 'score-high' : score >= 0.4 ? 'score-mid' : 'score-low';
        var scPct = (score * 100).toFixed(0) + '%';
        html += '<div class="kb-test-result"><div class="test-header"><span class="test-file">' + htmlEscape(item.file) + '</span><span class="test-score ' + scCls + '">' + scPct + '</span></div><div class="test-text">' + htmlEscape((item.text||'').slice(0, 300)) + '</div></div>';
      }
      res.innerHTML = html;
    } catch { res.innerHTML = '<p class="hint">检索出错</p>'; }
  },
  async _loadDocs() {
    if (!this._currentKB) return;
    var list = document.getElementById("kb-docs-list");
    var empty = document.getElementById("kb-docs-empty");
    try {
      var r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/docs");
      if (!r.ok) { list.innerHTML = ""; empty.style.display = "block"; return; }
      var docs = await r.json();
      if (!docs.length) { list.innerHTML = ""; empty.style.display = "block"; return; }
      empty.style.display = "none";

      // 批量并行加载各文档元数据
      var metas = {};
      await Promise.all(docs.map(async (doc) => {
        try {
          var mr = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/doc/" + encodeURIComponent(doc.name) + "/settings");
          if (mr.ok) metas[doc.name] = await mr.json();
        } catch(e) {}
      }));

      var html = '';
      for (var i = 0; i < docs.length; i++) {
        var d = docs[i];
        var displayName = d.name.replace(/\.txt$/, '');
        var size = d.size < 1024 ? d.size+'B' : d.size < 1048576 ? (d.size/1024).toFixed(1)+'KB' : (d.size/1048576).toFixed(1)+'MB';
        var meta = metas[d.name] || {};
        var citeOn = meta.auto_cite !== false;
        html += '<div class="kb-doc-item">';
        html += '<span class="doc-name" onclick="settings._openDocDetail(\'' + d.name + '\')">' + htmlEscape(displayName) + '</span>';
        html += '<span class="doc-meta">' + size + '</span>';
        html += '<span class="toggle-switch doc-cite-toggle' + (citeOn ? '' : ' off') + '" data-doc="' + d.name + '" onclick="event.stopPropagation();settings._toggleDocCite(this)"></span>';
        html += '<span class="doc-del" onclick="event.stopPropagation();settings._deleteDoc(\'' + d.name + '\')">&times;</span>';
        html += '</div>';
      }
      list.innerHTML = html;
      // 更新 KB 列表中的引用状态
      for (var i = 0; i < docs.length; i++) {
        var d = docs[i];
        var meta = metas[d.name] || {};
        var citeOn = meta.auto_cite !== false;
        var el = list.querySelector('.doc-cite-toggle[data-doc="' + d.name + '"]');
        if (el) { el.classList.toggle('off', !citeOn); }
      }
    } catch { list.innerHTML = ""; empty.style.display = "block"; }
  },
  async _toggleDocCite(el) {
    var docName = el.dataset.doc;
    var on = !el.classList.contains("off");
    el.classList.toggle("off", on);
    // 保留用户已设置的 cite_format，不硬编码
    var existingFormat = document.getElementById("kb-cite-format")?.value || "inline";
    await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/doc/" + encodeURIComponent(docName) + "/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_cite: !on, cite_format: existingFormat })
    }).catch(function(){});
  },
  async _openDocDetail(docName) {
    this._currentDoc = docName;
    // 隐藏文档列表，显示详情
    document.querySelector("#kb-panel-docs .kb-search-bar").style.display = "none";
    document.querySelector("#kb-panel-docs .kb-docs-section").style.display = "none";
    document.getElementById("kb-doc-detail").style.display = "block";

    var dn = document.getElementById("kb-doc-detail-name");
    var ds = document.getElementById("kb-doc-detail-stats");
    var preview = document.getElementById("kb-doc-content-preview");
    var chunksList = document.getElementById("kb-doc-chunks-list");

    dn.textContent = docName.replace(/\.txt$/, '');
    ds.textContent = "加载中...";
    preview.textContent = "加载中...";
    chunksList.innerHTML = "";

    try {
      var r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/doc/" + encodeURIComponent(docName) + "/detail");
      if (!r.ok) throw new Error("load fail");
      var data = await r.json();
      ds.textContent = (data.size < 1024 ? data.size+'B' : (data.size/1024).toFixed(1)+'KB') + ' | ' + data.total_chunks + ' 个分段';
      preview.textContent = data.content || "(空文档)";

      // 文档级引用控制
      var meta = data.meta || {};
      var autoCite = document.getElementById("kb-doc-autocite");
      autoCite.dataset.on = meta.auto_cite !== false ? "true" : "false";
      autoCite.classList.toggle("off", meta.auto_cite === false);
      document.getElementById("kb-doc-citefmt").value = meta.cite_format || "inline";

      // 分段列表
      if (data.chunks && data.chunks.length > 0) {
        var html = '';
        for (var i = 0; i < data.chunks.length; i++) {
          var c = data.chunks[i];
          var chunkLen = (c.text||'').length;
          html += '<div class="kb-doc-chunk">';
          html += '<div class="chunk-header"><span class="chunk-range">Chunk-' + (i+1) + ' | ' + (c.lines||'') + '</span><span class="chunk-size-label">' + chunkLen + ' 字符</span></div>';
          html += '<div class="chunk-text">' + (c.text||'').slice(0, 300) + '</div>';
          html += '</div>';
        }
        chunksList.innerHTML = html;
      } else {
        chunksList.innerHTML = '<p class="hint">该文档尚未索引</p>';
      }
    } catch (e) {
      ds.textContent = "加载失败";
      preview.textContent = "加载失败: " + e.message;
    }
  },
  _closeDocDetail() {
    this._currentDoc = null;
    document.querySelector("#kb-panel-docs .kb-search-bar").style.display = "";
    document.querySelector("#kb-panel-docs .kb-docs-section").style.display = "";
    document.getElementById("kb-doc-detail").style.display = "none";
  },
  async _saveDocSettings() {
    if (!this._currentKB || !this._currentDoc) return;
    var data = {
      auto_cite: document.getElementById("kb-doc-autocite").dataset.on === "true",
      cite_format: document.getElementById("kb-doc-citefmt").value
    };
    await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/doc/" + encodeURIComponent(this._currentDoc) + "/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    }).catch(function(){});
  },
  async _previewDoc(docName) {
    if (!this._currentKB) return;
    const old = document.getElementById("kb-doc-preview"); if (old) old.remove();
    try {
      const r = await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/doc/" + encodeURIComponent(docName));
      if (!r.ok) return;
      const doc = await r.json();
      const prev = document.createElement("div");
      prev.id = "kb-doc-preview"; prev.className = "kb-doc-preview"; prev.style.display = "block";
      prev.textContent = docName + "\n\n" + doc.content;
      document.getElementById("kb-docs-list").after(prev);
    } catch {}
  },
  async _deleteDoc(docName) {
    if (!(await sidebar._confirm("del " + docName + "?"))) return;
    try {
      await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB) + "/doc/" + encodeURIComponent(docName), { method: "DELETE" });
      this._loadDocs(); this.loadKB();
    } catch {}
  },
  async renameKB() {
    // 跳转到设置标签页，在名称输入框中修改后保存
    this._switchKBTab("settings");
    document.getElementById("kb-settings-name").focus();
    document.getElementById("kb-settings-name").select();
  },
  async deleteKB() {
    if (!(await sidebar._confirm("delete " + this._currentKB + "?"))) return;
    try {
      await _fetch(API_BASE + "/knowledge/" + encodeURIComponent(this._currentKB), { method: "DELETE" });
      this._currentKB = null; document.getElementById("kb-detail").style.display = "none";
      document.getElementById("kb-empty").style.display = "block"; this.loadKB();
    } catch {}
  },
  async createKB() {
    const name = document.getElementById("kb-new-name").value.trim();
    if (!name) return;
    try {
      const r = await _fetch(API_BASE + "/knowledge/create", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name}) });
      if (r.ok) { this.selectKB(name); document.getElementById("kb-new-name").value = ""; }
    } catch {}
  },
  async addKBText() {
    // 已废弃：使用上传向导替代，保留兼容
    const title = document.getElementById("kb-doc-title")?.value?.trim();
    const content = document.getElementById("kb-doc-content")?.value?.trim();
    if (!title || !content || !this._currentKB) return;
    const st = document.getElementById("kb-add-status");
    try {
      const r = await _fetch(API_BASE + "/knowledge/add", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({kb: this._currentKB, title, content}) });
      st.textContent = r.ok ? "done" : "fail"; if (r.ok) { document.getElementById("kb-doc-title").value = ""; document.getElementById("kb-doc-content").value = ""; this._loadDocs(); this.loadKB(); }
      setTimeout(() => st.textContent = "", 2000);
    } catch { st.textContent = "err"; }
  },
  async addKBUrl() {
    const url = document.getElementById("kb-url").value.trim();
    if (!url || !this._currentKB) return;
    const st = document.getElementById("kb-add-status");
    try {
      const r = await _fetch(API_BASE + "/knowledge/add-url", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({kb: this._currentKB, url}) });
      st.textContent = r.ok ? "done" : "fail"; if (r.ok) { document.getElementById("kb-url").value = ""; this._loadDocs(); this.loadKB(); }
      setTimeout(() => st.textContent = "", 2000);
    } catch { st.textContent = "err"; }
  },
  async searchKB() {
    const query = document.getElementById("kb-search-query").value.trim();
    if (!query || !this._currentKB) return;
    const res = document.getElementById("kb-search-results");
    try {
      const r = await _fetch(API_BASE + "/knowledge/search?kb=" + encodeURIComponent(this._currentKB) + "&q=" + encodeURIComponent(query));
      if (!r.ok) return;
      const data = await r.json();
      if (!data.results || !data.results.length) { res.innerHTML = '<p class="hint" style="padding:8px">no results</p>'; }
      else { let html = ''; for (const r of data.results.slice(0,8)) html += '<div class="kb-result-card"><div class="kb-result-file">' + htmlEscape(r.file) + ' (' + r.score + ')</div><div class="kb-result-text">' + htmlEscape((r.text||'').slice(0,200)) + '</div></div>'; res.innerHTML = html; }
      res.style.display = "block";
    } catch {}
  },
  // ===== 知识库拖拽上传 + 分步向导 =====
  _kbFiles: [],
  _kbTempFiles: [],  // uploaded temp info from backend

  handleFiles(fileList) {
    const files = Array.from(fileList);
    if (!files.length) return;
    // 合并去重
    const existNames = new Set(this._kbFiles.map(f => f.name));
    for (const f of files) {
      if (!existNames.has(f.name)) {
        this._kbFiles.push(f);
        existNames.add(f.name);
      }
    }
    this._renderFileList();
  },

  _renderFileList() {
    const count = this._kbFiles.length;
    document.getElementById("kb-file-count").textContent = count + ' 个文件';
    const list = document.getElementById("kb-file-items");
    const nextBtn = document.getElementById("btn-kb-next");

    if (count === 0) {
      document.getElementById("kb-file-list").style.display = "none";
      document.getElementById("kb-dropzone").style.display = "";
      nextBtn.disabled = true;
      return;
    }

    document.getElementById("kb-file-list").style.display = "block";
    document.getElementById("kb-dropzone").style.display = "none";
    nextBtn.disabled = false;

    let html = '';
    for (let i = 0; i < this._kbFiles.length; i++) {
      const f = this._kbFiles[i];
      const ext = f.name.split('.').pop().toLowerCase();
      const iconCls = this._fileIconClass(ext);
      const size = f.size < 1024 ? f.size + 'B' : f.size < 1048576 ? (f.size/1024).toFixed(1) + 'KB' : (f.size/1048576).toFixed(1) + 'MB';
      html += '<div class="kb-file-item"><div class="file-icon ' + iconCls + '">' + htmlEscape(ext.slice(0,3)) + '</div><div class="file-info"><div class="file-name" title="' + htmlEscape(f.name) + '">' + htmlEscape(f.name) + '</div><div class="file-size">' + size + '</div></div><span class="file-remove" onclick="settings.removeFile(' + i + ')">&times;</span></div>';
    }
    list.innerHTML = html;
  },

  _fileIconClass(ext) {
    const map = {
      pdf: 'file-icon-pdf', docx: 'file-icon-docx', doc: 'file-icon-docx',
      txt: 'file-icon-txt', md: 'file-icon-md', csv: 'file-icon-csv',
      py: 'file-icon-code', js: 'file-icon-code', ts: 'file-icon-code',
      jsx: 'file-icon-code', tsx: 'file-icon-code',
      html: 'file-icon-code', css: 'file-icon-code', json: 'file-icon-code',
      yaml: 'file-icon-code', yml: 'file-icon-code', xml: 'file-icon-code',
      java: 'file-icon-code', c: 'file-icon-code', cpp: 'file-icon-code',
      h: 'file-icon-code', rs: 'file-icon-code', go: 'file-icon-code',
      rb: 'file-icon-code', php: 'file-icon-code', sql: 'file-icon-code',
      sh: 'file-icon-code', bat: 'file-icon-code', ps1: 'file-icon-code',
    };
    return map[ext] || 'file-icon-other';
  },

  removeFile(i) {
    this._kbFiles.splice(i, 1);
    this._renderFileList();
  },

  clearFiles() {
    this._kbFiles = [];
    this._kbTempFiles = [];
    this._renderFileList();
  },

  async goStep2() {
    if (!this._kbFiles.length) return;
    // 上传文件到后端临时目录
    const form = new FormData();
    for (const f of this._kbFiles) form.append("files", f);
    try {
      const r = await _fetch(API_BASE + "/knowledge/upload", { method: "POST", body: form, _timeout: 60000 });
      if (!r.ok) throw new Error("upload failed");
      const data = await r.json();
      this._kbTempFiles = data.files || [];
    } catch (e) {
      alert("文件上传失败: " + e.message);
      return;
    }

    // 切换到步骤2
    document.getElementById("kb-upload-step1").style.display = "none";
    document.getElementById("kb-upload-step2").style.display = "block";
    document.getElementById("kb-upload-step3").style.display = "none";
    this._setStep(2);

    // 渲染预览文件列表
    const list = document.getElementById("kb-preview-list");
    let html = '';
    for (let i = 0; i < this._kbTempFiles.length; i++) {
      const f = this._kbTempFiles[i];
      html += '<div class="kb-preview-file' + (i === 0 ? ' active' : '') + '" onclick="settings._previewUploadFile(' + i + ')">' + htmlEscape(f.name) + '</div>';
    }
    list.innerHTML = html;
    if (this._kbTempFiles.length > 0) this._previewUploadFile(0);
  },

  async _previewUploadFile(i) {
    const f = this._kbTempFiles[i];
    if (!f) return;
    // 高亮选中
    document.querySelectorAll(".kb-preview-file").forEach((el, idx) => { el.classList.toggle("active", idx === i); });
    const content = document.getElementById("kb-preview-content");
    content.innerHTML = '<p class="hint" style="text-align:center;padding:20px">加载预览...</p>';
    try {
      const r = await _fetch(API_BASE + "/knowledge/upload-preview?path=" + encodeURIComponent(f.temp_path));
      if (!r.ok) { content.textContent = "预览失败"; return; }
      const d = await r.json();
      if (d.error) { content.textContent = d.error; return; }
      content.textContent = d.content || "(空文件)";
    } catch {
      content.textContent = "预览失败";
    }
  },

  goStep1() {
    document.getElementById("kb-upload-step1").style.display = "block";
    document.getElementById("kb-upload-step2").style.display = "none";
    document.getElementById("kb-upload-step3").style.display = "none";
    document.getElementById("kb-process-results").style.display = "none";
    this._setStep(1);
  },

  _setStep(n) {
    document.querySelectorAll(".kb-step").forEach(el => {
      const s = parseInt(el.dataset.step);
      el.classList.remove("active", "done");
      if (s === n) el.classList.add("active");
      if (s < n) el.classList.add("done");
    });
  },

  async startIndexing() {
    if (!this._kbTempFiles.length || !this._currentKB) return;
    // 切换到步骤3
    document.getElementById("kb-upload-step1").style.display = "none";
    document.getElementById("kb-upload-step2").style.display = "none";
    document.getElementById("kb-upload-step3").style.display = "block";
    document.getElementById("kb-process-results").style.display = "none";
    this._setStep(3);

    const bar = document.getElementById("kb-progress-bar");
    const text = document.getElementById("kb-progress-text");
    const detail = document.getElementById("kb-progress-detail");

    bar.style.width = "5%";
    text.textContent = "正在上传并解析文件...";
    detail.innerHTML = '';

    // 显示文件列表
    for (const f of this._kbTempFiles) {
      const div = document.createElement("div");
      div.className = "kb-progress-file";
      div.innerHTML = '<span>' + htmlEscape(f.name) + '</span><span class="status-pending">等待中</span>';
      detail.appendChild(div);
    }

    const chunkSize = parseInt(document.getElementById("kb-chunk-size").value) || 1000;

    // 调用后端处理
    try {
      bar.style.width = "20%";
      text.textContent = "正在解析文件内容...";

      const r = await _fetch(API_BASE + "/knowledge/process-files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kb: this._currentKB,
          files: this._kbTempFiles,
          chunk_size: chunkSize
        }),
        _timeout: 300000  // 5分钟，处理大文件+embedding需要时间
      });

      bar.style.width = "70%";
      text.textContent = "正在构建向量索引...";

      if (!r.ok) throw new Error("处理失败");

      bar.style.width = "90%";
      text.textContent = "索引完成";

      const data = await r.json();
      const results = data.results || [];

      // 更新文件状态
      const items = detail.querySelectorAll(".kb-progress-file");
      for (let i = 0; i < items.length; i++) {
        const span = items[i].querySelector("span:last-child");
        const r = results[i];
        if (r && r.status === "ok") {
          span.className = "status-ok"; span.textContent = "完成 (" + (r.chars||0) + " 字符)";
        } else if (r && r.status === "empty") {
          span.className = "status-err"; span.textContent = "空文件";
        } else {
          span.className = "status-err"; span.textContent = r ? r.status : "失败";
        }
      }

      bar.style.width = "100%";
      text.textContent = "全部完成！";

      // 显示结果摘要
      setTimeout(() => {
        const resultList = document.getElementById("kb-process-results-list");
        let html = '';
        for (const r of results) {
          html += '<div class="result-item"><span class="result-name">' + htmlEscape(r.name) + '</span>';
          if (r.status === "ok") html += '<span class="result-ok">成功 ' + (r.chars||0) + ' chars</span>';
          else if (r.status === "empty") html += '<span class="result-err">空文件</span>';
          else html += '<span class="result-err">' + htmlEscape(r.status) + '</span>';
          html += '</div>';
        }
        resultList.innerHTML = html;
        document.getElementById("kb-process-results").style.display = "block";
      }, 500);

    } catch (e) {
      bar.style.width = "100%";
      bar.style.background = "var(--danger)";
      text.textContent = "处理失败: " + e.message;
    }
  },

  goDone() {
    // 重置上传状态
    this._kbFiles = [];
    this._kbTempFiles = [];
    document.getElementById("kb-file-input").value = "";
    this._renderFileList();
    this.goStep1();

    // 强制切到文档标签并刷新
    this._switchKBTab("docs");
    // 延迟一点确保 DOM 切换完成后再加载数据
    var self = this;
    setTimeout(function() {
      self._loadDocs();
      self.loadKB();
      self._loadKBDetail();
    }, 100);
  },
};
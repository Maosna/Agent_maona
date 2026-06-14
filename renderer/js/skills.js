/* ===== 统一技能中心 ===== */
window.skillcenter = {
  installed: [],
  market: [],
  tools: [],
  currentTab: 'installed',  // 'installed' | 'market' | 'tools'
  currentCategory: '全部',

  async init() {
    await Promise.all([this.loadInstalled(), this.loadMarket(), this.loadTools()]);
  },

  /* ---- 已安装技能 ---- */
  async loadInstalled() {
    try {
      var resp = await _fetch('/api/chat/skills');
      var data = await resp.json();
      this.installed = data.skills || [];
      if (this.currentTab === 'installed') this.render();
    } catch (e) {
      document.getElementById('skills-main').innerHTML = '<p class="ws-empty">加载失败</p>';
    }
  },

  /* ---- 技能市场 ---- */
  async loadMarket() {
    try {
      var resp = await _fetch('/api/chat/skills/market');
      var data = await resp.json();
      this.market = data.skills || [];
      if (this.currentTab === 'market') this.render();
    } catch (e) { /* 无市场数据 */ }
  },

  async toggleSkill(id) {
    var s = this.installed.find(function(x) { return x.id === id; });
    if (!s) return;
    var newState = !s.enabled;
    try {
      await _fetch('/api/chat/skills/' + id + '/toggle', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: newState}) });
      s.enabled = newState;
      // 刷新当前视图
      if (document.getElementById('skills-detail').style.display !== 'none') {
        this.refreshDetailView(id);
      } else {
        this.render();
      }
    } catch (e) { console.warn("[技能] 操作失败:", e.message || e); }
  },

  refreshDetailView(id) {
    var s = this.installed.find(function(x) { return x.id === id; });
    if (!s) return;
    // 直接更新详情页中的开关状态
    var detail = document.getElementById('skills-detail');
    var toggles = detail.querySelectorAll('.skill-toggle');
    toggles.forEach(function(t) {
      var onclick = t.getAttribute('onclick') || '';
      if (onclick.indexOf(id) !== -1) {
        t.classList.toggle('on', s.enabled);
      }
    });
  },

  async toggleSuite(suite, enabled) {
    try {
      var resp = await _fetch('/api/chat/skills/suite/' + suite + '/toggle', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: enabled}) });
      await this.loadInstalled();
      this.render();
      // 如果正在看套件详情也刷新
      if (this._currentSuiteDetail === suite) this.showSuiteDetail(suite);
    } catch (e) { console.warn("[技能] 操作失败:", e.message || e); }
  },

  showSuiteDetail(suite) {
    var allSkills = this.installed;
    var suiteSkills = allSkills.filter(function(s) { return s.suite === suite; });
    if (!suiteSkills.length) return;
    var enabledCount = suiteSkills.filter(function(s) { return s.enabled; }).length;
    var allEnabled = enabledCount === suiteSkills.length;
    this._currentSuiteDetail = suite;
    document.getElementById('skills-main').style.display = 'none';
    var d = document.getElementById('skills-detail');
    d.style.display = 'block';
    var html = '';
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">';
    html += '  <button class="btn-sm" onclick="window.skillcenter.closeDetail()">← 返回</button>';
    html += '  <h3 style="margin:0">套件: ' + htmlEscape(suite) + '</h3>';
    html += '  <span style="margin-left:auto;font-size:10px;color:var(--text-dim)">' + suiteSkills.length + ' 项' + '</span>';
    html += '</div>';
    html += '<p style="color:var(--text-dim);margin-bottom:8px">' + htmlEscape(suiteSkills[0].description) + '</p>';
    html += '<div class="skill-grid">';
    var self = this;
    suiteSkills.forEach(function(s) {
      html += '<div class="skill-card" onclick="window.skillcenter.showDetail(\'' + s.id + '\')" style="cursor:pointer">';
      html += '  <div class="skill-card-head"><span class="skill-name">' + htmlEscape(s.name) + '</span></div>';
      html += '  <div class="skill-desc">' + htmlEscape(s.description) + '</div>';
      html += '  <div class="skill-card-foot"><span class="skill-id"></span>' +
        '  <span class="skill-toggle ' + (s.enabled ? 'on' : '') + '" onclick="event.stopPropagation();window.skillcenter.toggleSkill(\'' + s.id + '\')"></span></div>';
      html += '</div>';
    });
    html += '</div>';
    d.innerHTML = html;
  },

  /* ---- 工具 ---- */
  async loadTools() {
    try {
      var resp = await _fetch('/api/chat/tools');
      var data = await resp.json();
      this.tools = data.tools || [];
      if (this.currentTab === 'tools') this.renderToolsList();
    } catch (e) { console.warn("[技能] 操作失败:", e.message || e); }
  },

  async toggleTool(name) {
    var t = this.tools.find(function(x) { return x.name === name; });
    if (!t) return;
    var newState = !t.enabled;
    try {
      await _fetch('/api/chat/tools/' + name + '/toggle', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: newState}) });
      t.enabled = newState;
      this.renderToolsList();
    } catch (e) { console.warn("[技能] 操作失败:", e.message || e); }
  },

  renderToolsList() {
    var c = document.getElementById('skills-main');
    if (!this.tools.length) { c.innerHTML = '<p class="ws-empty">无工具</p>'; return; }
    var html = '<div class="market-tabs">';
    html += '<span class="market-tab" onclick="window.skillcenter.currentTab=\'installed\';window.skillcenter.render()">已安装</span>';
    html += '<span class="market-tab active" onclick="window.skillcenter.loadTools()">工具</span>';
    html += '</div>';
    var cats = {};
    this.tools.forEach(function(t) {
      var cat = t.category || '通用';
      if (!cats[cat]) cats[cat] = [];
      cats[cat].push(t);
    });
    for (var cat in cats) {
      html += '<div class="skill-cat-title">' + htmlEscape(cat) + ' (' + cats[cat].length + ')</div>';
      html += '<div class="skill-grid">';
      var self = this;
      cats[cat].forEach(function(t) {
        html += '<div class="skill-card">';
        html += '  <div class="skill-card-head"><span class="skill-name">' + htmlEscape(t.name) + '</span></div>';
        html += '  <div class="skill-desc">' + htmlEscape(t.description) + '</div>';
        html += '  <div class="skill-card-foot"><span class="skill-id">' + htmlEscape(t.name) + '</span>';
        html += '  <span class="skill-toggle ' + (t.enabled ? 'on' : '') + '" onclick="window.skillcenter.toggleTool(\'' + t.name + '\')"></span></div>';
        html += '</div>';
      });
      html += '</div>';
    }
    c.innerHTML = html;
  },

  async installSkill(id) {
    try {
      await _fetch('/api/chat/skills/' + id + '/install', { method: 'POST' });
      await this.loadInstalled();
      this.render();
    } catch (e) { alert('安装失败'); }
  },

  async uninstallSkill(id) {
    if (!confirm('确定要卸载此技能吗？')) return;
    try {
      await _fetch('/api/chat/skills/' + id + '/uninstall', { method: 'POST' });
      await this.loadInstalled();
      this.render();
    } catch (e) { alert('卸载失败'); }
  },

  filterCategory(cat) { this.currentCategory = cat; this.render(); },

  /* ---- 渲染 ---- */
  render() {
    var container = document.getElementById('skills-main');

    // 工具 Tab 独立渲染
    if (this.currentTab === 'tools') { this.renderToolsList(); return; }

    var source = this.currentTab === 'installed' ? this.installed : this.market;
    var installedIds = this.installed.map(function(s) { return s.id; });

    // 筛选
    var skills = this.currentCategory === '全部'
      ? source.slice()
      : source.filter(function(s) { return s.category === this.currentCategory; }, this);

    var self = this;

    // 分类列表（始终生成，不管当前筛选结果）
    var allCats = ['全部'];
    source.forEach(function(s) {
      if (allCats.indexOf(s.category) === -1) allCats.push(s.category);
    });

    var html = '';
    // 分类标签
    html += '<div class="market-cats">';
    allCats.forEach(function(cat) {
      html += '<span class="market-cat-tag' + (self.currentCategory === cat ? ' active' : '') + '" onclick="window.skillcenter.filterCategory(\'' + cat + '\')">' + htmlEscape(cat) + '</span>';
    });
    html += '</div>';

    // Tab 切换
    html += '<div class="market-tabs">';
    html += '<span class="market-tab' + (this.currentTab === 'installed' ? ' active' : '') + '" onclick="window.skillcenter.currentTab=\'installed\';window.skillcenter.loadInstalled()">已安装 (' + this.installed.length + ')</span>';
    html += '<span class="market-tab' + (this.currentTab === 'tools' ? ' active' : '') + '" onclick="window.skillcenter.currentTab=\'tools\';window.skillcenter.loadTools()">工具 (' + this.tools.length + ')</span>';
    html += '</div>';

    // 空列表提示
    if (!skills.length && this.currentCategory !== '全部') {
      html += '<p class="ws-empty">该分类下暂无技能，请切换分类</p>';
      container.innerHTML = html;
      return;
    }
    if (!skills.length) {
      html += '<p class="ws-empty">' + (this.currentTab === 'installed' ? '尚未安装任何技能，去技能市场逛逛吧！' : '暂无技能') + '</p>';
      container.innerHTML = html;
      return;
    }

    // 分组：套件 vs 独立技能
    var suites = {};
    var standalone = [];
    skills.forEach(function(s) {
      if (s.suite) {
        if (!suites[s.suite]) suites[s.suite] = [];
        suites[s.suite].push(s);
      } else {
        standalone.push(s);
      }
    });

    // 卡片：套件和独立技能混排在同一网格
    html += '<div class="skill-grid">';

    for (var suite in suites) {
      var suiteSkills = suites[suite];
      var firstSkill = suiteSkills[0];
      var enabledCount = suiteSkills.filter(function(x) {
        var inst = self.installed.find(function(y) { return y.id === x.id; });
        return inst && inst.enabled;
      }).length;
      var allEnabled = enabledCount === suiteSkills.length;
      html += '<div class="skill-card" onclick="window.skillcenter.showSuiteDetail(\'' + suite + '\')">';
      html += '  <div class="skill-card-head"><span class="skill-name">' + htmlEscape(suite) + '</span><span class="suite-count">' + suiteSkills.length + ' 项</span></div>';
      html += '  <div class="skill-desc">' + htmlEscape(firstSkill.description) + '</div>';
      html += '  <div class="skill-card-foot"><span class="skill-id">' + suiteSkills.length + ' 项</span>';
      html += '  <span class="skill-toggle ' + (allEnabled ? 'on' : '') + '" onclick="event.stopPropagation();window.skillcenter.toggleSuite(\'' + suite + '\',' + (!allEnabled) + ')"></span></div>';
      html += '</div>';
    }

    standalone.forEach(function(s) {
      var installed = self.installed.find(function(x) { return x.id === s.id; });
      var enabled = installed ? installed.enabled : false;
      html += '<div class="skill-card" onclick="window.skillcenter.showDetail(\'' + s.id + '\')">';
      html += '  <div class="skill-card-head"><span class="skill-name">' + htmlEscape(s.name) + '</span></div>';
      html += '  <div class="skill-desc">' + htmlEscape(s.description) + '</div>';
      html += '  <div class="skill-card-foot"><span class="skill-id">' + htmlEscape(s.category) + '</span>';
      html += '  <span class="skill-toggle ' + (enabled ? 'on' : '') + '" onclick="event.stopPropagation();window.skillcenter.toggleSkill(\'' + s.id + '\')"></span></div>';
      html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  },

  /* ---- 详情 ---- */
  showDetail(id) {
    var s = this.installed.find(function(x) { return x.id === id; });
    if (!s) return;
    var isInstalled = this.installed.some(function(x) { return x.id === id; });
    var installed = this.installed.find(function(x) { return x.id === id; });
    document.getElementById('skills-main').style.display = 'none';
    var d = document.getElementById('skills-detail');
    d.style.display = 'block';
    d.innerHTML = [
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">',
      '  <button class="btn-sm" onclick="window.skillcenter.closeDetail()">← 返回</button>',
      '  <h3 style="margin:0">' + htmlEscape(s.name) + '</h3>',
      '  <span style="margin-left:auto;font-size:10px;color:var(--text-dim)">' + htmlEscape(s.category) + (s.author ? ' · ' + htmlEscape(s.author) : '') + '</span>',
      '</div>',
      '<p style="color:var(--text-dim);margin-bottom:4px">' + htmlEscape(s.description) + '</p>',
      (s.description_en ? '<p style="font-size:11px;color:var(--text);background:var(--bg4);padding:8px;border-radius:6px;margin-bottom:8px">' + s.description_en.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</p>' : ''),
      (s.tools && s.tools.length ? '<div style="margin:8px 0"><strong>推荐工具：</strong><span style="font-size:10px;color:var(--accent)">' + htmlEscape(s.tools.join(', ')) + '</span></div>' : ''),
      s.body ? '<h4>完整提示词</h4><pre style="background:var(--bg4);padding:12px;border-radius:8px;font-size:12px;white-space:pre-wrap;color:var(--text-dim);max-height:40vh;overflow:auto">' + s.body.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</pre>' : '',
      '<div style="margin-top:12px;display:flex;align-items:center;gap:8px">',
      isInstalled
        ? '<span class="skill-toggle ' + (installed && installed.enabled ? 'on' : '') + '" onclick="window.skillcenter.toggleSkill(\'' + id + '\')"></span>'
        : '<button class="btn-sm" onclick="window.skillcenter.installSkill(\'' + id + '\')">安装</button>',
      isInstalled ? '<button class="btn-sm" style="border-color:var(--danger);color:var(--danger)" onclick="window.skillcenter.uninstallSkill(\'' + id + '\')">卸载</button>' : '',
      '</div>'
    ].join('');
  },

  closeDetail() {
    this._currentSuiteDetail = null;
    document.getElementById('skills-main').style.display = 'block';
    document.getElementById('skills-detail').style.display = 'none';
    this.render();
  }
};

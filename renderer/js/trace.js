/** 执行 Trace 面板 — 可视化 Agent 的工具调用时间线 */

const tracePanel = {
  traces: [],
  maxTraces: 50,
  _el: null,
  _expanded: false,

  init() {
    this._el = document.getElementById("trace-panel");
    if (!this._el) return;
    // 从已存储恢复
    const saved = localStorage.getItem("maona_traces");
    if (saved) {
      try { this.traces = JSON.parse(saved); } catch {}
    }
    this.render();
  },

  add(convId, round, toolName, args, result, duration, ok) {
    this.traces.unshift({
      id: Date.now(),
      conv: convId || "?",
      round,
      tool: toolName,
      args: String(args).slice(0, 80),
      result: String(result).slice(0, 120),
      duration: Math.round(duration),
      ok,
      time: new Date().toLocaleTimeString()
    });
    if (this.traces.length > this.maxTraces) this.traces = this.traces.slice(0, this.maxTraces);
    // 持久化到 localStorage
    try { localStorage.setItem("maona_traces", JSON.stringify(this.traces)); } catch {}
    this.render();
  },

  render() {
    if (!this._el) return;
    const recent = this.traces.slice(0, 20);
    if (!recent.length) {
      this._el.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-dim)">暂无执行记录</div>';
      return;
    }
    this._el.innerHTML = recent.map((t, i) =>
      `<div class="trace-row ${t.ok ? '' : 'trace-err'}" style="
        padding:4px 10px;font-size:11px;border-bottom:1px solid var(--border);
        display:flex;gap:6px;align-items:center;font-family:var(--font-mono);
      ">
        <span style="color:${t.ok ? 'var(--success)' : 'var(--danger)'};width:12px">${t.ok ? '✓' : '✗'}</span>
        <span style="color:var(--text-dim);min-width:24px">R${t.round}</span>
        <span style="color:var(--accent);min-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.tool}</span>
        <span style="color:var(--text-dim);min-width:30px;text-align:right">${t.duration}ms</span>
        <span style="color:var(--text-dim);min-width:40px;text-align:right">${t.time}</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.6">${t.args}</span>
        ${i >= 3 ? '' : `<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.5;font-size:10px">${t.result}</span>`}
      </div>`
    ).join("");
  },

  clear() {
    this.traces = [];
    localStorage.removeItem("maona_traces");
    this.render();
  },

  toggle() {
    this._expanded = !this._expanded;
    document.getElementById("trace-container").style.display = this._expanded ? "block" : "none";
    document.getElementById("trace-toggle").textContent = this._expanded ? "▼ 执行日志" : "▶ 执行日志";
  }
};

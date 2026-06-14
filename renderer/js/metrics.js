/** Agent 指标面板 —— 追踪成功率、Token 用量、循环次数 */

const metricsPanel = {
  _el: null,
  _expanded: false,
  _data: {
    totalConversations: 0,
    totalToolCalls: 0,
    totalFailures: 0,
    avgRounds: 0,
    totalTokens: 0,
    recentSuccess: [],  // [true, false, ...]
    byProvider: {},
  },

  init() {
    this._el = document.getElementById("metrics-panel");
    if (!this._el) return;
    const saved = localStorage.getItem("maona_metrics");
    if (saved) {
      try {
        const d = JSON.parse(saved);
        Object.assign(this._data, d);
      } catch {}
    }
    this.render();
  },

  _save() {
    try { localStorage.setItem("maona_metrics", JSON.stringify(this._data)); } catch {}
  },

  recordConversation(ok, rounds, tokens, provider) {
    this._data.totalConversations++;
    this._data.totalToolCalls += rounds || 0;
    if (!ok) this._data.totalFailures++;
    this._data.totalTokens += tokens || 0;

    var prev = this._data.avgRounds || 0;
    this._data.avgRounds = Math.round(
      (prev * (this._data.totalConversations - 1) + (rounds || 0)) / this._data.totalConversations
    );

    this._data.recentSuccess.push(ok);
    if (this._data.recentSuccess.length > 50) this._data.recentSuccess.shift();

    if (provider) {
      var pb = this._data.byProvider[provider] || { calls: 0, fails: 0, tokens: 0 };
      pb.calls++;
      if (!ok) pb.fails++;
      pb.tokens += tokens || 0;
      this._data.byProvider[provider] = pb;
    }

    this._save();
    this.render();
  },

  recordToolCall(toolName, ok, duration) {
    this._data.totalToolCalls++;
    if (!ok) this._data.totalFailures++;
    this._save();
  },

  render() {
    if (!this._el) return;
    var d = this._data;
    var successRate = d.totalConversations > 0
      ? Math.round((d.totalConversations - d.totalFailures) / d.totalConversations * 100)
      : 100;

    var recentOk = d.recentSuccess.slice(-10).filter(function(v) { return v; }).length;
    var recentRate = d.recentSuccess.length > 0
      ? Math.round(recentOk / Math.min(d.recentSuccess.length, 10) * 100)
      : 100;

    this._el.innerHTML =
      '<div style="padding:10px">' +
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px">' +
        metricBox('对话总数', d.totalConversations, '') +
        metricBox('成功率', successRate + '%', successRate >= 90 ? 'var(--success)' : 'var(--danger)') +
        metricBox('最近10轮', recentRate + '%', recentRate >= 80 ? 'var(--success)' : 'var(--warning)') +
        metricBox('工具调用', d.totalToolCalls, '') +
        metricBox('平均轮次', d.avgRounds || '-', '') +
        metricBox('Token消耗', formatTokens(d.totalTokens), '') +
      '</div>' +
      '<div style="display:flex;gap:4px;align-items:center;height:8px">' +
        d.recentSuccess.slice(-30).map(function(ok) {
          return '<span style="flex:1;height:6px;border-radius:3px;background:' +
            (ok ? 'var(--success)' : 'var(--danger)') + '"></span>';
        }).join('') +
      '</div>' +
      (Object.keys(d.byProvider).length > 0 ?
        '<div style="margin-top:8px;font-size:10px;color:var(--text-dim)">' +
          Object.entries(d.byProvider).map(function(e) {
            var p = e[1];
            var pr = Math.round((p.calls - p.fails) / p.calls * 100);
            return '<div style="display:flex;gap:6px">' +
              '<span style="min-width:60px">' + e[0] + '</span>' +
              '<span>' + pr + '%</span>' +
              '<span style="opacity:.5">' + formatTokens(p.tokens) + '</span>' +
            '</div>';
          }).join('') +
        '</div>' : ''
      ) +
      '</div>';
  },

  toggle() {
    this._expanded = !this._expanded;
    document.getElementById("metrics-container").style.display = this._expanded ? "block" : "none";
  },

  reset() {
    this._data = {
      totalConversations: 0, totalToolCalls: 0, totalFailures: 0,
      avgRounds: 0, totalTokens: 0, recentSuccess: [], byProvider: {},
    };
    this._save();
    this.render();
  },
};

function metricBox(label, value, color) {
  return '<div style="background:var(--bg3);border-radius:6px;padding:6px 8px;text-align:center">' +
    '<div style="font-size:15px;font-weight:600;color:' + (color || 'var(--text)') + '">' + value + '</div>' +
    '<div style="font-size:9px;color:var(--text-dim);margin-top:2px">' + label + '</div>' +
  '</div>';
}

function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

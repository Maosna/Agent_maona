/* ===== 用量统计页 ===== */
(function() {
  var PAGE_SIZE = 50;
  window._usagePage = 0;

  function fmt(n) {
    if (n == null) return "-";
    if (n >= 1000000) return (n/1000000).toFixed(1) + "M";
    if (n >= 1000) return (n/1000).toFixed(0) + "K";
    return String(n);
  }

  function fmtCost(n) {
    if (!n || n === 0) return "$0";
    return "$" + n.toFixed(4);
  }

  function fmtTime(ts) {
    if (!ts) return "";
    var d = new Date(ts);
    var pad = function(n) { return n < 10 ? "0" + n : n; };
    return d.getFullYear() + "-" + pad(d.getMonth()+1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  async function refresh() {
    var page = window._usagePage;
    var days = document.getElementById("usage-days").value;
    var model = document.getElementById("usage-model").value;
    var token = window._sessionToken || localStorage.getItem("maona_token") || "";

    // 加载日志
    var res = await fetch("/api/usage/logs?days=" + days + "&model=" + encodeURIComponent(model) + "&limit=" + PAGE_SIZE + "&offset=" + (page * PAGE_SIZE) + "&t=" + Date.now(), { headers: { "x-session-token": token } });
    var data = await res.json();

    // 汇总卡片
    var s = data.summary || {};
    document.getElementById("stat-requests").textContent = fmt(s.requests);
    document.getElementById("stat-tokens").textContent = fmt(s.tokens_total);
    document.getElementById("stat-input").textContent = fmt(s.tokens_input);
    document.getElementById("stat-output").textContent = fmt(s.tokens_output);
    document.getElementById("stat-cost").textContent = fmtCost(s.cost);

    // 表格
    var tbody = document.getElementById("usage-table-body");
    var rows = data.rows || [];
    if (rows.length === 0) {
      tbody.innerHTML = "<tr><td colspan='6' style='text-align:center;padding:48px 24px;color:var(--text-dim);font-size:14px'>暂无用量数据<br><small style='opacity:0.5'>发送消息后将自动记录</small></td></tr>";
    } else {
      var html = "<tr><th>时间</th><th>模型</th><th>输入</th><th>输出</th><th>总计</th><th>成本</th></tr>";
      html += rows.map(function(r) {
        return "<tr>" +
          "<td>" + fmtTime(r.timestamp) + "</td>" +
          "<td>" + (r.model || "-") + "</td>" +
          "<td>" + fmt(r.tokens_input) + "</td>" +
          "<td>" + fmt(r.tokens_output) + "</td>" +
          "<td>" + fmt(r.tokens_total) + "</td>" +
          "<td>" + fmtCost(r.cost) + "</td>" +
        "</tr>";
      }).join("");
      // 汇总行
      html += "<tr style='font-weight:700;border-top:2px solid var(--border)'>" +
        "<td colspan='2'>合计（本页）</td>" +
        "<td>" + fmt(s.tokens_input) + "</td>" +
        "<td>" + fmt(s.tokens_output) + "</td>" +
        "<td>" + fmt(s.tokens_total) + "</td>" +
        "<td class='cost-high'>" + fmtCost(s.cost) + "</td>" +
      "</tr>";
      tbody.innerHTML = html;
    }

    // 分页
    var total = data.total || 0;
    var pages = Math.ceil(total / PAGE_SIZE);
    var pager = document.getElementById("usage-pager");
    if (pages <= 1) {
      pager.innerHTML = "";
    } else {
      var html = '<button ' + (page === 0 ? 'disabled' : '') + ' onclick="window.usageGoTo(0)">首页</button>';
      html += '<button ' + (page === 0 ? 'disabled' : '') + ' onclick="window.usageGoTo(' + (page-1) + ')">«</button>';
      var start = Math.max(0, page - 2);
      var end = Math.min(pages, page + 3);
      for (var i = start; i < end; i++) {
        html += '<button class="' + (i === page ? 'active' : '') + '" onclick="window.usageGoTo(' + i + ')">' + (i+1) + '</button>';
      }
      html += '<button ' + (page >= pages-1 ? 'disabled' : '') + ' onclick="window.usageGoTo(' + (page+1) + ')">»</button>';
      html += '<button ' + (page >= pages-1 ? 'disabled' : '') + ' onclick="window.usageGoTo(' + (pages-1) + ')">末页</button>';
      pager.innerHTML = html;
    }
  }

  window.usageGoTo = function(p) { window._usagePage = p; window._usageRefresh(); };
  window._usageRefresh = function() { refresh(); };

  // 筛选器
  document.getElementById("usage-days").addEventListener("change", function() { window._usagePage = 0; refresh(); });
  document.getElementById("usage-model").addEventListener("change", function() { window._usagePage = 0; refresh(); });
  document.getElementById("btn-usage-refresh").addEventListener("click", function() { refresh(); });
  document.getElementById("btn-usage-export").addEventListener("click", function() {
    var days = document.getElementById("usage-days").value;
    var model = document.getElementById("usage-model").value;
    var token = window._sessionToken || localStorage.getItem("maona_token") || "";
    window.open("/api/usage/export?days=" + days + "&model=" + encodeURIComponent(model) + "&token=" + encodeURIComponent(token));
  });
})();

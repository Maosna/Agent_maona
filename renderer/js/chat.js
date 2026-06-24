/* chat.js v1780391790 */

/* ========== 工具名翻译 ========== */

window._cnToolName = function(tool) {

  var t = (tool || "").trim();

  if (t === "read_file") return "\u8bfb\u53d6\u6587\u4ef6";

  if (t === "write_file") return "\u5199\u5165\u6587\u4ef6";

  if (t === "edit_file") return "\u7f16\u8f91\u6587\u4ef6";

  if (t === "list_files") return "\u5217\u51fa\u76ee\u5f55";

  if (t === "search_content") return "\u641c\u7d22\u5185\u5bb9";

  if (t === "run_command") return "\u6267\u884c\u547d\u4ee4";

  if (t === "web_search") return "\u7f51\u9875\u641c\u7d22";

  if (t === "web_fetch") return "\u6293\u53d6\u7f51\u9875";

  if (t === "save_memory") return "\u4fdd\u5b58\u8bb0\u5fc6";

  if (t === "read_memory") return "\u8bfb\u53d6\u8bb0\u5fc6";

  if (t === "save_daily_log") return "\u8bb0\u5f55\u65e5\u5fd7";

  return t;

};

/* ========== 任务面板（独立任务状态追踪） ========== */
var _taskRegistry = {};

function _hideTaskPanel() {
  _taskRegistry = {};
  var tp = document.getElementById("task-panel");
  if (tp) tp.style.display = "none";
}

function _renderTaskPanel() {
  var panel = document.getElementById("task-panel");
  var body = document.getElementById("task-panel-body");
  var count = document.getElementById("task-panel-count");
  if (!panel || !body || !count) return;

  var entries = [];
  for (var k in _taskRegistry) { if (_taskRegistry.hasOwnProperty(k)) entries.push(_taskRegistry[k]); }
  if (!entries.length) { panel.style.display = "none"; return; }
  panel.style.display = "";
  count.textContent = entries.length;

  var html = "";
  for (var i = 0; i < entries.length; i++) {
    var t = entries[i];
    var cls = t.status === "completed" ? "done" : t.status === "in_progress" ? "in-progress" : "";
    var progress = "";
    if (t.steps && t.steps.length && t.currentStep) {
      progress = ' <span class="task-note">' + t.currentStep + '/' + t.steps.length + '</span>';
    }
    html += '<div class="task-item ' + cls + '"><span class="task-check"></span><span class="task-name">' +
            (t.subject || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").slice(0, 80) +
            '</span>' + progress + '</div>';
  }
  body.innerHTML = html;
}

function updateTaskPanel(resultText) {
  if (!resultText) return;

  // task_create: "已创建任务 [tid]：subject\n步骤：...\n状态：..."
  var m = (resultText || "").match(/已创建任务\s*\[([^\]]+)\][：:]\s*([^\n]+)/);
  if (m) {
    var tid = m[1], subject = m[2].trim();
    var stepsLine = (resultText.match(/(?:步骤|Steps?)[：:]\s*(.+)/i) || [])[1] || "";
    var steps = stepsLine ? stepsLine.split(/→|->|,/).map(function(s){ return s.trim(); }) : [];
    _taskRegistry[tid] = { subject: subject, status: "in_progress", steps: steps, currentStep: 0 };
    _renderTaskPanel(); return;
  }

  // task_update: 中英文混合匹配
  var m2 = (resultText || "").match(/(?:任务|Task)\s*\[([^\]]+)\]\s*[→>]\s*(\S+)(?:\s*\|\s*(?:进度|Progress)[：:]?\s*(\d+)\/(\d+))?/i);
  if (m2) {
    var tid2 = m2[1];
    if (_taskRegistry[tid2]) {
      var rawStatus = m2[2];
      var normStatus = "in_progress";
      if (/完成|completed|done|ok/i.test(rawStatus)) normStatus = "completed";
      else if (/待处理|pending|waiting/i.test(rawStatus)) normStatus = "pending";
      else if (/失败|failed|error/i.test(rawStatus)) normStatus = "failed";
      _taskRegistry[tid2].status = normStatus;
      var cs = parseInt(m2[3]) || 0;
      if (cs) _taskRegistry[tid2].currentStep = cs;
    }
    _renderTaskPanel(); return;
  }
}

/* 从历史消息恢复 */
function restoreTaskPanel(messages) {
  _taskRegistry = {};
  if (!messages || !messages.length) return;
  for (var i = 0; i < messages.length; i++) {
    var m = messages[i];
    if (!m.tool_calls || !m.tool_calls.length) continue;
    for (var j = 0; j < m.tool_calls.length; j++) {
      var tc = m.tool_calls[j];
      var tname = tc.tool || (tc.function && tc.function.name);
      if (tname !== "task_create" && tname !== "task_update") continue;
      var args = tc.args || (tc.function && tc.function.arguments) || {};
      if (typeof args === "string") try { args = JSON.parse(args); } catch(e) {}

      if (tname === "task_create") {
        var subj = args.subject || "";
        var steps = args.steps || [];
        if (!subj) continue;
        var tcr = tc.result || "";
        var tidm = tcr.match(/\[([^\]]+)\]/);
        var tid = tidm ? tidm[1] : subj;
        _taskRegistry[tid] = { subject: subj, status: "in_progress", steps: steps, currentStep: 0 };
      } else if (tname === "task_update") {
        var tid = args.task_id || "";
        if (_taskRegistry[tid]) {
          _taskRegistry[tid].status = args.status || _taskRegistry[tid].status;
          if (args.step) _taskRegistry[tid].currentStep = args.step;
        }
      }
    }
  }
  _renderTaskPanel();
}

/* ========== 简版 Markdown ========== */

/* ========== Markdown 渲染（marked.js + highlight.js） ========== */

// 配置 marked
if (typeof marked !== 'undefined') {
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
  if (typeof hljs !== 'undefined') {
    marked.setOptions({
      highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
          try { return hljs.highlight(code, { language: lang }).value; }
          catch (e) {}
        }
        return code;
      }
    });
  }
}

function renderMarkdown(text) {
  if (!text) return "";
  if (typeof marked !== 'undefined') {
    var html = marked.parse(text);
    // 给代码块加复制按钮和语言标签
    html = html.replace(/<pre><code(\s+class="language-(\w+)")?/g, function(m, clsAttr, lang) {
      var langLabel = lang ? '<span class="cb-lang">' + lang + '</span>' : '';
      return '<div class="code-block">'
        + '<button class="cb-copy" onclick="copyCodeInner(this)" title="复制">'
        + '<img src="/assets/icon-copy.svg" width="14" height="14" alt="copy">'
        + '</button>'
        + langLabel
        + m;
    });
    html = html.replace(/<\/code><\/pre>/g, '</code></pre></div>');
    return html;
  }
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
}

// 保留别名兼容旧调用
function simpleMarkdown(text) { return renderMarkdown(text); }

// 代码块复制
function copyCodeInner(btn) {
  var code = btn.parentNode.querySelector('code');
  if (!code) return;
  var text = code.textContent || code.innerText || '';
  navigator.clipboard.writeText(text).then(function() {
    btn.classList.add('copied');
    var img = btn.querySelector('img');
    if (img) img.src = '/assets/icon-copy.svg';  // 保持图标，用 class 表示状态
    setTimeout(function() { btn.classList.remove('copied'); }, 1500);
  }).catch(function() {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
    btn.classList.add('copied');
    setTimeout(function() { btn.classList.remove('copied'); }, 1500);
  });
}


/* ========== ChatRenderer ========== */

function ChatRenderer(el, sendBtn, stopBtn, input, updateStatusFn, removeStatusFn) {

  this.el = el;

  this.sendBtn = sendBtn;

  this.stopBtn = stopBtn;

  this.input = input;

  this.isStreaming = false;

  this.currentAssistantMsg = null;

  this._abortPromise = null;

  this._replyEl = null;

  this._rawText = "";

  this._renderRAF = null;

  this.messages = [];



  this.updateStatus = typeof updateStatusFn === "function" ? updateStatusFn : function(msg, type) {

    if (this._streamStatus) {

      this._streamStatus.textContent = msg || "";

      this._streamStatus.style.display = "";

      this._streamStatus.className = "stream-status" + (type === "error" ? " stream-error" : "");

    }

  };

  this.removeStatus = typeof removeStatusFn === "function" ? removeStatusFn : function() {

    if (this._streamStatus) { this._streamStatus.style.display = "none"; }

  };

}



/* ---------- _wrapExecContainer ---------- */

ChatRenderer.prototype._wrapExecContainer = function(contentEl) {

  if (!this._replyEl) return;

  var batches = [];

  var current = [];

  var node = contentEl.firstChild;

  while (node && node !== this._replyEl) {

    // 先保存 nextSibling，因为 round-text 分支里 replaceChild 会让原节点脱离 DOM，nextSibling 变成 null
    var next = node.nextSibling;

    if (node.nodeType === 1 && (node.classList.contains("tool-card") || node.classList.contains("reasoning-block") || node.classList.contains("round-text") || node.classList.contains("round-text-inline"))) {
      if (node.classList.contains("round-text")) {
        var rtInline = document.createElement("div");
        rtInline.className = "round-text-inline";
        rtInline.textContent = node.textContent.substring(0, 2000);
        node.parentNode.replaceChild(rtInline, node);
        current.push(rtInline);
      } else {
        current.push(node);
      }

    }

    node = next;

  }

  if (current.length > 0) batches.push(current);

  for (var i = batches.length - 1; i >= 0; i--) {

    var b = batches[i];

    if (b === null) continue;

    if (b.length < 2) continue;

    var toolCount = b.filter(function(el) { return el.classList.contains("tool-card"); }).length;

    var reasoningCount = b.filter(function(el) { return el.classList.contains("reasoning-block"); }).length;

    var exec = document.createElement("div");

    exec.className = "execution-details collapsed";

    exec.innerHTML = '<div class="execution-header" onclick="let e=this.nextElementSibling;e.style.display=e.style.display==\'none\'?\'block\':\'none\';this.querySelector(\'.execution-arrow\').textContent=e.style.display==\'none\'?\'▶\':\'▼\'"><span class="execution-arrow">▶</span><span class="execution-summary">工具调用 ' + toolCount + ' · 过程消息 ' + reasoningCount + '</span></div><div class="execution-body" style="display:none"></div>';

    var body = exec.querySelector(".execution-body");

    contentEl.insertBefore(exec, b[0]);

    b.forEach(function(el) { body.appendChild(el); });

  }

};

/* ---------- render ---------- */


ChatRenderer.prototype.render = function(role, raw, isStreaming, abortPromise) {

  var msg = document.createElement("div");

  msg.className = "message " + role;

  var contentEl = document.createElement("div");

  contentEl.className = "message-content";

  msg.appendChild(contentEl);



  if (role === "user") {

    contentEl.innerHTML = simpleMarkdown(raw);

    this.el.appendChild(msg);

    this.el.scrollTop = this.el.scrollHeight;

    return;

  }



  this.isStreaming = true;

  this._streamStatus = document.createElement("div");
  this._streamStatus.className = "stream-status";

  this._replyEl = document.createElement("span");

  // Trace 和 Metrics 需要的跟踪变量
  this._roundCount = 0;
  this._lastContextTokens = 0;
  this._convContext = {};  // conversationId -> {tokens, budget, pct, ctxWindow, fmtTokens, fmtWindow}
  this._rawText = "";
  this._reasoningPre = null;  // 深度思考流式 pre 元素引用

  contentEl.appendChild(this._replyEl);
  contentEl.appendChild(this._streamStatus);  // spinner 放文字下面

  this.el.appendChild(msg);

  this.el.scrollTop = this.el.scrollHeight;



  this._abortPromise = abortPromise || null;

  this.sendBtn.style.display = "none";

  this.stopBtn.style.display = "";

  this.input.disabled = true;



  var timeout_ = null;

  var clearTimeout_ = function() { if (timeout_) { clearTimeout(timeout_); timeout_ = null; } };



  return {

    onMeta: function(provider, model, conversationId) {

      if (conversationId) {

        this.currentConversationId = conversationId;

      }

      if (typeof sidebar !== "undefined" && sidebar.onConversationDone) {

        sidebar.onConversationDone();

      }

    }.bind(this),



    onReasoning: function(content) {
      if (!this.isStreaming) return;

      clearTimeout_();
      this.updateStatus("深度思考中...", "tool");

      // 同一段推理流增量追加到同一块；新推理段（_reasoningPre 已置 null）才建新块
      if (!this._reasoningPre) {
        var rb = document.createElement("div");
        rb.className = "reasoning-block";
        rb.innerHTML = '<div class="reasoning-header" onclick="let b=this.nextElementSibling;b.style.display=b.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.reasoning-arrow\').textContent=b.style.display===\'none\'?\'▶\':\'▼\'"><span class="reasoning-arrow">▼</span> 深度思考</div><div class="reasoning-body"><pre></pre></div>';
        contentEl.insertBefore(rb, this._replyEl);
        this._reasoningPre = rb.querySelector("pre");
      }
      if (this._reasoningPre) {
        this._reasoningPre.textContent += content;
      }
      this.el.scrollTop = this.el.scrollHeight;

    }.bind(this),



    onToken: function(token) {
      // 已停止则忽略后续 token
      if (!this.isStreaming) return;

      clearTimeout_();

      // 推理结束，下一段推理将创建新块
      this._reasoningPre = null;

      // 折叠文字前面的所有卡片（推理块 + 工具卡片）
      contentEl.querySelectorAll(":scope > .reasoning-block, :scope > .tool-card").forEach(function(block) {

        block.classList.add("collapsed");

        var body = block.querySelector(".reasoning-body, .tool-card-result");

        if (body) body.style.display = "none";

        var arrow = block.querySelector(".reasoning-arrow, .tool-arrow");

        if (arrow) arrow.textContent = "\u25b6";

      });

      this._rawText += token;

      this._scheduleIncrementalRender(contentEl);

      var el = this.el;

      if (el.scrollHeight - el.scrollTop - el.clientHeight < 60) {

        el.scrollTop = el.scrollHeight;

      }

    }.bind(this),



    onStep: function(round, total) {
      if (!this.isStreaming) return;

      this._roundCount = round;
      // 新轮次：重置推理块指针，下一段推理会创建新卡
      this._reasoningPre = null;
      this._reasoningRound = round;
      clearTimeout_();

      this.updateStatus("\u6b65\u9aa4 " + round + "...", "tool");

    }.bind(this),



    onConfirmRequired: function(confirmId, tool, command) {

      clearTimeout_();

      var ok = confirm("\u9ad8\u98ce\u9669\u64cd\u4f5c\u786e\u8ba4\n\n\u5de5\u5177: " + tool + "\n\u547d\u4ee4: " + (command || "").slice(0, 200) + "\n\n\u662f\u5426\u7ee7\u7eed\u6267\u884c\uff1f");

      api.confirmTool(confirmId, ok).catch(function(){});

    }.bind(this),



    onToolCall: function(tool, args) {
      if (!this.isStreaming) return;

      clearTimeout_();

      // 把当前缓冲区文字（本轮的说明文字）提出来，放在工具卡前面

      if (this._replyEl && this._replyEl.textContent.trim()) {

        var roundText = document.createElement("span");

        roundText.className = "round-text";
        roundText.style.display = "none";

        roundText.textContent = this._replyEl.textContent;

        contentEl.insertBefore(roundText, this._replyEl);

        this._replyEl.textContent = "";

        this._rawText = "";

      }

      var desc = "";

      var argsShort = "";

      try { var a = JSON.parse(args); argsShort = JSON.stringify(a).slice(0, 60); } catch(e) {}

      var desc = window._cnToolName ? window._cnToolName(tool) : tool;

      this.updateStatus(desc + (argsShort ? " " + argsShort : "") + "...", "tool");

      var titleText = argsShort ? htmlEscape(desc + " " + argsShort) : htmlEscape(desc);

      var card = document.createElement("div");

      card.className = "tool-card tool-executing";
      card._startTime = Date.now();
      card._argsText = argsShort;
      card.setAttribute("data-tool", tool);
      card.innerHTML = '<div class="tool-card-header" onclick="let b=this.nextElementSibling;b.style.display=b.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.tool-arrow\').textContent=b.style.display===\'none\'?\'▶\':\'▼\'"><span class="tool-arrow">▼</span><span class="tool-card-title">' + titleText + '</span><span class="tool-card-summary">\u6267\u884c\u4e2d</span></div><div class="tool-card-result" style="display:block"><span class="tool-card-result-pending">\u7b49\u5f85\u7ed3\u679c...</span></div>';

      contentEl.insertBefore(card, this._replyEl);

      this.el.scrollTop = this.el.scrollHeight;

    }.bind(this),



    onToolResult: function(tool, result) {
      if (!this.isStreaming) return;
      clearTimeout_();

      // 任务面板实时更新
      if (tool === "task_create" || tool === "task_update") {
        updateTaskPanel(result);
      }

      var cards = contentEl.querySelectorAll(":scope > .tool-card.tool-executing");

      var card = cards[cards.length - 1];

      if (card) {

        card.classList.remove("tool-executing");

        var summary = card.querySelector(".tool-card-summary");
        var resultDiv = card.querySelector(".tool-card-result");
        if (summary) summary.textContent = "完成";
        if (resultDiv) {
          resultDiv.innerHTML = "<pre>" + (result || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") + "</pre>";
        }
        var arrow = card.querySelector(".tool-arrow");
        if (arrow) arrow.textContent = "▶";
        card.classList.add("collapsed");
        var bodyEl = card.querySelector(".tool-card-result");
        if (bodyEl) bodyEl.style.display = "none";

        // 预览动作：检测 live_preview 返回的 {"action":"preview", ...}
      try {
        var parsed = JSON.parse(result);
        if (parsed.action === "preview" && parsed.path) {
          if (window.electronAPI && window.electronAPI.previewHtml) {
            window.electronAPI.previewHtml(parsed.path);
          } else {
            window.open("file:///" + parsed.path.replace(/\\/g, "/"), "_blank");
          }
        }
      } catch (_) {}
      }

    }.bind(this),



    onDone: function() {

      clearTimeout_();

      // 取消 pending 的增量渲染，避免覆盖格式化输出
      if (this._renderRAF) { cancelAnimationFrame(this._renderRAF); this._renderRAF = null; }

      // 折叠所有卡片（流式结束，让用户看到紧凑的结果）
      contentEl.querySelectorAll(":scope > .reasoning-block, :scope > .tool-card").forEach(function(block) {

        block.classList.add("collapsed");

        var body = block.querySelector(".reasoning-body, .tool-card-result");

        if (body) body.style.display = "none";

        var arrow = block.querySelector(".reasoning-arrow, .tool-arrow");

        if (arrow) arrow.textContent = "\u25b6";

      });

      this._wrapExecContainer(contentEl);

      if (this._replyEl && this._rawText) {

        this._replyEl.innerHTML = simpleMarkdown(this._rawText);

        // 语法高亮：对代码块调用 highlight.js
        if (typeof hljs !== "undefined") {

          this._replyEl.querySelectorAll("pre code").forEach(function(b) { hljs.highlightElement(b); });

        }

      }

      this.isStreaming = false;

      this.sendBtn.style.display = "";

      this.stopBtn.style.display = "none";

      this.input.disabled = false;

      this.input.focus();

      this.currentAssistantMsg = null;

      this._abortPromise = null;

      if (typeof sidebar !== "undefined" && sidebar.onConversationDone) {

        sidebar.onConversationDone();

      }

      this.removeStatus();
      this._addCopyButton(msg, contentEl);

    }.bind(this),



    onSystem: function(msg) {
      // 系统消息：显示为短暂状态提示，不混入文本流
      this.updateStatus(msg, "tool", 3000);
    }.bind(this),


    onError: function(e) {

      clearTimeout_();

      var errMsg = "\u9519\u8bef: " + e;

      console.error("[onError]", e);

      app && app.showErrorToast && app.showErrorToast(errMsg);

      this.updateStatus(errMsg, "error");

      var errSpan = document.createElement("span");

      errSpan.style.color = "var(--danger)";

      errSpan.textContent = "[\u9519\u8bef: " + e + "]";

      if (this._replyEl) this._replyEl.appendChild(errSpan);

      if (this._replyEl && !this._rawText) {

        var msgDiv = this._replyEl.closest(".message");

        if (msgDiv) msgDiv.remove();

      }

      this._replyEl = null;

      this._streamStatus = null;

      this.isStreaming = false;

      this.sendBtn.style.display = "";

      this.stopBtn.style.display = "none";

      this.input.disabled = false;

      this.input.focus();

      this.currentAssistantMsg = null;

      this._abortPromise = null;

      if (typeof sidebar !== "undefined" && sidebar.onConversationDone) {

        sidebar.onConversationDone();

      }

      this.removeStatus();

    }.bind(this),

    onContext: function(tokens, budget, pct, meta) {
      var ring = document.getElementById("context-ring-fill");
      var pctEl = document.getElementById("context-ring-pct");
      if (!ring || !pctEl) return;
      var ctxWindow = (meta && meta.context_window) ? meta.context_window : (budget || 200000);
      var realPct = ctxWindow > 0 ? Math.min(100, Math.round(tokens / ctxWindow * 100)) : 0;
      var offset = 56.55 * (1 - Math.min(1, realPct / 100));
      ring.setAttribute("stroke-dashoffset", offset);
      ring.setAttribute("stroke", realPct > 80 ? "var(--danger)" : realPct > 50 ? "var(--info)" : "var(--accent2)");
      var fmt = function(n) {
        if (n >= 1000000) return (n/1000000).toFixed(1) + "M";
        if (n >= 1000) return (n/1000).toFixed(0) + "K";
        return String(n);
      };
      pctEl.textContent = realPct + "% · " + fmt(tokens) + " / " + fmt(ctxWindow);
      // 保存每对话的上下文状态
      var cid = this.currentConversationId;
      if (cid && this._convContext) {
        this._convContext[cid] = { tokens: tokens, budget: budget, pct: pct, ctxWindow: ctxWindow, realPct: realPct };
      }
    }

  };

};



/* ---------- 增量渲染 ---------- */

ChatRenderer.prototype._scheduleIncrementalRender = function(contentEl) {

  if (this._renderRAF) return;

  this._renderRAF = requestAnimationFrame(function() {

    this._renderRAF = null;

    this._doIncrementalRender(contentEl);

  }.bind(this));

};



ChatRenderer.prototype._isIncompleteTable = function(text) {

  var lastBar = text.lastIndexOf("|");

  if (lastBar < 0) return false;

  var after = text.slice(lastBar);

  if (after.includes("<br>") || after.includes("\n")) return false;

  return after.split("|").length < 3;

};



ChatRenderer.prototype._doIncrementalRender = function(contentEl) {
  if (!this._replyEl || !this._rawText) return;
  var raw = this._rawText;
  if (this._isIncompleteTable(raw)) return;
  var codeOpen = (raw.match(/```/g) || []).length;
  if (codeOpen % 2 !== 0) return;
  // 流式渲染只用 textContent 显示原文，避免 marked.parse 中间态乱码
  this._replyEl.textContent = raw;
};



/* ---------- sendMessage ---------- */

ChatRenderer.prototype.sendMessage = async function(text) {

  if (!text || this.isStreaming) return;

  // 处理上传的文件：Electron 下传路径，AI 用 read_file 工具按需读取
  var fullText = text;
  var files = this._uploadedFiles || [];
  var sentFiles = [];  // 记录文件名，用于消息气泡展示
  if (files.length > 0) {
    var pathBlocks = [];
    for (var i = 0; i < Math.min(files.length, 5); i++) {
      var fname = files[i].name;
      var fpath = files[i].path || "";
      var isImg = files[i].type && files[i].type.startsWith("image/");
      sentFiles.push(fname);
      if (fpath) {
        if (isImg) {
          pathBlocks.push("【图片: " + fname + "】\n路径: " + fpath + "\n(可尝试用 ImageGen 工具或直接分析路径)");
        } else {
          pathBlocks.push("【文件: " + fname + "】\n路径: " + fpath);
        }
      } else {
        // 无路径回退（网页端）：读内容
        try {
          var content = await new Promise(function(resolve, reject) {
            var reader = new FileReader();
            reader.onload = function() { resolve(reader.result); };
            reader.onerror = function() { reject(reader.error); };
            reader.readAsText(files[i]);
          });
          pathBlocks.push("【文件: " + fname + "】\n" + content.slice(0, 3000));
        } catch (e) {
          pathBlocks.push("【文件: " + fname + "】\n[读取失败]");
        }
      }
    }
    if (pathBlocks.length > 0) {
      fullText = text + "\n\n--- 附件 ---\n" + pathBlocks.join("\n\n");
    }
    // 清理预览（数据保留 sentFiles 用于气泡展示）
    this.clearFiles();
    this._uploadedFiles = [];
  }

  var messages = (this.messages || []).concat([{ role: "user", content: fullText }]);

  this.messages = messages;

  var userMsg = document.createElement("div");

  userMsg.className = "message user";

  var userContent = document.createElement("div");

  userContent.className = "message-content";

  userContent.innerHTML = simpleMarkdown(text);

  userMsg.appendChild(userContent);

  // 显示已发送的文件标签
  if (sentFiles.length > 0) {
    var tagsDiv = document.createElement("div");
    tagsDiv.className = "message-file-tags";
    tagsDiv.innerHTML = sentFiles.map(function(f) {
      return '<span class="file-tag">' + f.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") + '</span>';
    }).join("");
    userMsg.appendChild(tagsDiv);
  }

  this.el.appendChild(userMsg);

  this.el.scrollTop = this.el.scrollHeight;



  var modelSelect = document.getElementById("model-select");

  var personaSelect = document.getElementById("persona-select");

  var modelVal = modelSelect ? modelSelect.value : "";

  var personaId = personaSelect ? personaSelect.value : "default";

  var parts = modelVal.includes(":") ? modelVal.split(":") : ["", ""];
  var provider = parts[0];
  var model = parts[1];

  // "自动"模式：清空 provider/model，后端自动选择最佳可用模型
  if (modelVal === "_auto") {
    provider = "";
    model = "";
    await api.setPref("last_model", "_auto");
  }

  var projectId = app ? app.getCurrentProject() : "agent_maona";

  var workspace = app ? app.workspacePath : null;



  if (!workspace && app) {

    if (typeof app.ensureWorkspace === "function") {

      workspace = await app.ensureWorkspace();

    }

    if (!workspace) {
      // 无工作空间时直接传 null，对话存入"任务"区
      workspace = null;
    }

  }



  var wm = this.el.querySelector(".welcome-msg");

  if (wm) wm.style.display = "none";

  var bar = document.getElementById("ws-bar");

  if (bar) bar.style.display = "none";



  var handlers = this.render("assistant", "", true, null);

  this.updateStatus("\u7b49\u5f85\u6a21\u578b\u54cd\u5e94...", "tool");



  try {

    if (typeof api === "undefined") throw new Error("api \u5bf9\u8c61\u672a\u5b9a\u4e49");

    if (typeof api.chatStream !== "function") throw new Error("api.chatStream \u4e0d\u662f\u51fd\u6570");

    var controller = api.chatStream(

      messages, provider || "", projectId, workspace, model || null,

      this.currentConversationId, personaId, (app && app.currentMode) || "craft", handlers

    );

    if (!controller) throw new Error("api.chatStream \u8fd4\u56de null");

    this._abortPromise = controller;

  } catch (e) {

    var errMsg = "\u53d1\u9001\u5931\u8d25: " + (e.message || e);

    console.error("[sendMessage]", e);

    app && app.showErrorToast && app.showErrorToast(errMsg);

    if (this._replyEl) {

      var msgDiv = this._replyEl.closest(".message");

      if (msgDiv) msgDiv.remove();

    }

    this._replyEl = null;

    this._streamStatus = null;

    this.isStreaming = false;

    if (this.sendBtn) this.sendBtn.style.display = "";

    if (this.stopBtn) this.stopBtn.style.display = "none";

    if (this.input) { this.input.disabled = false; this.input.focus(); }

  }

};



/* ---------- newChat ---------- */

ChatRenderer.prototype.newChat = function() {

  this.el.innerHTML = '<div class="welcome-msg"><h2>Maona</h2><p>主人好，现在要做什么？</p></div>';

  // 清除任务面板
  _hideTaskPanel();

  this.isStreaming = false;

  this.currentAssistantMsg = null;

  this._abortPromise = null;

  this._replyEl = null;

  this._rawText = "";

  this._streamStatus = null;

  this.messages = [];

  this.currentConversationId = null;

  // 重置上下文用量环
  var ring = document.getElementById("context-ring-fill");
  var pctEl = document.getElementById("context-ring-pct");
  if (ring) { ring.setAttribute("stroke-dashoffset", "56.55"); ring.setAttribute("stroke", "var(--accent2)"); }
  if (pctEl) pctEl.textContent = "";

  if (this.input) { this.input.disabled = false; this.input.focus(); }

  if (this.sendBtn) this.sendBtn.style.display = "";

  if (this.stopBtn) this.stopBtn.style.display = "none";

};

/* ---------- _hasDraft ---------- */

ChatRenderer.prototype._hasDraft = function() {

  return this.input && this.input.value.trim().length > 0;

};



/* ---------- clearFiles ---------- */

ChatRenderer.prototype.clearFiles = function() {

  var preview = document.getElementById("drop-preview");

  if (preview) preview.style.display = "none";

  var filesDiv = document.getElementById("drop-files");

  if (filesDiv) filesDiv.innerHTML = "";

};


/* ---------- 文件拖拽上传 ---------- */
ChatRenderer.prototype._initDragDrop = function() {
  var self = this;
  var overlay = document.getElementById("drop-overlay");
  if (!overlay) return;

  var dragCounter = 0;
  var _isSettingsActive = function() {
    var s = document.getElementById("page-settings");
    return s && s.classList.contains("active");
  };
  document.addEventListener("dragenter", function(e) { e.preventDefault(); if (_isSettingsActive()) return; dragCounter++; if (dragCounter === 1) overlay.style.display = "flex"; });
  document.addEventListener("dragleave", function(e) { e.preventDefault(); if (_isSettingsActive()) return; dragCounter--; if (dragCounter <= 0) { overlay.style.display = "none"; dragCounter = 0; } });
  document.addEventListener("dragover", function(e) { if (!_isSettingsActive()) e.preventDefault(); });

  document.addEventListener("drop", function(e) {
    if (_isSettingsActive()) return;
    e.preventDefault();
    overlay.style.display = "none";
    dragCounter = 0;
    var files = e.dataTransfer.files;
    if (!files.length) return;
    // 显示预览
    var preview = document.getElementById("drop-preview");
    var filesDiv = document.getElementById("drop-files");
    preview.style.display = "block";
    var html = "";
    for (var i = 0; i < files.length; i++) {
      var fname = files[i].name.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
      html += '<div class="drop-file-item"><span>' + fname + '</span><span class="file-remove" onclick="this.parentElement.remove();if(!document.querySelector(\'.drop-file-item\'))document.getElementById(\'drop-preview\').style.display=\'none\'">x</span></div>';
    }
    filesDiv.innerHTML = html;
    // 存储文件引用（保留 Electron 的 path 属性用于后端读取）
    self._uploadedFiles = [];
    for (var i = 0; i < files.length; i++) {
      self._uploadedFiles.push(files[i]);
    }
    self.input.focus();
  });
};



/* ---------- init / stopStreaming ---------- */

ChatRenderer.prototype.init = function() {

  if (this.stopBtn) {

    this.stopBtn.addEventListener("click", this.stopStreaming.bind(this));

  }

  document.addEventListener("keydown", function(e) {

    if (e.key === "Escape" && this.isStreaming) {

      e.preventDefault();

      this.stopStreaming();

    }

  }.bind(this));

  this._initDragDrop();

};



ChatRenderer.prototype.stopStreaming = function() {

  if (this._abortPromise) { this._abortPromise.abort(); }

  this.updateStatus("\u5df2\u505c\u6b62", "error");

  this.isStreaming = false;

  this.sendBtn.style.display = "";

  this.stopBtn.style.display = "none";

  this.input.disabled = false;

  this.input.focus();

  this._abortPromise = null;

  setTimeout(this.removeStatus.bind(this), 5000);

};



/* ---------- 恢复历史对话 ---------- */

function restoreConversationMessages(messages, conversationId) {

  var el = document.getElementById("chat-messages");

  el.innerHTML = "";

  window.chat.messages = messages.filter(function(m) { return m.role === "user" || m.role === "assistant" || m.role === "tool"; }).map(function(m) {

    var msg = { role: m.role, content: m.content || "" };

    if (m.reasoning_content || m.reasoning) msg.reasoning = m.reasoning_content || m.reasoning;

    if (m.tool_calls) msg.tool_calls = m.tool_calls;

    return msg;

  });

  window.chat._replyEl = null;

  window.chat._streamStatus = null;

  window.chat._rawText = "";

  // 保留 conversationId 以便后续消息正确关联
  if (conversationId) {
    window.chat.currentConversationId = conversationId;
    // 恢复该对话的上下文用量显示
    var saved = window.chat._convContext && window.chat._convContext[conversationId];
    if (saved) {
      var ring = document.getElementById("context-ring-fill");
      var pctEl = document.getElementById("context-ring-pct");
      if (ring && pctEl) {
        var offset = 56.55 * (1 - Math.min(1, (saved.realPct || 0) / 100));
        ring.setAttribute("stroke-dashoffset", offset);
        ring.setAttribute("stroke", (saved.realPct || 0) > 80 ? "var(--danger)" : (saved.realPct || 0) > 50 ? "var(--info)" : "var(--accent2)");
        var fmt = function(n) {
          if (n >= 1000000) return (n/1000000).toFixed(1) + "M";
          if (n >= 1000) return (n/1000).toFixed(0) + "K";
          return String(n);
        };
        pctEl.textContent = (saved.realPct || 0) + "% · " + fmt(saved.tokens || 0) + " / " + fmt(saved.ctxWindow || 200000);
      }
    }
  }

  // 懒加载分页：保留有内容或工具调用的消息
  var allMsgData = messages.filter(function(m) { return m.role === "user" || m.role === "assistant"; }).filter(function(m) { return m.content || (m.tool_calls && m.tool_calls.length > 0); });
  if (!allMsgData.length) return;

  var renderedCount = 0;

  var PAGE_SIZE = 30;

  function renderAssistantHTML(msg) {

    var html = "";

    var hasTools = msg.tool_calls && msg.tool_calls.length > 0;

    if (hasTools) {
      // 如果 content 为空但工具调用存在，显示中断标记
      var markText = msg.content || ('[已中断，完成 ' + msg.tool_calls.length + ' 个工具调用]');
      var reasonings = (msg.reasoning_content || msg.reasoning || "").split("\x00").filter(Boolean);

      var tcs = msg.tool_calls;

      var batchTools = 0;

      var batchReasonings = 0;

      var batchHtml = "";

      var flushBatch = function() {

        if (batchTools + batchReasonings < 2) { html += batchHtml; batchTools = 0; batchReasonings = 0; batchHtml = ""; return; }

        html += '<div class="execution-details collapsed"><div class="execution-header" onclick="let e=this.nextElementSibling;e.style.display=e.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.execution-arrow\').textContent=e.style.display===\'none\'?\'▶\':\'▼\'"><span class="execution-arrow">▶</span><span class="execution-summary">工具调用 ' + batchTools + ' \u00b7 过程消息 ' + batchReasonings + '</span></div><div class="execution-body" style="display:none">' + batchHtml + '</div></div>';

        batchTools = 0;

        batchReasonings = 0;

        batchHtml = "";

      };

      for (var i = 0; i < tcs.length; i++) {

        var tc = tcs[i];

        var rText = reasonings[i] || "";

        if (tc.round_text) { batchReasonings++; var safeRT = tc.round_text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); batchHtml += '<div class="round-text-inline">' + safeRT.substring(0, 2000) + '</div>'; }

        if (rText) { batchReasonings++; batchHtml += '<div class="reasoning-block collapsed"><div class="reasoning-header" onclick="let b=this.nextElementSibling;b.style.display=b.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.reasoning-arrow\').textContent=b.style.display===\'none\'?\'▶\':\'▼\'"><span class="reasoning-arrow">▶</span> 深度思考</div><div class="reasoning-body" style="display:none"><pre>' + rText.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") + '</pre></div></div>'; }

        var rawName = (tc.tool || (tc.function && tc.function.name) || "工具").trim();

        var tcName = window._cnToolName ? window._cnToolName(rawName) : rawName;

        var tcArgs = tc.args || (tc.function && tc.function.arguments) || {};

        var argsShort = "";

        try { argsShort = JSON.stringify(tcArgs).slice(0, 60); } catch(e) {}

        var titleText = htmlEscape(argsShort ? tcName + " " + argsShort : tcName);

        var tcResult = tc.result || (tc.function && tc.function.result) || "";

        batchTools++;

        batchHtml += '<div class="tool-card collapsed"><div class="tool-card-header" onclick="let b=this.nextElementSibling;b.style.display=b.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.tool-arrow\').textContent=b.style.display===\'none\'?\'▶\':\'▼\'"><span class="tool-arrow">▶</span><span class="tool-card-title">' + titleText + '</span><span class="tool-card-summary">完成</span></div><div class="tool-card-result" style="display:none"><pre>' + (tcResult || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") + '</pre></div></div>';

      }

      flushBatch();

      return html + '<span>' + simpleMarkdown(markText) + '</span>';

    } else {

      if (msg.reasoning_content || msg.reasoning) {

        html += '<div class="reasoning-block collapsed"><div class="reasoning-header" onclick="let b=this.nextElementSibling;b.style.display=b.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.reasoning-arrow\').textContent=b.style.display===\'none\'?\'▶\':\'▼\'"><span class="reasoning-arrow">▶</span> 深度思考</div><div class="reasoning-body" style="display:none"><pre>' + ((msg.reasoning_content || msg.reasoning) || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") + '</pre></div></div>';

      }

      return html + '<span>' + simpleMarkdown(msg.content || "") + '</span>';

    }

  }

  function renderMore() {

    var start = Math.max(0, allMsgData.length - renderedCount - PAGE_SIZE);

    var batch = allMsgData.slice(start, allMsgData.length - renderedCount);

    if (!batch.length) return;

    renderedCount += batch.length;

    var oldBtn = el.querySelector(".load-more-btn");

    if (oldBtn) oldBtn.remove();

    var ref = el.firstChild;

    batch.forEach(function(msg) {

      var m = document.createElement("div");

      m.className = "message " + msg.role;

      var content = document.createElement("div");

      content.className = "message-content";

      if (msg.role === "user") {
        // 恢复用户消息时，附件内容折叠为文件标签
        var userText = msg.content || "";
        var attachIdx = userText.indexOf("\n\n--- 附件 ---") >= 0
          ? userText.indexOf("\n\n--- 附件 ---")
          : userText.indexOf("\n\n--- 附件内容 ---");
        var fileTags = "";
        if (attachIdx >= 0) {
          var mainText = userText.slice(0, attachIdx);
          var attachBlock = userText.slice(attachIdx);
          // 提取文件名
          var fnames = (attachBlock.match(/【文件:\s*([^】]+)】/g) || []).map(function(m) {
            return m.replace(/【文件:\s*/g, "").replace(/】/g, "");
          });
          fileTags = fnames.length > 0
            ? '<div class="message-file-tags" style="margin-top:6px">' + fnames.map(function(f) {
                return '<span class="file-tag">' + f.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") + '</span>';
              }).join("") + '</div>'
            : "";
          content.innerHTML = (mainText ? simpleMarkdown(mainText) : "") + fileTags;
        } else {
          content.innerHTML = simpleMarkdown(userText);
        }

      } else {

        content.innerHTML = renderAssistantHTML(msg);

      }

      m.appendChild(content);

      if (msg.role === "assistant") {
        window.chat._addCopyButton(m, content);
      }

      el.insertBefore(m, ref);

    });

    // 语法高亮
    if (typeof hljs !== "undefined") {
      batch.forEach(function(msg) {
        var mEl = (msg.role === "user" ? el.querySelector(".message.user:last-child") : el.querySelector(".message.assistant:first-child"));
        if (mEl) mEl.querySelectorAll("pre code").forEach(function(b) { hljs.highlightElement(b); });
      });
    }

    if (renderedCount < allMsgData.length) {

      var btn = document.createElement("div");

      btn.className = "load-more-btn";

      btn.textContent = "▲ 显示更早消息（" + (allMsgData.length - renderedCount) + " 条）";

      btn.onclick = renderMore;

      el.insertBefore(btn, el.firstChild);

    }

  }

  renderMore();

  el.scrollTop = el.scrollHeight;

}

/* ---------- 复制按钮 ---------- */
ChatRenderer.prototype._addCopyButton = function(msgEl, contentEl) {
  if (msgEl.querySelector(".copy-btn")) return;

  var btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.title = "复制回复";
  btn.textContent = "复制";
  btn.onclick = function(e) {
    e.stopPropagation();
    var clone = contentEl.cloneNode(true);
    clone.querySelectorAll(".tool-card, .reasoning-block, .stream-status, .copy-btn, .exec-container, .tool-result-container, .tool-call-container").forEach(function(el) { el.remove(); });
    var text = clone.textContent.trim();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function() {
        btn.textContent = "已复制";
        btn.classList.add("copied");
        setTimeout(function() { btn.textContent = "复制"; btn.classList.remove("copied"); }, 1500);
      });
    } else {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); document.body.removeChild(ta);
      btn.textContent = "已复制";
      btn.classList.add("copied");
      setTimeout(function() { btn.textContent = "复制"; btn.classList.remove("copied"); }, 1500);
    }
  };
  msgEl.appendChild(btn);
};



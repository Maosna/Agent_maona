/** API 请求封装 */
const API_BASE = "http://127.0.0.1:8765/api";
let _sessionToken = "";

async function _getToken() {
  if (!_sessionToken) {
    try {
      const r = await globalThis.fetch("http://127.0.0.1:8765/api/token");
      _sessionToken = (await r.json()).token || "";
    } catch {
      _sessionToken = "";
      console.warn("[Maona] 获取 session token 失败，后端可能未启动");
    }
  }
  return _sessionToken;
}

// 强制重新获取 Token（后端重启后调用）
async function _refreshToken() {
  _sessionToken = "";
  return await _getToken();
}

// 后端 session token 注入中间件（仅 localhost，无实际网络开销）
async function _fetch(url, options = {}) {
  const token = await _getToken();
  var timeout = options._timeout || 30000;
  delete options._timeout;
  var ctrl = new AbortController();
  var timer = setTimeout(function() { ctrl.abort(); }, timeout);
  // 将外部 signal 与内部超时合并：任一触发都终止请求
  if (options.signal) {
    if (options.signal.aborted) { ctrl.abort(); }
    else { options.signal.addEventListener("abort", function() { ctrl.abort(); }); }
  }
  try {
    let resp = await globalThis.fetch(url, { ...options, signal: ctrl.signal, headers: { ...(options.headers || {}), "x-session-token": token } });
    // Token 失效时（403），重新获取后重试一次
    if (resp.status === 403) {
      await _refreshToken();
      resp = await globalThis.fetch(url, { ...options, signal: ctrl.signal, headers: { ...(options.headers || {}), "x-session-token": _sessionToken } });
    }
    return resp;
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("请求超时（" + (timeout/1000) + "秒），请稍后重试");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

const api = {
  // ========== 对话 ==========
  chatStream(messages, provider = "", projectId = "agent_maona", workspace = null, model = null, conversationId = null, personaId = null, mode = "craft", handlers) {
    const controller = new AbortController();
    let body;
    try {
      body = JSON.stringify({
        messages,
        provider: provider || null,
        model: model || null,
        project_id: projectId,
        workspace: workspace || null,
        conversation_id: conversationId || null,
        persona_id: personaId || null,
        mode: mode || "craft",
      });
    } catch (e) {
      handlers.onError?.(e.message);
      return controller;
    }

    // 在后台执行流读取，立即返回 controller
    (async () => {
    try {
      const resp = await _fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: controller.signal,
      });

      if (!resp.ok) {
        var errText = "";
        try { errText = await resp.text(); } catch (_) {}
        throw new Error("请求失败 (HTTP " + resp.status + "): " + (errText || resp.statusText));
      }
      const reader = resp.body?.getReader();
      if (!reader) throw new Error(`后端响应无效 (status ${resp.status})`);
      const decoder = new TextDecoder();
      let buffer = "";

      try {
      while (true) {
        // 检查停止信号：用户点了停止按钮则立即终止
        if (controller.signal.aborted) {
          reader.cancel();
          break;
        }
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              switch (data.type) {
                case "meta":
                  window._modelContextWindow = data.context_window || 0;
                  handlers.onMeta?.(data.provider, data.model, data.conversation_id, data);
                  break;
                case "token":
                  handlers.onToken?.(data.content);
                  break;
                case "context":
                  handlers.onContext?.(data.tokens, data.budget, data.pct, { context_window: data.context_window, model: data.model });
                  break;
                case "tool_call":
                  handlers.onToolCall?.(data.tool, data.args);
                  break;
                case "tool_result":
                  handlers.onToolResult?.(data.tool, data.result);
                  break;
                case "confirm_required":
                  handlers.onConfirmRequired?.(data.confirm_id, data.tool, data.command);
                  break;
                case "done":
                  handlers.onDone?.();
                  break;
                case "reasoning":
                  handlers.onReasoning?.(data.content);
                  break;
                case "step":
                  handlers.onStep?.(data.round, data.total);
                  break;
                case "error":
                  handlers.onError?.(data.content);
                  break;
                case "system":
                  // 系统消息：显示为短暂提示，不混入文本流
                  handlers.onSystem?.(data.content);
                  break;
              }
            } catch (e) {
              // 忽略格式错误的 SSE 行，不中断整条流
              console.warn("[SSE] 解析失败:", line.slice(6, 80), e.message);
            }
          }
        }
      }
      } catch (readerErr) {
        // 流中断分类：AbortError = 用户取消，其他 = 网络/读取错误
        if (readerErr.name === "AbortError") {
          handlers.onDone?.();
        } else {
          console.warn("[SSE] 流读取异常:", readerErr.message || readerErr);
          handlers.onError?.("连接中断: " + (readerErr.message || "未知错误"));
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        const msg = err.message || String(err);
        handlers.onError?.(msg);
      } else {
        handlers.onDone?.(); // 用户主动停止时通知完成
      }
    }
    })();
    return controller;
  },

  // ========== 人设管理 ==========
  async getPersonas() {
    const resp = await _fetch(`${API_BASE}/personas`);
    return await resp.json();
  },

  async savePersona(data) {
    const resp = await _fetch(`${API_BASE}/personas`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
    return await resp.json();
  },

  async deletePersona(id) {
    await _fetch(`${API_BASE}/personas/${encodeURIComponent(id)}`, { method: "DELETE" });
  },

  // ========== 图片 OCR ==========
  async ocrPreview(dataUrl) {
    const resp = await _fetch(`${API_BASE}/files/ocr-preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_url: dataUrl }),
    });
    return await resp.json();
  },

  // ========== 健康检查 ==========
  async health() {
    try {
      const resp = await _fetch(`${API_BASE}/health`);
      return await resp.json();
    } catch {
      return null;
    }
  },

  // ========== 文件 ==========
  async listFiles(path) {
    const url = path ? `${API_BASE}/files/list?path=${encodeURIComponent(path)}` : `${API_BASE}/files/list`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  async readFile(path) {
    const resp = await _fetch(`${API_BASE}/files/read?path=${encodeURIComponent(path)}`);
    return await resp.json();
  },

  async getHome() {
    const resp = await _fetch(`${API_BASE}/files/home`);
    return await resp.json();
  },

  // ========== Provider 管理 ==========
  async listProviders() {
    const resp = await _fetch(`${API_BASE}/settings/providers`);
    return await resp.json();
  },

  async addProvider(name, apiUrl, apiKey) {
    const resp = await _fetch(`${API_BASE}/settings/providers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, api_url: apiUrl, api_key: apiKey }),
    });
    return await resp.json();
  },

  async removeProvider(name) {
    const resp = await _fetch(`${API_BASE}/settings/providers/${name}`, { method: "DELETE" });
    return await resp.json();
  },

  async fetchModels(name) {
    const resp = await _fetch(`${API_BASE}/settings/providers/${name}/fetch-models`, { method: "POST" });
    return await resp.json();
  },

  async getModels(name) {
    const resp = await _fetch(`${API_BASE}/settings/providers/${name}/models`);
    return await resp.json();
  },

  async toggleModel(name, modelId, enabled) {
    const resp = await _fetch(`${API_BASE}/settings/providers/${name}/toggle-model?model_id=${encodeURIComponent(modelId)}&enabled=${enabled ? "true" : "false"}`, { method: "POST" });
    return await resp.json();
  },

  async getAvailableProviders() {
    const resp = await _fetch(`${API_BASE}/chat/providers/available`);
    return await resp.json();
  },

  async confirmTool(confirmId, ok) {
    const resp = await _fetch(`${API_BASE}/chat/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm_id: confirmId, confirmed: ok }),
    });
    return await resp.json();
  },

  // ========== 技能 ==========
  async getSkills() {
    const resp = await _fetch(`${API_BASE}/files/skills/list`);
    return await resp.json();
  },
  async saveSkills(ids) {
    const resp = await _fetch(`${API_BASE}/files/skills/toggle`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_ids: ids }),
    });
    return await resp.json();
  },

  async getBalance(provider, model = "") {
    let url = `${API_BASE}/settings/providers/${encodeURIComponent(provider)}/balance`;
    if (model) url += `?model=${encodeURIComponent(model)}`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  // ========== 记忆 ==========
  async getLongTermMemory(project = "agent_maona", workspace = null) {
    let url = `${API_BASE}/memory/longterm?project=${project}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  async saveLongTermMemory(project, content, workspace = null) {
    let url = `${API_BASE}/memory/longterm?content=${encodeURIComponent(content)}&project=${project}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url, { method: "PUT" });
    return await resp.json();
  },

  async getDailyMemory(project = "agent_maona", date, workspace = null) {
    let url = `${API_BASE}/memory/daily?project=${project}`;
    if (date) url += `&date_str=${date}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  async getMemoryContext(project = "agent_maona", workspace = null) {
    let url = `${API_BASE}/memory/context?project=${project}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  async getDailyLogs(project = "agent_maona", workspace = null) {
    let url = `${API_BASE}/memory/logs?project=${project}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  async readDailyLog(project = "agent_maona", date, workspace = null) {
    let url = `${API_BASE}/memory/daily?project=${project}&date_str=${date}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url);
    return await resp.json();
  },

  async listProjects() {
    const resp = await _fetch(`${API_BASE}/memory/projects`);
    return await resp.json();
  },

  // ========== 对话历史 ==========
  async getConversations(projectId = "agent_maona", limit = 20, offset = 0) {
    const resp = await _fetch(`${API_BASE}/chat/conversations?project_id=${projectId}&limit=${limit}&offset=${offset}`);
    return await resp.json();
  },

  async createConversation(projectId = "agent_maona") {
    const resp = await _fetch(`${API_BASE}/chat/conversations?project_id=${projectId}`, {
      method: "POST",
    });
    return await resp.json();
  },

  async getConversation(id) {
    const resp = await _fetch(`${API_BASE}/chat/conversations/${id}`);
    return await resp.json();
  },

  async deleteConversation(id) {
    return await _fetch(`${API_BASE}/chat/conversations/${id}`, { method: "DELETE" });
  },

  async renameConversation(id, title) {
    await _fetch(`${API_BASE}/chat/conversations/${id}?title=${encodeURIComponent(title)}`, { method: "PATCH" });
  },

  async searchConversations(query, projectId = "agent_maona") {
    const resp = await _fetch(`${API_BASE}/chat/conversations/search?q=${encodeURIComponent(query)}&project_id=${projectId}`);
    return await resp.json();
  },

  // ========== 工作空间 ==========
  async getWorkspaces() {
    const resp = await _fetch(`${API_BASE}/memory/workspaces`);
    return await resp.json();
  },

  async saveWorkspaces(workspaces) {
    const resp = await _fetch(`${API_BASE}/memory/workspaces`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspaces }),
    });
    return await resp.json();
  },

  async getDefaultWorkspace() {
    const resp = await _fetch(`${API_BASE}/memory/default-workspace`);
    return await resp.json();
  },

  async saveDefaultWorkspace(path) {
    const resp = await _fetch(`${API_BASE}/memory/default-workspace?path=${encodeURIComponent(path)}`, {
      method: "PUT",
    });
    return await resp.json();
  },

  // ========== 偏好 ==========
  async getPref(key) {
    const resp = await _fetch(`${API_BASE}/memory/prefs`);
    const prefs = await resp.json();
    return prefs[key] || null;
  },

  async setPref(key, value) {
    // 同步到 localStorage，避免页面加载闪烁
    try { localStorage.setItem("maona_" + key, String(value)); } catch(e) {}
    const resp = await _fetch(`${API_BASE}/memory/prefs?key=${encodeURIComponent(key)}&value=${encodeURIComponent(value)}`, {
      method: "PUT",
    });
    return await resp.json();
  },

  // ========== 后台任务 ==========
  async startBgTask(prompt, provider, model, project, workspace) {
    let url = `${API_BASE}/tasks?prompt=${encodeURIComponent(prompt)}&project=${project}`;
    if (provider) url += `&provider=${provider}`;
    if (model) url += `&model=${encodeURIComponent(model)}`;
    if (workspace) url += `&workspace=${encodeURIComponent(workspace)}`;
    const resp = await _fetch(url, { method: "POST" });
    return await resp.json();
  },

  async getTask(id) {
    const resp = await _fetch(`${API_BASE}/tasks/${id}`);
    return await resp.json();
  },
};

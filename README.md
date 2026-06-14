# Maona

> 自用 AI 桌面办公助手 — Electron + Python FastAPI，本地 Agent 闭环

<p align="center">
  <img src="renderer/assets/icon.png" width="80" alt="Maona">
</p>

## 简介

Maona 是一个运行在本地的 AI 桌面助手，集文件读写、命令执行、联网搜索、知识库、多模型切换于一身。支持任意 OpenAI 兼容 API（DeepSeek、GLM、硅基流动、OpenAI 等），带多层记忆系统和自动化 Agent 循环。

**核心理念：闭嘴干活。** AI 能自己动手就不问用户，读文件、写代码、跑命令一气呵成，失败自动重试，完成后自动验证。

## 功能概览

### 对话与交互
- **流式输出** — 逐字实时渲染，支持停止 / 重新生成
- **深度思考** — Reasoning 内容可折叠查看（DeepSeek-R1 等推理模型）
- **工作模式** — Craft（自由执行）/ Plan（先计划后执行）/ Ask（只读回答）三模式
- **代码高亮** — highlight.js + Monokai 主题
- **Markdown 渲染** — 表格、列表、代码块完整支持
- **图片支持** — 粘贴 / 拖入图片，OCR 文字识别
- **快捷操作** — Enter 发送 / Shift+Enter 换行 / Esc 停止 / Ctrl+↑ 引用上文

### Agent 能力（85+ 工具）
| 类别 | 工具 |
|------|------|
| 文件系统 | 读写、编辑、列表、搜索、重命名、删除 |
| 命令行 | Shell 命令、Python 脚本、pip 安装 |
| 网络 | 联网搜索、网页抓取、API 调用、文件下载 |
| 办公文档 | CSV/Excel/Word/PPT/PDF 读写 |
| 代码智能 | LSP 诊断、引用查找、符号大纲、代码格式化 |
| 浏览器 | Playwright 自动化 — 导航、截图、点击、填表、数据提取 |
| Git | 版本 diff、日志、快照 |
| 多媒体 | 截图、图片压缩、HTML 预览、文字转语音 |
| 内存/RAG | 知识库 CRUD、向量语义搜索、TF-IDF 全文检索 |
| 自动化 | 后台任务、定时调度、ComfyUI 节点开发 |
| 技能系统 | 技能安装/切换/市场，按需加载专业能力 |

### 工作空间
- 选择本地文件夹作为工作空间，AI 自动创建 `.maona/` 记忆目录
- 每日工作日志自动维护（`YYYY-MM-DD.md`）
- 长期记忆（`MEMORY.md`）+ 自定义规则（`rules.md`）
- 对话历史 SQLite 持久化 + FTS5 全文搜索
- 长任务检查点恢复，中断后断点续跑

### 记忆系统（自研多层架构）
```
用户画像 ─── 自动学习工具偏好、关键词、工作主题
知识图谱 ─── 从记忆文件提取实体关系，支持语义搜索
工作流记忆 ─ 记录成功工具序列，相似任务推荐历史方案
对话记忆 ─── SQLite + FTS5，全文搜索历史对话
验证闭环 ─── 代码生成后自动语法检查 + 修复重试
```

### Provider 管理
- 动态添加/删除/切换 OpenAI 兼容 API
- API Key XOR + Base64 加密存储
- 一键拉取模型列表（5 分钟缓存）
- 故障自动降级链（主 → 备用 → 备用2）
- 余额查询

### 技能系统
- 内置技能市场，一键安装专业能力模块
- 支持 Godot 游戏开发、办公文档处理、浏览器自动化等
- 技能按需加载，不消耗不必要 token

### 桌面集成
- 全局快捷键 Alt+Space 呼出/隐藏
- 系统托盘最小化
- 退出自动关闭后端进程

## 快速开始

### 环境要求

- **Node.js** ≥ 18
- **Python** ≥ 3.10
- **Windows**（macOS 理论兼容，未测试）

### 安装与启动

```bash
# 1. 安装 Node 依赖
cd F:\工具\Agent_maona
npm install

# 2. 安装 Python 依赖
cd backend
pip install -r requirements.txt

# 3. 回到根目录启动
cd ..
npm start
```

首次启动会自动预置 DeepSeek 和 GLM 两个 Provider 模板，在设置页填入 API Key 即可使用。

### Windows 快捷启动

双击 `启动Maona.vbs` 或 `启动Maona.bat`。

## 基本使用

### 对话

打开后直接输入文字，Enter 发送。

| 操作 | 快捷键 |
|------|--------|
| 发送 | Enter |
| 换行 | Shift+Enter |
| 停止生成 | Esc 或点击 ■ |
| 引用上次回复 | Ctrl+↑ |
| 输入历史 | 空输入框时 ↑ ↓ |
| 粘贴图片 | Ctrl+V |
| 搜索对话 | Ctrl+Shift+F |

### 工作空间

1. 点击底部「📁 默认工作空间」选择文件夹
2. AI 会在工作空间中创建 `.maona/` 目录存储记忆
3. 通过 `@文件名` 引用工作空间中的文件

**工作空间目录结构：**
```
你的项目/
├── .maona/
│   ├── MEMORY.md      # 长期记忆
│   ├── 2026-06-14.md  # 每日工作日志
│   └── rules.md       # 自定义规则（可选）
└── ... 你的项目文件 ...
```

### 自定义规则

在 `.maona/rules.md` 中写入指令，AI 每次对话自动遵循：

```markdown
## 项目规则
- 所有 Python 代码使用 4 空格缩进
- 文件名使用 snake_case
- 不要修改 backend/config.py
```

### 模型切换

顶部下拉框选择 Provider 和模型，选择自动保存。

## 设置

### 添加 API Provider

1. 点击左侧 ⚙️ 设置 → API 管理
2. 填写名称、API URL、API Key
3. 点击「获取模型」拉取可用模型列表
4. 支持任何 OpenAI 兼容 API：

| Provider | API URL |
|----------|---------|
| DeepSeek | `https://api.deepseek.com/v1` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| 硅基流动 | `https://api.siliconflow.cn/v1` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |

### 模型参数

在设置页可调整全局参数：Temperature、Max Tokens、Top-P、推理模式、Embedding 配置。

### 人设切换

内置 7 种人设：默认 / 代码专家 / 产品经理 / 翻译助手 / 代码审查 / 详细解释 / 言简意赅。在设置页切换。

## 架构

```
┌──────────────────────────────────────────────────┐
│                  Electron 桌面壳                    │
│          main.js  →  preload.js  →  renderer/     │
├──────────────────────────────────────────────────┤
│  前端（原生 HTML/CSS/JS，暗色主题）                   │
│  chat.js │ sidebar.js │ app.js │ settings.js      │
├──────────────────────────────────────────────────┤
│            HTTP/SSE → localhost:8765               │
├──────────────────────────────────────────────────┤
│              Python FastAPI 后端                    │
│                                                    │
│  API 层    ├─ /api/chat/*    对话 & Agent 循环     │
│            ├─ /api/memory/*  记忆 CRUD            │
│            ├─ /api/settings/* Provider 管理        │
│            ├─ /api/tasks/*   后台任务              │
│            ├─ /api/files/*   文件浏览 & OCR        │
│            ├─ /api/personas/* 人设管理             │
│            └─ /api/knowledge/* 知识库全套          │
│                                                    │
│  核心层    ├─ tools/        85+ 工具定义 & 调度     │
│            ├─ providers/    AI Provider & 降级链   │
│            ├─ memory/       多层记忆系统           │
│            ├─ skills.py     技能系统              │
│            ├─ personas/     人设模板              │
│            └─ tasks/        后台任务执行器         │
├──────────────────────────────────────────────────┤
│                 外部 AI API                        │
│     DeepSeek / GLM / OpenAI / 硅基流动 ...         │
└──────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 桌面壳 | Electron 30 |
| 前端 | 原生 HTML/CSS/JS（零框架） |
| 后端 | Python 3.13 + FastAPI |
| 流式 | SSE (Server-Sent Events) |
| 对话存储 | SQLite + FTS5 全文搜索 |
| 向量搜索 | 本地 TF-IDF / 语义向量 |
| 加密 | XOR + Base64（API Key） |
| 浏览器 | Playwright |
| 代码智能 | LSP (Language Server Protocol) |
| OCR | Tesseract 5（中英文） |

## 项目结构

```
Agent_maona/
├── main.js                    # Electron 主进程
├── preload.js                 # 预加载安全桥接
├── package.json
├── renderer/                  # 前端 UI
│   ├── index.html
│   ├── css/style.css
│   ├── assets/icon.png
│   └── js/
│       ├── api.js             # API 封装
│       ├── app.js             # 应用入口
│       ├── chat.js            # 对话面板 & 流式渲染
│       ├── sidebar.js         # 侧栏 & 工作空间
│       ├── settings.js        # 设置页 & Provider 管理
│       ├── skills.js          # 技能管理 UI
│       ├── memory.js          # 记忆查看 UI
│       ├── metrics.js         # 指标仪表板
│       └── trace.js           # Agent 执行追踪
├── backend/                   # Python 后端
│   ├── main.py                # FastAPI 入口 & 路由注册
│   ├── config.py              # 全局配置
│   ├── skills.py              # 技能系统
│   ├── api/                   # API 路由
│   │   ├── chat.py            # 对话 / Agent 循环 / SSE
│   │   ├── files.py           # 文件浏览 & OCR
│   │   ├── memory.py          # 记忆管理
│   │   ├── settings.py        # Provider 管理
│   │   ├── tasks.py           # 后台任务
│   │   └── personas_api.py    # 人设 API
│   ├── memory/                # 记忆引擎
│   │   ├── conversations.py   # SQLite 对话持久化 & FTS5
│   │   ├── store.py           # Markdown 文件存储
│   │   ├── context.py         # 上下文构建器
│   │   ├── profile.py         # 用户画像
│   │   ├── planner.py         # 任务拆解 & 回溯
│   │   ├── graph.py           # 知识图谱
│   │   ├── procedural.py      # 工作流记忆
│   │   ├── checkpoint.py      # 检查点恢复
│   │   └── verify.py          # 验证闭环
│   ├── providers/             # AI Provider
│   │   ├── openai_provider.py # OpenAI 兼容客户端
│   │   ├── manager.py         # Provider 缓存管理
│   │   ├── store.py           # 加密持久化
│   │   ├── wrapper.py         # 故障降级包装
│   │   ├── fallback.py        # 降级链构建
│   │   └── model_settings.py  # 全局模型参数
│   ├── tools/                 # 工具系统（85+ 工具）
│   │   ├── definitions.py     # 工具 Schema 定义
│   │   ├── dispatcher.py      # 工具路由 & 执行
│   │   ├── file_ops.py        # 文件操作
│   │   ├── shell.py           # Shell / Python 执行
│   │   ├── browser.py         # Playwright 浏览器
│   │   ├── lsp.py             # LSP 代码智能
│   │   ├── deploy.py          # 站点部署
│   │   ├── creative.py        # 生图 / 定时任务
│   │   ├── comfy_cli.py       # ComfyUI 节点
│   │   ├── knowledge.py       # 本地知识库
│   │   ├── rag.py             # 向量语义搜索
│   │   ├── ocr.py             # 图片 OCR
│   │   ├── gdscript_lint.py   # GDScript 验证
│   │   ├── godot_ops.py       # Godot 项目工具
│   │   ├── mcp_client.py      # MCP 桥接（Node.js）
│   │   └── memory_tools.py    # 记忆工具
│   ├── llm/                   # LLM 抽象层
│   ├── personas/              # 人设模板
│   ├── tasks/runner.py        # 后台 Agent 任务
│   └── models/schemas.py      # 数据模型
├── data/                      # 本地数据
│   ├── skills/                # 已安装技能
│   └── godot-mcp/             # Godot MCP 服务
├── tesseract/                 # Tesseract OCR 引擎
├── scripts/                   # 辅助脚本
│   ├── start.bat              # 启动批处理
│   └── 集成Tesseract.bat      # OCR 集成脚本
├── tests/                     # 测试文件
├── docs/                      # 文档 & 诊断报告
└── screenshots/               # 截图
```

### 持久化存储

| 存储项 | 路径 | 格式 |
|--------|------|------|
| Provider 配置 | `~/.agent_maona/providers.json` | JSON（Key 加密） |
| 对话历史 | `~/.agent_maona/conversations.db` | SQLite + FTS5 |
| 全局记忆 | `~/.agent_maona/memory/global/` | Markdown + JSON |
| 知识图谱 | `~/.agent_maona/knowledge_graph.json` | JSON |
| 工作流记忆 | `~/.agent_maona/procedural_memory.json` | JSON |
| 用户画像 | `~/.agent_maona/memory/global/user_profile.json` | JSON |
| 模型参数 | `~/.agent_maona/model_settings.json` | JSON |
| 人设列表 | `~/.agent_maona/personas.json` | JSON |
| 检查点 | `~/.agent_maona/checkpoints/` | JSON |
| 工作空间记忆 | `{workspace}/.maona/` | Markdown |

## 配置

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENT_MAONA_PORT` | 8765 | 后端端口 |
| `AGENT_MAX_ROUNDS` | 150 | Agent 最大循环轮次 |
| `AGENT_PARALLEL_WRITES` | true | 是否并行写入不同文件 |

## FAQ

**Q: 启动后显示「请求超时」**
A: 检查 API Key 是否正确，API URL 是否以 `/v1` 结尾，账户余额是否充足。

**Q: 如何添加新的 AI Provider**
A: 设置页 → API 管理 → 填名称/URL/Key → 获取模型 → 保存。

**Q: 如何切换工作模式**
A: 对话页顶部选择 Craft（自由执行）/ Plan（先计划）/ Ask（只读）。

**Q: 对话历史存在哪里**
A: SQLite 数据库 `~/.agent_maona/conversations.db`，支持全文搜索。

**Q: 可以离线使用吗**
A: 核心工具（文件读写、命令执行、OCR）可离线使用。AI 对话和搜索需联网。

**Q: API Key 安全吗**
A: Key 用 XOR + Base64 加密存储在本地 `~/.agent_maona/providers.json`，Master Key 首次生成后持久化。

## 版本历史

| 版本 | 日期 | 主要内容 |
|------|------|----------|
| v0.8 | 2026-06 | 知识库系统完善、技能市场、验证闭环、MCP 自动重连 |
| v0.7 | 2026-06 | 全面诊断修复 — FTS5 全文搜索、API Key 持久化加密、Agent 循环优化、CSS 修复 |
| v0.6 | 2026-05 | Agent 150 轮循环、上下文压缩、任务跟踪、断点恢复 |
| v0.5 | 2026-05 | 多 Provider 支持、工作空间记忆、对话搜索、系统托盘 |
| v0.1 | 2026-05 | 初版 — 基础对话、文件操作、SSE 流式输出 |

## License

MIT

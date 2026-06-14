# Maona

> 自用 AI 桌面办公助手 

## 简介

Maona 是一个运行在本地的 AI 桌面助手，集文件读写、命令执行、联网搜索、知识库、多模型切换于一身。


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

### 工作空间

1. 点击底部「📁 默认工作空间」选择文件夹
2. AI 会在工作空间中创建 `.maona/` 目录存储记忆
3. 通过 `@文件名` 引用工作空间中的文件


### 模型切换

顶部下拉框选择 Provider 和模型，选择自动保存。

## 设置

### 添加 API Provider

1. 点击左侧 ⚙️ 设置 → API 管理
2. 填写名称、API URL、API Key
3. 点击「获取模型」拉取可用模型列表
4. 目前只测试过deepseek

### 存储

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


## License

MIT

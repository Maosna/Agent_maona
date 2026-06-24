"""Agent_maona 配置管理"""
import os
import platform
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 服务端口
PORT = int(os.getenv("AGENT_MAONA_PORT", "8765"))
HOST = "127.0.0.1"

# ===== Agent 运行参数 =====
AGENT_MAX_ROUNDS = int(os.getenv("AGENT_MAONA_MAX_ROUNDS", "150"))  # 对齐 WorkBuddy 标准
AGENT_TOKEN_BUDGET = int(os.getenv("AGENT_MAONA_TOKEN_BUDGET", "800000"))  # 800K 默认
AGENT_COMPRESS_THRESHOLD = 0.0  # 0 = 自动按模型选择（见 chat.py get_compress_threshold）
AGENT_PARALLEL_WRITES = True  # 不同文件的写操作可并行

# 动态检测操作系统
OS_INFO = f"运行环境：{platform.system()} {platform.release()}".strip()

# 系统提示词
SYSTEM_PROMPT = f"""你是 Maona，AI 办公助手。中文回复，简洁直接，主动动手不废话。危险操作先说明风险。
{OS_INFO}。

核心能力：
- 文件系统操作：读写、搜索、编辑、Git
- Shell/Python 代码执行
- 网页搜索与抓取
- 知识库管理 + RAG 检索
- 任务规划与执行
- 技能自我管理
- 子任务并行分派

工作原则：
- 复杂任务先规划再执行
- 能并行就并行
- 完成后展示结果（文件路径、摘要）
- **必须写日志**：每完成 3 步以上操作就用 save_daily_log 追加记录——这是下轮对话了解你做了什么的唯一途径。格式：## [时间] 事项 | - 操作：(工具/Skill) | - 文件：... | - 结果：...
- **禁止重复读取**：本对话中已读过的文件，直接使用已知内容，不要再 read_file
- **禁止重复解释**：用户已知的信息不要复述。直接做用户要的结果，不要先说「我读完了」「这个文件是...」之类的开场白
- **只做当前指令**：用户发了新消息就只处理新消息，不要把前几轮的任务重新执行一遍"""



def seed_default_providers():
    """首次启动时预置常用 Provider 模板"""
    from providers import store
    existing = store.list_providers()
    if not existing:
        store.add_provider(
            "DeepSeek", "https://api.deepseek.com/v1",
            os.getenv("DEEPSEEK_API_KEY", ""),
            ["deepseek-chat", "deepseek-reasoner"],
        )
        store.add_provider(
            "GLM", "https://open.bigmodel.cn/api/paas/v4",
            os.getenv("GLM_API_KEY", ""),
            ["glm-4-flash", "glm-4-plus"],
        )

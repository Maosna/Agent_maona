"""智能模型路由 — 根据消息内容自动选择最佳模型

思路：类似 OpenRouter/LiteLLM 的做法，用关键词+模式匹配判定任务类型，
查模型能力表做匹配，优先在同一个 Provider 内选，不行就跨 Provider 搜索。
零延迟（纯本地计算），不消耗额外 token。
"""

import re
from typing import Optional

# === 模型能力表（按模型名模式匹配） ===
# key = 关键词匹配模型名, value = {能力标签: 权重}
# 权重越高越适合该任务类型
_MODEL_CAPABILITIES = [
    # DeepSeek 系列
    (r"deepseek.*v4.*pro|deepseek.*reasoner|deepseek.*r1", {"reasoning": 10, "coding": 8, "fast": 3, "longctx": 10}),
    (r"deepseek.*v4.*flash", {"fast": 9, "coding": 6, "reasoning": 5, "longctx": 8}),
    (r"deepseek.*chat|deepseek.*v3", {"fast": 7, "coding": 7, "reasoning": 5, "longctx": 6}),
    # OpenAI 系列
    (r"o[134].*mini", {"reasoning": 8, "coding": 7, "fast": 7, "longctx": 6}),
    (r"o[134]\b", {"reasoning": 10, "coding": 8, "fast": 4, "longctx": 6}),
    (r"gpt.*4\.1|gpt.*4o", {"fast": 6, "coding": 7, "reasoning": 6, "longctx": 8}),
    (r"gpt.*4.*turbo|gpt.*4\b", {"fast": 5, "coding": 6, "reasoning": 5, "longctx": 4}),
    (r"gpt.*3", {"fast": 8, "coding": 4, "reasoning": 3, "longctx": 3}),
    # Anthropic
    (r"claude.*3\.[57].*sonnet", {"reasoning": 9, "coding": 9, "fast": 5, "longctx": 7}),
    (r"claude.*3.*haiku|claude.*3\.5.*haiku", {"fast": 9, "coding": 6, "reasoning": 4, "longctx": 5}),
    (r"claude.*3.*opus", {"reasoning": 9, "coding": 8, "fast": 3, "longctx": 7}),
    (r"claude", {"reasoning": 7, "coding": 7, "fast": 5, "longctx": 6}),
    # Gemini
    (r"gemini.*2\.5.*pro", {"reasoning": 10, "coding": 8, "fast": 4, "longctx": 10, "vision": 9}),
    (r"gemini.*2\.[05].*flash", {"fast": 9, "coding": 6, "reasoning": 5, "longctx": 8, "vision": 7}),
    (r"gemini.*1\.5.*pro", {"reasoning": 9, "coding": 8, "fast": 4, "longctx": 10, "vision": 8}),
    (r"gemini", {"fast": 6, "coding": 6, "reasoning": 6, "longctx": 8, "vision": 6}),
    # Qwen
    (r"qwen.*max|qwen3.*max", {"reasoning": 7, "coding": 6, "fast": 5, "longctx": 6}),
    (r"qwen.*turbo", {"fast": 9, "coding": 5, "reasoning": 4, "longctx": 8}),
    (r"qwq", {"reasoning": 9, "coding": 6, "fast": 4, "longctx": 5}),
    (r"qwen.*vl|qvq", {"reasoning": 6, "coding": 5, "fast": 5, "longctx": 5, "vision": 9}),
    (r"qwen", {"fast": 6, "coding": 5, "reasoning": 5, "longctx": 5}),
    # GLM
    (r"glm.*4v", {"reasoning": 5, "coding": 4, "fast": 5, "longctx": 5, "vision": 8}),
    (r"glm.*4", {"reasoning": 6, "coding": 5, "fast": 6, "longctx": 5}),
    (r"glm", {"fast": 6, "coding": 4, "reasoning": 4, "longctx": 4}),
    # 通用兜底
    (r".*", {"fast": 5, "coding": 5, "reasoning": 5, "longctx": 5}),
]

# === 任务类型检测（关键词+模式，零延迟） ===

def detect_task_type(message: str) -> str:
    """分析用户消息，返回最可能的任务类型"""
    msg = (message or "").lower()

    # 检查消息中是否包含附件（图片/文件路径）
    has_attachment = "【图片:" in message or "[图片:" in message or "【文件:" in message

    # 1. 视觉类：图片附件或明确提图
    vision_patterns = [
        "图片", "图像", "照片", "截图", "看图", "视觉", "识别图片",
        "ocr", "文字识别", "image", "photo", "screenshot",
    ]
    vision_matches = sum(1 for p in vision_patterns if p in msg)
    if has_attachment or vision_matches >= 1:
        return "vision"

    # 2. 代码类
    code_patterns = [
        "```", "import ", "def ", "function ", "class ", "const ", "let ", "var ",
        "console.", "npm ", "pip ", "docker ", "api", "rest ", "json",
        "写", "代码", "脚本", "函数", "bug", "报错", "错误", "调试",
        "前端", "vue", "react", "next", "python", "javascript", "typescript", "html", "css",
        "实现", "重构", "程序", "算法", "框架",
    ]
    code_count = sum(1 for p in code_patterns if p in msg)
    # 先检查代码特征（防止"写"这类短字误匹配到常规聊天）
    code_strong = any(p in msg for p in ["```", "import ", "def ", "function ", "class ", "console.", "npm ", "pip ", "docker ",
                                         "bug", "错", "前端", "vue", "react", "next", "python", "javascript",
                                         "重构", "算法", "框架", "css", "html", "typescript", "java "])

    # 推理优先标记：即使有代码关键词，也应该被推理覆盖
    reasoning_override = any(p in msg for p in ["为什么", "分析一下", "解释一下", "原理", "设计模式", "架构设计"])

    if not reasoning_override:
        if code_count >= 3 or (code_strong and code_count >= 1) or any(p in msg for p in ["```", "def ", "function ", "class "]):
            return "coding"

    # 3. 推理类
    reasoning_patterns = [
        "分析", "解释", "为什么", "原因", "原理", "比较", "区别",
        "总结", "概括", "方案", "设计", "架构",
        "深入", "仔细", "详细", "逻辑", "推理",
    ]
    reasoning_count = sum(1 for p in reasoning_patterns if p in msg)
    if reasoning_count >= 2:
        return "reasoning"

    # 4. 长消息默认推理（> 200 字），除非明确是代码
    if len(message or "") > 200:
        if code_count >= 2:
            return "coding"
        return "reasoning"

    # 5. 单个推理关键词 + 中等长度 → 推理
    single_reasoning = sum(1 for p in ["分析", "为什么", "原因", "原理", "方案", "设计", "架构", "比较", "解释", "总结", "区别"] if p in msg)
    if single_reasoning >= 1:
        return "reasoning"

    # 6. 短消息、问候、简单查询 → 快捷
    return "fast"


# === 路由引擎 ===

def score_model(model_id: str, task_type: str) -> int:
    """给模型打分（0-10），越高越适合该任务"""
    mid = model_id.lower()
    for pattern, caps in _MODEL_CAPABILITIES:
        if re.search(pattern, mid):
            return caps.get(task_type, 5)
    return 5  # 未知模型默认 5 分


def route_auto(enabled_models: list[dict]) -> Optional[tuple[str, str, str]]:
    """自动路由：根据上一条用户消息选择最佳 (provider_name, model_id, reason)
    
    Args:
        enabled_models: [{provider: "...", model: "..."}, ...]
    
    Returns:
        (provider, model, reason) 或 None
    """
    if not enabled_models:
        return None

    # 获取请求中的用户消息（由调用方传入）
    # 这里返回一个默认值，实际路由在 stream_chat 中完成
    return None


def find_best_model(enabled_models: list[dict], message: str) -> Optional[tuple]:
    """查找最匹配的模型
    
    Args:
        enabled_models: [{provider: "...", model: "...", api_key: "..."}, ...]
        message: 用户消息文本
    
    Returns:
        (provider_name, model_id, reason) 或 None
    """
    if not enabled_models:
        return None

    task = detect_task_type(message)
    candidates = []
    for em in enabled_models:
        mid = em.get("model", "")
        score = score_model(mid, task)
        # 同 Provider 内有更多启用模型？加分
        same_provider = [m for m in enabled_models if m.get("provider") == em["provider"]]
        if len(same_provider) > 1:
            score += 1
        candidates.append((score, em["provider"], mid, task))

    # 取最高分
    candidates.sort(reverse=True, key=lambda x: x[0])
    best_score, provider, model_id, task = candidates[0]

    task_names = {"fast": "快捷", "coding": "代码", "reasoning": "推理", "vision": "视觉"}
    reason = f"任务: {task_names.get(task, task)} (评分 {best_score}/10)"
    return (provider, model_id, reason)

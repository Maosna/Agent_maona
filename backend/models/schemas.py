"""Pydantic 数据模型"""
from pydantic import BaseModel, Field
from typing import Optional, Union


class Message(BaseModel):
    role: str
    content: Union[str, list[dict]]  # 文本或 vision 格式的数组
    name: Optional[str] = None
    tool_calls: Optional[list[dict]] = None  # 历史消息的工具调用记录
    tool_call_id: Optional[str] = None  # tool 消息的调用 ID
    reasoning: Optional[str] = None  # 推理内容
    reasoning_content: Optional[str] = None  # 推理内容（备选字段名）


class ChatRequest(BaseModel):
    messages: list[Message]
    provider: Optional[str] = None  # provider name, None = first available
    model: Optional[str] = None     # specific model, None = provider default
    tools: Optional[list[dict]] = None
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None
    workspace: Optional[str] = None  # 工作空间路径
    persona_id: Optional[str] = None  # 人设 ID
    mode: Optional[str] = None        # "craft" | "plan" | "ask", 默认 "craft"


class ProviderConfig(BaseModel):
    name: str
    api_url: str
    api_key: str
    models: list[str] = []

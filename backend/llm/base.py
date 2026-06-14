"""LLM Provider 抽象基类"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class LLMProvider(ABC):
    """统一的 LLM Provider 接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """
        流式对话
        messages: [{"role": "...", "content": "..."}]
        tools: OpenAI 格式的工具定义列表
        yield: 每个 token / delta
        """
        ...

    async def chat_non_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """
        非流式对话（用于 Tool Use 循环）
        返回: {"content": "...", "tool_calls": [...]}
        """
        ...

    @abstractmethod
    def supports_tools(self) -> bool:
        """是否支持 function calling"""
        ...

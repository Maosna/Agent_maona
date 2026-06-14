"""Provider 降级包装器 - 自动故障转移"""
from typing import AsyncIterator
from .fallback import get_fallback_chain


class FallbackProviderWrapper:
    """包装降级链，chat_stream/chat_non_stream 失败时自动切换"""
    
    def __init__(self, primary_name: str, model: str = None):
        self.chain = get_fallback_chain(primary_name, model)
        self._current_idx = 0
        self._name = None  # 延迟获取
    
    @property
    def name(self):
        return self.chain[self._current_idx][0]
    
    def _current(self):
        return self.chain[self._current_idx][1]
    
    async def _try_next(self) -> bool:
        """切换到下一个 provider，成功返回 True"""
        self._current_idx += 1
        if self._current_idx >= len(self.chain):
            return False
        return True
    
    async def chat_stream(self, messages, tools=None, **kw) -> AsyncIterator[dict]:
        """流式对话，带降级"""
        last_err = None
        while self._current_idx < len(self.chain):
            try:
                async for chunk in self._current().chat_stream(messages, tools, **kw):
                    yield chunk
                return  # 成功
            except Exception as e:
                last_err = e
                if not await self._try_next():
                    break
                yield {"type": "token", "content": f"\n[已切换到备��� Provider: {self.name}]"}
        yield {"type": "done", "content": f"\n所有 Provider 均失败: {last_err}", "error": True}
    
    async def chat_non_stream(self, messages, tools=None, **kw) -> dict:
        """非流式对话，带降级"""
        last_err = None
        while self._current_idx < len(self.chain):
            try:
                return await self._current().chat_non_stream(messages, tools, **kw)
            except Exception as e:
                last_err = e
                if not await self._try_next():
                    break
        return {"error": f"所有 Provider 均失败: {last_err}"}
    
    def reset(self):
        self._current_idx = 0

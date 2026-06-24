"""通用 OpenAI 兼容 Provider

适用于 DeepSeek、GLM、硅基流动、OpenRouter 等所有 OpenAI 兼容 API
"""
import json
import asyncio
import httpx
from typing import AsyncIterator, Optional


class OpenAIProvider:
    """通用 OpenAI 兼容 Provider"""

    def __init__(self, name: str, api_url: str, api_key: str, model: str):
        self.name = name
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=600.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=30),
        )
        self._closed = False

    async def aclose(self):
        """关闭底层 httpx 客户端，释放连接"""
        if not self._closed:
            self._closed = True
            try:
                await self._client.aclose()
            except Exception:
                pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def _post_with_retry(self, url, payload, headers, max_retries=2):
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                resp = await self._client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                # 429 限流 + 5xx 服务器错误 → 退避重试
                if (e.response.status_code == 429 or e.response.status_code >= 500) and attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                raise last_err

    async def fetch_models(self) -> list[str]:
        """从 API 获取可用模型列表"""
        try:
            resp = await self._client.get(
                f"{self._api_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            models = []
            for m in data.get("data", []):
                mid = m.get("id", "")
                if mid and not any(skip in mid.lower() for skip in ["embed", "moderation", "whisper", "tts", "dall"]):
                    models.append(mid)
            return sorted(models)
        except Exception:
            # 无法获取列表时返回空，用户可手动填写
            return []

    async def check_balance(self) -> dict:
        """查询余额（目前支持 DeepSeek）"""
        # DeepSeek 有专门的余额接口
        if "deepseek" in self._api_url.lower():
            try:
                resp = await self._client.get(
                    f"{self._api_url}/user/balance",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                info = data.get("balance_infos", [{}])[0] if data.get("balance_infos") else {}
                return {
                    "balance": info.get("total_balance", "0"),
                    "granted": info.get("granted_balance", "0"),
                    "topped_up": info.get("topped_up_balance", "0"),
                    "currency": info.get("currency", "CNY"),
                }
            except Exception:
                pass
        return {}

    async def chat_non_stream(
        self, messages: list[dict], tools: Optional[list[dict]] = None,
        temperature: float = None, max_tokens: int = None, top_p: float = None,
        thinking_enabled: bool = False, reasoning_effort: str = "high"
    ) -> dict:
        if not self._api_key:
            return {"error": f"{self.name} API Key 未配置"}

        url = f"{self._api_url}/chat/completions"
        payload = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        # 思考模式：DeepSeek thinking mode
        if thinking_enabled:
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = reasoning_effort
            # 思考模式下 temperature/top_p 不生效，但保留 max_tokens
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
        else:
            if temperature is not None:
                payload["temperature"] = temperature
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if top_p is not None:
                payload["top_p"] = top_p

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        resp = await self._post_with_retry(url, payload, headers)
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage", {})
        return {
            "content": msg.get("content"),
            "tool_calls": msg.get("tool_calls"),
            "reasoning": msg.get("reasoning_content"),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        }

    async def chat_stream(
        self, messages: list[dict], tools: Optional[list[dict]] = None, max_retries: int = 2,
        temperature: float = None, max_tokens: int = None, top_p: float = None,
        thinking_enabled: bool = False, reasoning_effort: str = None
    ) -> AsyncIterator[dict]:
        """流式对话，yield {"type":"token"|"reasoning"|"done", "content":"...", ...}"""
        if not self._api_key:
            yield {"type": "done", "content": f"{self.name} API Key 未配置", "error": True}
            return

        url = f"{self._api_url}/chat/completions"
        payload = {"model": self.model, "messages": messages, "stream": True}
        if temperature is not None: payload["temperature"] = temperature
        if max_tokens: payload["max_tokens"] = max_tokens
        if top_p is not None: payload["top_p"] = top_p
        if tools:
            payload["tools"] = tools
        if thinking_enabled and self.name.lower().find("deepseek") >= 0:
            payload["thinking"] = {"type": "enabled"}
            if reasoning_effort:
                payload["thinking"]["effort"] = reasoning_effort

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        accumulated_content = ""
        accumulated_reasoning = ""
        tool_call_map: dict[int, dict] = {}
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if delta.get("reasoning_content"):
                                accumulated_reasoning += delta["reasoning_content"]
                                yield {"type": "reasoning", "content": delta["reasoning_content"]}
                            elif delta.get("content"):
                                accumulated_content += delta["content"]
                                yield {"type": "token", "content": delta["content"]}
                            tc_deltas = delta.get("tool_calls", [])
                            for tc in tc_deltas:
                                idx = tc.get("index", 0)
                                if idx not in tool_call_map:
                                    tool_call_map[idx] = {"id": tc.get("id", ""), "function": {"name": "", "arguments": ""}}
                                if tc.get("id"):
                                    tool_call_map[idx]["id"] = tc["id"]
                                fn = tc.get("function", {})
                                if fn.get("name"):
                                    tool_call_map[idx]["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    tool_call_map[idx]["function"]["arguments"] += fn["arguments"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                # 成功，跳出重试
                break
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < max_retries and getattr(e, 'response', None) and getattr(e.response, 'status_code', 0) >= 500:
                    await asyncio.sleep(1.5 ** attempt)  # 指数退避
                    continue
                yield {"type": "done", "content": f"\n[API 错误: {e}]", "error": True}
                return

        # 流结束，发送 done 事件（含完整数据）
        tool_calls = [tool_call_map[i] for i in sorted(tool_call_map.keys())] if tool_call_map else None
        yield {
            "type": "done",
            "content": accumulated_content,
            "reasoning": accumulated_reasoning,
            "tool_calls": tool_calls,
        }

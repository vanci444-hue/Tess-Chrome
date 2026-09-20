"""百炼 OpenAI 兼容接口，保留标准工具消息，不隐式重试计费请求。"""

from typing import Any

import httpx
from src.adapters.base import ProviderError
from src.config.settings import Settings

from pycore.core import get_logger


class BailianLLMProvider:
    def __init__(self, config: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.config, self.transport = config, transport
        self.last_response_metadata: dict[str, Any] = {}

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | None = None,
    ) -> dict:
        cfg = self.config
        if not cfg.bailian_api_key or not cfg.bailian_base_url:
            raise ProviderError("LLM_NOT_CONFIGURED", "模型服务未配置")
        body: dict[str, Any] = {
            "model": cfg.llm_model,
            "messages": messages,
            "stream": False,
            "enable_thinking": cfg.llm_enable_thinking,
        }
        if tools:
            body.update(tools=tools, tool_choice="auto")
        if response_format:
            body["response_format"] = response_format
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                transport=self.transport,
                timeout=httpx.Timeout(cfg.model_timeout, connect=cfg.http_connect_timeout),
            ) as client:
                response = await client.post(
                    cfg.bailian_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.bailian_api_key}"},
                    json=body,
                )
            if response.status_code != 200:
                raise ProviderError("LLM_UPSTREAM_ERROR", "模型请求失败，请检查服务配置和额度")
            payload = response.json()
            message = payload["choices"][0]["message"]
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise ValueError("message")
            if message.get("content") is None and not message.get("tool_calls"):
                raise ValueError("empty")
            for call in message.get("tool_calls") or []:
                if not (
                    call.get("id")
                    and call.get("type") == "function"
                    and isinstance(call.get("function", {}).get("arguments"), str)
                ):
                    raise ValueError("tool_call")
            self.last_response_metadata = {
                "model": payload.get("model"),
                "id": payload.get("id"),
                "usage": payload.get("usage"),
            }
            get_logger().info("百炼接口成功，响应结构已核验")
            return {k: message[k] for k in ("role", "content", "tool_calls") if k in message}
        except httpx.TimeoutException:
            raise ProviderError("LLM_TIMEOUT", "模型请求超时，未自动重试") from None
        except httpx.HTTPError:
            raise ProviderError("LLM_CONNECTION_ERROR", "模型连接失败") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("LLM_INVALID_RESPONSE", "模型响应格式不符合约定") from None

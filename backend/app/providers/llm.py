import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class ProviderError(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LLMProvider(Protocol):
    model: str

    def stream(self, content: str) -> AsyncIterator["str | Usage"]: ...


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None


class MockProvider:
    model = "mock-stream-v1"

    async def stream(self, content: str) -> AsyncIterator[str | Usage]:
        for token in f"Mock assistant: I received your message: {content}".split(" "):
            yield f"{token} "
            await asyncio.sleep(0.01)
        yield Usage(len(content.split()), len(content.split()) + 8, "mock")


class OpenAICompatibleProvider:
    """Streams the widely supported chat-completions SSE format."""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        self.model = settings.llm_model
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url.rstrip("/")
        self.timeout = settings.llm_timeout_seconds
        self.max_tokens = settings.llm_max_output_tokens

    async def stream(self, content: str) -> AsyncIterator[str | Usage]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_completion_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "store": False,
        }
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                ) as response,
            ):
                if response.status_code == 429:
                    raise ProviderError("PROVIDER_RATE_LIMIT", True)
                if response.status_code >= 500:
                    raise ProviderError("PROVIDER_UNAVAILABLE", True)
                if response.status_code >= 400:
                    raise ProviderError("PROVIDER_REJECTED_REQUEST", False)
                finished = False
                async for line in response.aiter_lines():
                    if line == "data: [DONE]":
                        finished = True
                        break
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    if data.get("error"):
                        raise ProviderError("PROVIDER_INVALID_RESPONSE", False)
                    usage = data.get("usage")
                    if usage:
                        yield Usage(
                            usage.get("prompt_tokens"),
                            usage.get("completion_tokens"),
                            response.headers.get("x-request-id") or data.get("id"),
                        )
                    choices = data.get("choices") or []
                    delta = choices[0].get("delta", {}).get("content") if choices else None
                    if delta:
                        yield delta
                if not finished:
                    raise ProviderError("PROVIDER_INCOMPLETE_RESPONSE", False)
        except httpx.TimeoutException as exc:
            raise ProviderError("PROVIDER_TIMEOUT", True) from exc
        except httpx.TransportError as exc:
            raise ProviderError("PROVIDER_NETWORK_ERROR", True) from exc
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise ProviderError("PROVIDER_INVALID_RESPONSE", False) from exc


def get_provider(settings: Settings | None = None) -> LLMProvider:
    active = settings or get_settings()
    if active.llm_provider == "mock":
        return MockProvider()
    if active.llm_provider == "openai":
        return OpenAICompatibleProvider(active)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {active.llm_provider}")

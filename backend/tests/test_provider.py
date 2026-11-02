import json

import httpx
import pytest

from app.core.config import Settings
from app.providers.llm import OpenAICompatibleProvider, ProviderError, Usage


def provider(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs)
    )
    return OpenAICompatibleProvider(
        Settings(llm_api_key="test-only", llm_model="configured-model", _env_file=None)
    )


@pytest.mark.asyncio
async def test_stream_usage_empty_choices_and_output_limit(monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream_options"] == {"include_usage": True}
        assert payload["max_completion_tokens"] == 1000
        assert payload["store"] is False
        chunks = [
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
        ]
        return httpx.Response(
            200,
            headers={"x-request-id": "provider-123"},
            text="".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n",
        )

    events = [event async for event in provider(monkeypatch, handler).stream("Hi")]
    assert events == ["Hello", Usage(12, 3, "provider-123")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (429, "PROVIDER_RATE_LIMIT"),
        (503, "PROVIDER_UNAVAILABLE"),
        (401, "PROVIDER_REJECTED_REQUEST"),
    ],
)
async def test_safe_provider_errors(monkeypatch, status, code):
    adapter = provider(
        monkeypatch, lambda _: httpx.Response(status, text="private upstream details")
    )
    with pytest.raises(ProviderError, match=code) as error:
        _ = [event async for event in adapter.stream("private prompt")]
    assert "private" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,code",
    [
        ("data: broken\n", "PROVIDER_INVALID_RESPONSE"),
        ('data: {"choices": []}\n', "PROVIDER_INCOMPLETE_RESPONSE"),
    ],
)
async def test_malformed_and_truncated_stream(monkeypatch, body, code):
    adapter = provider(monkeypatch, lambda _: httpx.Response(200, text=body))
    with pytest.raises(ProviderError, match=code):
        _ = [event async for event in adapter.stream("hello")]

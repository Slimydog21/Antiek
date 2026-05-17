"""Real Anthropic adapter tests via httpx.MockTransport.

These don't hit the network. They feed canned Anthropic responses through
the actual adapter to verify:

- Request body shape (model / max_tokens / temperature / messages).
- Header construction (x-api-key, anthropic-version, content-type).
- Response parsing including the typed-parts ``content`` array.
- ``stop_reason`` flows through (router normalizes it on emit).
- ``normalize_usage`` correctly extracts ``input_tokens``, ``output_tokens``,
  and ``cache_read_input_tokens`` from the real Anthropic shape.
- Error paths: 401, 429, 5xx, timeout — each maps to ProviderError
  with the correct ``retryable`` flag.
- Prompt-caching mode sends ``cache_control`` on the user message.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.dispatch import AnthropicProvider, ProviderError  # noqa: E402


def _make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_anthropic_basic_call_and_headers_and_body():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["headers"] = dict(req.headers)
        captured["body"] = httpx.Request.read(req)
        return httpx.Response(
            200,
            json={
                "id": "msg_001", "type": "message", "role": "assistant",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "hello back"}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {
                    "input_tokens": 100, "output_tokens": 25,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            headers={"request-id": "req_abc"},
        )

    p = AnthropicProvider(api_key="test-key", client=_make_client(handler))
    raw = p.call(model="claude-opus-4-7", prompt="hello", max_tokens=512, temperature=0.4)

    assert raw.text == "hello back"
    assert raw.finish_reason == "end_turn"
    assert raw.latency_ms >= 0
    assert raw.request_id == "req_abc"

    # Request URL + method
    assert captured["url"].endswith("/v1/messages")
    assert captured["method"] == "POST"

    # Headers — required by Anthropic
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["headers"]["content-type"] == "application/json"

    # Body shape
    import json
    body = json.loads(captured["body"])
    assert body["model"] == "claude-opus-4-7"
    assert body["max_tokens"] == 512
    assert body["temperature"] == 0.4
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_anthropic_multi_part_content_joins_text():
    """Anthropic returns content as a typed-part list. Non-text parts
    must be ignored cleanly so a tool_use sub-part doesn't crash parsing."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "msg_002", "content": [
                {"type": "text", "text": "part-a "},
                {"type": "tool_use", "id": "t1", "name": "calc", "input": {}},
                {"type": "text", "text": "part-b"},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 50, "output_tokens": 10},
        })

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    raw = p.call(model="claude-opus-4-7", prompt="x", max_tokens=10, temperature=0.0)
    assert raw.text == "part-a part-b"
    assert raw.finish_reason == "tool_use"


def test_anthropic_normalize_usage_with_cache_read():
    """Watch-item: cache_read_input_tokens is the cached subset of
    input_tokens. NormalizedUsage.cached_input_tokens carries it."""
    p = AnthropicProvider(api_key="k")
    u = p.normalize_usage({
        "input_tokens": 1200,
        "output_tokens": 350,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 800,
    })
    assert u.input_tokens == 1200  # cached subset is NOT subtracted
    assert u.output_tokens == 350
    assert u.cached_input_tokens == 800


def test_anthropic_normalize_usage_handles_missing_fields():
    """If the provider omits usage entirely, return zeros (do not raise)."""
    p = AnthropicProvider(api_key="k")
    u = p.normalize_usage({})
    assert u.input_tokens == 0
    assert u.output_tokens == 0
    assert u.cached_input_tokens == 0


def test_anthropic_prompt_caching_mode_attaches_cache_control():
    """When prompt caching is enabled, the user message uses the typed-parts
    form with cache_control on the text part."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(httpx.Request.read(req))
        return httpx.Response(200, json={
            "id": "msg_003", "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    p = AnthropicProvider(
        api_key="k", client=_make_client(handler),
        enable_prompt_caching=True,
    )
    p.call(model="m", prompt="long stable prefix...", max_tokens=10, temperature=0.0)

    msg = captured["body"]["messages"][0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "text"
    assert msg["content"][0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status,retryable", [
    (401, False),   # bad key — operator action needed, not retryable
    (400, False),   # malformed request
    (429, True),    # rate limit — retry after backoff
    (500, True),    # server error — retryable
    (502, True),
    (503, True),
    (504, True),
    (529, True),    # Anthropic overloaded
])
def test_anthropic_http_error_maps_to_provider_error(status, retryable):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "fail"}})

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is retryable
    assert ei.value.provider == "anthropic"


def test_anthropic_timeout_maps_to_retryable_provider_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated")

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is True


def test_anthropic_network_error_maps_to_retryable_provider_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns")

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is True


def test_anthropic_invalid_json_raises_non_retryable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is False


def test_anthropic_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()  # no explicit key, no env var
    with pytest.raises(ProviderError, match="API key not configured"):
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)


def test_anthropic_reads_api_key_from_env(monkeypatch):
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["key"] = req.headers["x-api-key"]
        return httpx.Response(200, json={
            "id": "i", "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
    p = AnthropicProvider(client=_make_client(handler))
    p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert captured["key"] == "env-key-123"

"""Real OpenAI-compat adapter tests via httpx.MockTransport.

Covers the response shapes used by DeepSeek, MiMo, Prime, OpenAI itself,
and OpenRouter — they all speak OpenAI chat-completions. Tests verify:

- Request body and headers (Authorization: Bearer, content-type).
- Configurable base_url + chat_completions_path.
- Response parsing including the ``choices[0].message.content`` path.
- ``normalize_usage`` correctly extracts ``prompt_tokens``,
  ``completion_tokens``, and the cached-token field from either
  ``prompt_tokens_details.cached_tokens`` (OpenAI/DeepSeek v3+) or the
  legacy ``prompt_cache_hit_tokens`` (DeepSeek v2-era).
- Error paths: 401, 429, 5xx, timeout, network — each maps correctly.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.dispatch import OpenAICompatProvider, ProviderError  # noqa: E402


def _make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _ok_response_payload(text: str = "out", finish: str = "stop") -> dict[str, Any]:
    return {
        "id": "chatcmpl-001", "object": "chat.completion",
        "model": "x",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": finish,
        }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 12, "total_tokens": 62},
    }


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_openai_compat_basic_call_and_headers_and_body():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["headers"] = dict(req.headers)
        captured["body"] = httpx.Request.read(req)
        return httpx.Response(200, json=_ok_response_payload("hello back"))

    p = OpenAICompatProvider(
        name="deepseek", base_url="https://api.deepseek.com",
        api_key="test-key", client=_make_client(handler),
    )
    raw = p.call(model="deepseek-v4-flash", prompt="hello", max_tokens=128, temperature=0.2)

    assert raw.text == "hello back"
    assert raw.finish_reason == "stop"
    assert raw.latency_ms >= 0

    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["headers"]["content-type"] == "application/json"

    import json
    body = json.loads(captured["body"])
    assert body["model"] == "deepseek-v4-flash"
    assert body["max_tokens"] == 128
    assert body["temperature"] == 0.2
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_openai_compat_extra_body_merged_into_request():
    """extra_body fields (e.g. z.ai's thinking toggle) merge into the request
    body on top of the core shape — the mechanism that lets the zai provider
    run GLM-5.2 with thinking=disabled without a subclass."""
    import json

    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = httpx.Request.read(req)
        return httpx.Response(200, json=_ok_response_payload("ok"))

    p = OpenAICompatProvider(
        name="zai", base_url="https://api.z.ai/api/paas/v4",
        api_key="zai-key", client=_make_client(handler),
        chat_completions_path="/chat/completions",
        extra_body={"thinking": {"type": "disabled"}},
    )
    p.call(model="glm-5.2", prompt="hi", max_tokens=64, temperature=0.2)

    body = json.loads(captured["body"])
    # core request shape intact
    assert body["model"] == "glm-5.2"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    # vendor-specific field merged on top
    assert body["thinking"] == {"type": "disabled"}


def test_openai_compat_no_extra_body_leaves_standard_shape():
    """No extra_body -> the request body is the standard OpenAI shape only
    (no spurious vendor fields). Regression guard for the default path."""
    import json

    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = httpx.Request.read(req)
        return httpx.Response(200, json=_ok_response_payload("ok"))

    p = OpenAICompatProvider(
        name="deepseek", base_url="https://api.deepseek.com",
        api_key="k", client=_make_client(handler),
    )
    p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    body = json.loads(captured["body"])
    assert "thinking" not in body
    assert set(body.keys()) == {"model", "max_tokens", "temperature", "messages"}


def test_openai_compat_custom_chat_completions_path():
    """Some providers omit /v1; configure via ``chat_completions_path``."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json=_ok_response_payload())

    p = OpenAICompatProvider(
        name="mimo", base_url="https://api.example.com",
        api_key="k", client=_make_client(handler),
        chat_completions_path="/chat/completions",  # no /v1
    )
    p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert captured["url"] == "https://api.example.com/chat/completions"


# ── Usage normalization — the watch-item ────────────────────────────


def test_openai_compat_normalize_with_prompt_tokens_details_cached():
    """OpenAI / DeepSeek v3+ shape: cached count under
    ``prompt_tokens_details.cached_tokens``."""
    p = OpenAICompatProvider(name="t", base_url="x", api_key="k")
    u = p.normalize_usage({
        "prompt_tokens": 2000,
        "completion_tokens": 500,
        "total_tokens": 2500,
        "prompt_tokens_details": {"cached_tokens": 1500},
    })
    assert u.input_tokens == 2000
    assert u.output_tokens == 500
    assert u.cached_input_tokens == 1500


def test_openai_compat_normalize_with_legacy_prompt_cache_hit_tokens():
    """DeepSeek v2-era shape: ``prompt_cache_hit_tokens`` at top level.
    The adapter must read both shapes to survive provider rollouts."""
    p = OpenAICompatProvider(name="t", base_url="x", api_key="k")
    u = p.normalize_usage({
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "prompt_cache_hit_tokens": 700,
    })
    assert u.cached_input_tokens == 700


def test_openai_compat_normalize_without_cache_field_returns_zero():
    p = OpenAICompatProvider(name="t", base_url="x", api_key="k")
    u = p.normalize_usage({"prompt_tokens": 100, "completion_tokens": 50})
    assert u.cached_input_tokens == 0


def test_openai_compat_normalize_handles_missing_usage():
    p = OpenAICompatProvider(name="t", base_url="x", api_key="k")
    u = p.normalize_usage({})
    assert (u.input_tokens, u.output_tokens, u.cached_input_tokens) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status,retryable", [
    (401, False),
    (400, False),
    (429, True),
    (500, True),
    (502, True),
    (503, True),
    (504, True),
])
def test_openai_compat_http_error_maps_correctly(status, retryable):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "fail", "type": "x"}})

    p = OpenAICompatProvider(
        name="x", base_url="https://e.example.com", api_key="k",
        client=_make_client(handler),
    )
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is retryable
    assert ei.value.provider == "x"


def test_openai_compat_timeout_maps_retryable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    p = OpenAICompatProvider(
        name="x", base_url="https://e.example.com", api_key="k",
        client=_make_client(handler),
    )
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is True


def test_openai_compat_network_error_maps_retryable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns")

    p = OpenAICompatProvider(
        name="x", base_url="https://e.example.com", api_key="k",
        client=_make_client(handler),
    )
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is True


def test_openai_compat_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = OpenAICompatProvider(
        name="deepseek", base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )
    with pytest.raises(ProviderError, match="API key not configured"):
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)


def test_openai_compat_reads_api_key_from_env(monkeypatch):
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["auth"] = req.headers["authorization"]
        return httpx.Response(200, json=_ok_response_payload())

    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-ds-key")
    p = OpenAICompatProvider(
        name="deepseek", base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY", client=_make_client(handler),
    )
    p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert captured["auth"] == "Bearer env-ds-key"


def test_openai_compat_unexpected_shape_raises_non_retryable():
    """Provider returns 200 but with a body that doesn't match the
    chat-completions schema — adapter must raise rather than crash on
    the next role call site."""

    def handler(req: httpx.Request) -> httpx.Response:
        # No 'choices' field — schema-broken response.
        return httpx.Response(200, json={"id": "x", "object": "garbage"})

    p = OpenAICompatProvider(
        name="x", base_url="https://e.example.com", api_key="k",
        client=_make_client(handler),
    )
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is False

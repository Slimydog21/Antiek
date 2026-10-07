"""Shared builders and parsers preserve the ordinary HTTP adapter contract."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from substrate.dispatch.base import ProviderError, RawProviderResponse
from substrate.dispatch.providers.anthropic import AnthropicProvider
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from substrate.dispatch.providers.wire_request import BuiltProviderRequest

_KEY = "synthetic-wire-credential"
_PROMPT = "private synthetic source"


def _openai_payload() -> dict[str, Any]:
    return {
        "id": "chat-1", "object": "chat.completion",
        "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }


def _anthropic_payload() -> dict[str, Any]:
    return {
        "id": "msg-1", "model": "response-model",
        "content": [
            {"type": "text", "text": "first"},
            {"type": "tool_use", "name": "ignored"},
            {"type": "text", "text": " second"},
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 7, "output_tokens": 3,
            "cache_read_input_tokens": 2, "cache_creation_input_tokens": 4,
        },
    }


def test_openai_call_uses_variant_builder_once_and_preserves_override_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds: list[BuiltProviderRequest] = []
    parsed: list[str] = []
    requests: list[httpx.Request] = []

    class VariantProvider(OpenAICompatProvider):
        def build_request(self, **kwargs: Any) -> BuiltProviderRequest:
            assert kwargs["model"] == "catalog-model"
            kwargs["model"] = "wire-model"
            built = super().build_request(**kwargs)
            builds.append(built)
            return built

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_openai_payload(), headers={"x-request-id": "req-1"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = VariantProvider(
            name="selected-provider", base_url="https://example.invalid/root/",
            chat_completions_path="/chat/completions", api_key=_KEY, client=client,
            extra_body={"model": "constructor-model", "max_tokens": 100, "vendor": True},
        )
        parser = provider.parse_response

        def parse(response: httpx.Response, **kwargs: Any) -> RawProviderResponse:
            parsed.append(kwargs["model"])
            return parser(response, **kwargs)

        monkeypatch.setattr(provider, "parse_response", parse)
        raw = provider.call(
            model="catalog-model", prompt=_PROMPT, max_tokens=30, temperature=0.4,
            extra_body={"model": "call-model", "max_tokens": 20},
        )

    assert len(builds) == len(requests) == 1
    assert parsed == ["wire-model"]
    built = builds[0]
    assert built.model == "wire-model"
    assert str(requests[0].url) == built.url == "https://example.invalid/root/chat/completions"
    assert requests[0].headers["authorization"] == built.headers["Authorization"] == f"Bearer {_KEY}"
    assert json.loads(requests[0].content) == built.body == {
        "model": "call-model", "max_tokens": 20, "temperature": 0.4,
        "messages": [{"role": "user", "content": _PROMPT}], "vendor": True,
    }
    assert provider._extra_body == {"model": "constructor-model", "max_tokens": 100, "vendor": True}
    assert raw == parser(
        httpx.Response(200, json=_openai_payload(), headers={"x-request-id": "req-1"}),
        model="wire-model", api_key=_KEY, latency_ms=raw.latency_ms, request_url=built.url,
    )
    assert raw.text == "answer" and raw.request_id == "req-1"
    assert _KEY not in repr(built) and _PROMPT not in repr(built)


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-4-7"])
@pytest.mark.parametrize("cache", [False, True])
def test_anthropic_builder_and_call_preserve_temperature_cache_and_parts(
    model: str, cache: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_anthropic_payload(), headers={"request-id": "req-2"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = AnthropicProvider(api_key=_KEY, client=client, enable_prompt_caching=cache)
        built = provider.build_request(
            model=model, prompt=_PROMPT, max_tokens=30, temperature=0.4, api_key=_KEY,
        )
        builder = provider.build_request
        calls = 0

        def build(**kwargs: Any) -> BuiltProviderRequest:
            nonlocal calls
            calls += 1
            return builder(**kwargs)

        monkeypatch.setattr(provider, "build_request", build)
        raw = provider.call(model=model, prompt=_PROMPT, max_tokens=30, temperature=0.4)

    assert calls == len(requests) == 1
    body = json.loads(requests[0].content)
    assert body == built.body
    assert str(requests[0].url) == built.url == "https://api.anthropic.com/v1/messages"
    assert requests[0].headers["x-api-key"] == built.headers["x-api-key"] == _KEY
    assert requests[0].headers["anthropic-version"] == "2023-06-01"
    if model == "claude-sonnet-5":
        assert "temperature" not in body
    else:
        assert body["temperature"] == 0.4
    expected_content: Any = _PROMPT
    if cache:
        expected_content = [{"type": "text", "text": _PROMPT, "cache_control": {"type": "ephemeral"}}]
    assert body["messages"] == [{"role": "user", "content": expected_content}]
    assert raw == provider.parse_response(
        httpx.Response(200, json=_anthropic_payload(), headers={"request-id": "req-2"}),
        model=model, api_key=_KEY, latency_ms=raw.latency_ms,
    )
    assert raw.text == "first second" and raw.request_id == "req-2"
    usage = provider.normalize_usage(raw.raw_usage)
    assert (usage.input_tokens, usage.cached_input_tokens, usage.cache_creation_input_tokens) == (13, 2, 4)
    assert _KEY not in repr(built) and _PROMPT not in repr(built)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_direct_builder_never_resolves_credentials_or_constructs_client(
    kind: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = (
        OpenAICompatProvider(name="selected", base_url="https://example.invalid")
        if kind == "openai" else AnthropicProvider()
    )

    def forbidden() -> None:
        pytest.fail("construction/parsing must not resolve credentials or create clients")

    monkeypatch.setattr(provider, "_resolve_api_key", forbidden)
    monkeypatch.setattr(provider, "_ensure_client", forbidden)
    built = provider.build_request(
        model="selected-model", prompt=_PROMPT, max_tokens=30, temperature=0.4, api_key=_KEY,
    )
    payload = _openai_payload() if kind == "openai" else _anthropic_payload()
    raw = provider.parse_response(httpx.Response(200, json=payload), model=built.model, api_key=_KEY, latency_ms=7)
    assert raw.latency_ms == 7
    assert provider._client is None
    assert _KEY not in repr(built) and _PROMPT not in repr(built)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize("reflection", ["text", "escaped", "metadata"])
def test_shared_parser_preserves_successful_response_reflection_rejection(
    kind: str, reflection: str,
) -> None:
    payload = _openai_payload() if kind == "openai" else _anthropic_payload()
    if reflection == "metadata":
        payload["private"] = {_KEY: "untrusted value"}
    elif kind == "openai":
        payload["choices"][0]["message"]["content"] = _KEY
    else:
        payload["content"] = [{"type": "text", "text": _KEY}]
    content = json.dumps(payload)
    if reflection == "escaped":
        content = content.replace(_KEY, "".join(f"\\u{ord(char):04x}" for char in _KEY))
        assert _KEY not in content

    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=content))) as client:
        provider = (
            OpenAICompatProvider(name="selected", base_url="https://example.invalid", api_key=_KEY,
                                 client=client, expose_error_body=False)
            if kind == "openai" else AnthropicProvider(api_key=_KEY, client=client, expose_error_body=False)
        )
        with pytest.raises(ProviderError, match="contained credential material") as ordinary:
            provider.call(model="selected-model", prompt=_PROMPT, max_tokens=30, temperature=0.4)
        with pytest.raises(ProviderError, match="contained credential material") as direct:
            provider.parse_response(httpx.Response(200, text=content), model="selected-model", api_key=_KEY, latency_ms=0)

    assert str(ordinary.value) == str(direct.value)
    assert _KEY not in str(ordinary.value)
    assert ordinary.value.request_id is None


def test_anthropic_shared_parser_rejects_secret_reassembled_from_parts() -> None:
    payload = _anthropic_payload()
    payload["content"] = [
        {"type": "text", "text": _KEY[:8]},
        {"type": "text", "text": _KEY[8:]},
    ]
    content = json.dumps(payload)
    assert _KEY not in content
    provider = AnthropicProvider(expose_error_body=False)
    with pytest.raises(ProviderError, match="contained credential material"):
        provider.parse_response(httpx.Response(200, text=content), model="selected-model", api_key=_KEY, latency_ms=0)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize("expose", [False, True])
def test_shared_parser_preserves_http_error_controls(kind: str, expose: bool) -> None:
    headers = {"request-id": "req-error", "x-request-id": "req-error"}
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, text="upstream detail", headers=headers)
    )) as client:
        provider = (
            OpenAICompatProvider(name="selected", base_url="https://example.invalid", api_key=_KEY,
                                 client=client, expose_error_body=expose)
            if kind == "openai" else AnthropicProvider(api_key=_KEY, client=client, expose_error_body=expose)
        )
        with pytest.raises(ProviderError) as ordinary:
            provider.call(model="selected-model", prompt=_PROMPT, max_tokens=30, temperature=0.4)
        with pytest.raises(ProviderError) as direct:
            provider.parse_response(httpx.Response(429, text="upstream detail", headers=headers),
                                    model="selected-model", api_key=_KEY, latency_ms=0)

    assert str(ordinary.value) == str(direct.value)
    assert ordinary.value.retryable and direct.value.retryable
    assert ordinary.value.model == direct.value.model == "selected-model"
    assert ordinary.value.request_id == ("req-error" if expose else None)
    assert ("upstream detail" in str(ordinary.value)) is expose


def test_openai_error_keeps_captured_url_and_pre_override_model() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        provider.base_url = "https://changed.invalid"
        return httpx.Response(400, text="invalid", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAICompatProvider(
            name="selected", base_url="https://original.invalid", api_key=_KEY, client=client,
        )
        with pytest.raises(ProviderError) as failure:
            provider.call(model="original-model", prompt=_PROMPT, max_tokens=30, temperature=0.4,
                          extra_body={"model": "overridden-model"})

    assert failure.value.model == "original-model"
    assert failure.value.endpoint == "https://original.invalid/v1/chat/completions"

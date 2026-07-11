from __future__ import annotations

import hashlib
from collections.abc import Callable

import httpx
import pytest

from substrate.dispatch.providers._safe_diagnostics import correlation_digest
from substrate.dispatch.providers.vision_anthropic import (
    AnthropicVisionProvider,
    VisionProvider,
    VisionProviderError,
)
from substrate.dispatch.providers.vision_openai import OpenAIVisionProvider


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _json_client(payload: object) -> httpx.Client:
    return _client(lambda _request: httpx.Response(200, json=payload))


def _raw_json_client(body: bytes) -> httpx.Client:
    return _client(lambda _request: httpx.Response(200, content=body))


def test_correlation_projection_is_keyed_and_stable_within_process() -> None:
    secret = "candidate-provider-secret"
    projected = correlation_digest(secret)

    assert projected == correlation_digest(secret)
    assert projected is not None
    assert projected.startswith("hmac-sha256:")
    assert projected != f"sha256:{hashlib.sha256(secret.encode()).hexdigest()}"
    assert secret not in projected


def _assert_vision_http_error_omits_upstream_body_and_api_key(
    provider_factory: Callable[[str, httpx.Client], VisionProvider],
    secret_header: str,
) -> None:
    secret = "sk-vision-reflected-secret"
    attacker_text = "attacker-controlled-diagnostic"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text=f"{attacker_text}: {request.headers[secret_header]}",
            headers={"x-request-id": secret},
        )

    provider = provider_factory(secret, _client(handler))
    with pytest.raises(VisionProviderError) as exc_info:
        provider.call_vision(
            model="vision-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
            max_output_tokens=20,
            temperature=0.0,
        )

    rendered = str(exc_info.value)
    assert "HTTP 401" in rendered
    assert secret not in rendered
    assert attacker_text not in rendered
    assert exc_info.value.provider in {"openai_vision", "anthropic_vision"}
    assert exc_info.value.status_code == 401
    assert exc_info.value.retryable is False
    assert exc_info.value.request_id == correlation_digest(secret)


def _assert_vision_transport_error_omits_exception_text_and_api_key(
    provider_factory: Callable[[str, httpx.Client], VisionProvider],
    secret_header: str,
) -> None:
    secret = "sk-vision-transport-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"reflected {request.headers[secret_header]}",
            request=request,
        )

    provider = provider_factory(secret, _client(handler))
    with pytest.raises(VisionProviderError) as exc_info:
        provider.call_vision(
            model="vision-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
        )

    assert secret not in str(exc_info.value)
    assert "ConnectError" in str(exc_info.value)
    assert exc_info.value.retryable is True
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_openai_vision_http_error_omits_upstream_body_and_api_key() -> None:
    _assert_vision_http_error_omits_upstream_body_and_api_key(
        lambda secret, client: OpenAIVisionProvider(
            api_key=secret,
            client=client,
        ),
        "authorization",
    )

    _assert_vision_transport_error_omits_exception_text_and_api_key(
        lambda secret, client: OpenAIVisionProvider(
            api_key=secret,
            client=client,
        ),
        "authorization",
    )


def test_anthropic_vision_http_error_omits_upstream_body_and_api_key() -> None:
    _assert_vision_http_error_omits_upstream_body_and_api_key(
        lambda secret, client: AnthropicVisionProvider(
            api_key=secret,
            client=client,
        ),
        "x-api-key",
    )

    _assert_vision_transport_error_omits_exception_text_and_api_key(
        lambda secret, client: AnthropicVisionProvider(
            api_key=secret,
            client=client,
        ),
        "x-api-key",
    )


def test_anthropic_vision_200_error_object_fails_without_copying_body() -> None:
    secret = "sk-vision-200-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"type": "error", "error": {"message": request.headers["x-api-key"]}},
        )

    provider = AnthropicVisionProvider(api_key=secret, client=_client(handler))
    with pytest.raises(VisionProviderError) as exc_info:
        provider.call_vision(
            model="vision-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
        )

    assert str(exc_info.value) == "anthropic_vision: unexpected response shape"
    assert secret not in str(exc_info.value)


def test_openai_vision_malformed_success_is_structured() -> None:
    payloads: tuple[object, ...] = (
        [],
        {"choices": [1]},
        {"choices": [{"message": 1}]},
        {"choices": [{"message": {"content": "ok"}}], "usage": "secret"},
        {"choices": [{"message": {"content": []}}]},
        {"choices": [{"message": {"content": [{"type": "tool_call"}]}}]},
    )
    for payload in payloads:
        provider = OpenAIVisionProvider(
            api_key="key",
            client=_json_client(payload),
        )
        with pytest.raises(VisionProviderError) as exc_info:
            provider.call_vision(
                model="vision-model",
                system_prompt="system",
                user_text="question",
                image_url="https://assets.example/image.png",
            )

        assert str(exc_info.value) == "openai_vision: unexpected response shape"
        assert exc_info.value.provider == "openai_vision"
        assert exc_info.value.latency_ms >= 0
        assert exc_info.value.retryable is False

    overflow_provider = OpenAIVisionProvider(
        api_key="key",
        client=_raw_json_client(
            b'{"choices":[{"message":{"content":"ok"}}],'
            b'"usage":{"prompt_tokens":1e400}}'
        ),
    )
    with pytest.raises(VisionProviderError) as overflow_info:
        overflow_provider.call_vision(
            model="vision-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
        )
    assert str(overflow_info.value) == "openai_vision: unexpected response shape"


def test_anthropic_vision_malformed_usage_is_structured() -> None:
    provider = AnthropicVisionProvider(
        api_key="key",
        client=_client(
            lambda _request: httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": "secret",
                },
            )
        ),
    )
    with pytest.raises(VisionProviderError) as exc_info:
        provider.call_vision(
            model="vision-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
        )

    assert str(exc_info.value) == "anthropic_vision: unexpected response shape"
    assert exc_info.value.provider == "anthropic_vision"
    assert exc_info.value.latency_ms >= 0
    assert exc_info.value.retryable is False


def test_anthropic_vision_empty_or_non_text_output_is_structured() -> None:
    for payload in (
        {"content": [{"type": "text", "text": ""}]},
        {"content": [{"type": "tool_use", "id": "tool"}]},
    ):
        provider = AnthropicVisionProvider(
            api_key="key",
            client=_json_client(payload),
        )
        with pytest.raises(VisionProviderError) as exc_info:
            provider.call_vision(
                model="vision-model",
                system_prompt="system",
                user_text="question",
                image_url="https://assets.example/image.png",
            )

        assert str(exc_info.value) == "anthropic_vision: unexpected response shape"
        assert exc_info.value.provider == "anthropic_vision"


def test_anthropic_vision_non_finite_usage_is_structured() -> None:
    provider = AnthropicVisionProvider(
        api_key="key",
        client=_raw_json_client(
            b'{"content":[{"type":"text","text":"ok"}],'
            b'"usage":{"input_tokens":1e400}}'
        ),
    )
    with pytest.raises(VisionProviderError) as exc_info:
        provider.call_vision(
            model="vision-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
        )

    assert str(exc_info.value) == "anthropic_vision: unexpected response shape"
    assert exc_info.value.provider == "anthropic_vision"


def test_vision_uses_requested_model_not_provider_metadata() -> None:
    secret = "sk-reflected-model"
    openai = OpenAIVisionProvider(
        api_key="key",
        client=_json_client(
            {
                "model": secret,
                "choices": [{"message": {"content": "ok"}}],
            }
        ),
    )
    anthropic = AnthropicVisionProvider(
        api_key="key",
        client=_json_client(
            {
                "model": secret,
                "content": [{"type": "text", "text": "ok"}],
            }
        ),
    )

    for provider in (openai, anthropic):
        result = provider.call_vision(
            model="requested-model",
            system_prompt="system",
            user_text="question",
            image_url="https://assets.example/image.png",
        )
        assert result.model == "requested-model"
        assert secret not in repr(result)

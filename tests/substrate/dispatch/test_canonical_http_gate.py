"""Behavior of the private final gate with no transport injection in its API."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from decimal import Decimal
from typing import Any, Literal

import httpx
import pytest

from substrate.dispatch import canonical_http as gate
from substrate.dispatch.base import ProviderError, RawProviderResponse
from substrate.dispatch.providers.anthropic import AnthropicProvider
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from substrate.dispatch.providers.wire_request import BuiltProviderRequest

_SECRET = "synthetic-canonical-gate-key"
_NONCE = "a" * 64
_TIMEOUT = {key: 120.0 for key in ("connect", "read", "write", "pool")}
Protocol = Literal["openai_compat", "anthropic"]


def _policy(protocol: Protocol = "openai_compat") -> gate.AdmittedCanonicalPolicy:
    model = "gpt-4.1-mini" if protocol == "openai_compat" else "claude-sonnet-4-5"
    endpoint = (
        "https://api.openai.com/v1/chat/completions" if protocol == "openai_compat"
        else "https://api.anthropic.com/v1/messages"
    )
    return gate.AdmittedCanonicalPolicy(
        protocol=protocol, provider_id="synthetic-owner-model", catalog_model=model,
        wire_model=model, endpoint=endpoint, prompt="private synthetic canonical input",
        output_limit=16, temperature=0.0, thinking=None,
        input_rate=Decimal("0.000002"), output_rate=Decimal("0.000008"),
        price_snapshot="synthetic-rates-v1", credential_fingerprint="b" * 64,
        registration_generation=3,
    )


def _provider(policy: gate.AdmittedCanonicalPolicy) -> OpenAICompatProvider | AnthropicProvider:
    if policy.protocol == "openai_compat":
        return OpenAICompatProvider(
            name=policy.provider_id, base_url=policy.endpoint.removesuffix("/v1/chat/completions"),
            expose_error_body=False,
        )
    return AnthropicProvider(expose_error_body=False)


def _payload(policy: gate.AdmittedCanonicalPolicy) -> dict[str, Any]:
    if policy.protocol == "openai_compat":
        return {
            "id": "chatcmpl-synthetic-1", "object": "chat.completion", "model": policy.wire_model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "answer"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
    return {
        "id": "msg-synthetic-1", "type": "message", "role": "assistant", "model": policy.wire_model,
        "content": [{"type": "text", "text": "first"}, {"type": "text", "text": " second"}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 7, "output_tokens": 3,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    }


class ExchangeFixture:
    def __init__(self, policy: gate.AdmittedCanonicalPolicy, monkeypatch: pytest.MonkeyPatch) -> None:
        self.policy = policy
        self.claims: list[str] = []
        self.requests: list[httpx.Request] = []
        self.respond: Callable[[httpx.Request], httpx.Response] = (
            lambda request: httpx.Response(200, json=_payload(policy))
        )
        monkeypatch.setattr(gate, "_new_inner_transport", lambda: httpx.MockTransport(self.send))

    def send(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def claim(self, digest: str) -> str:
        assert len(digest) == 64 and _SECRET not in digest
        self.claims.append(digest)
        return _NONCE

    def execute(self, provider: OpenAICompatProvider | AnthropicProvider | None = None) -> gate.CanonicalExchange:
        return gate.execute_owned_http(self.policy, provider or _provider(self.policy), _SECRET, self.claim)


def _request(
    policy: gate.AdmittedCanonicalPolicy, *, content: bytes | None = None,
    headers: list[tuple[str, str]] | None = None, extensions: dict[str, Any] | None = None,
    stream: httpx.SyncByteStream | None = None,
) -> httpx.Request:
    provider = _provider(policy)
    built = provider.build_request(
        model=policy.catalog_model, prompt=policy.prompt, max_tokens=policy.output_limit,
        temperature=policy.temperature or 0.0, api_key=_SECRET,
    )
    base_headers = list(built.headers.items()) + [
        ("Accept", "application/json"), ("Accept-Encoding", "identity"),
        ("Connection", "keep-alive"), ("User-Agent", "Antiek-OwnedCanonical/1"),
    ]
    arguments: dict[str, Any] = {
        "headers": base_headers + (headers or []),
        "extensions": extensions if extensions is not None else {"timeout": dict(_TIMEOUT)},
    }
    if stream is not None:
        arguments["stream"] = stream
    elif content is not None:
        arguments["content"] = content
    else:
        arguments["json"] = built.body
    return httpx.Request("POST", policy.endpoint, **arguments)


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
def test_real_builders_serialize_one_claimed_exchange(
    protocol: Protocol, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(protocol)
    fixture = ExchangeFixture(policy, monkeypatch)
    response_bytes = json.dumps(_payload(policy), separators=(",", ":")).encode()
    fixture.respond = lambda request: httpx.Response(200, content=response_bytes)
    exchange = fixture.execute()
    assert len(fixture.claims) == len(fixture.requests) == 1
    request = fixture.requests[0]
    assert request.method == "POST" and str(request.url) == policy.endpoint
    assert json.loads(request.content) == policy.expected_body()
    assert request.extensions == {"timeout": _TIMEOUT}
    assert exchange.request_digest == fixture.claims[0]
    assert exchange.response_digest == hashlib.sha256(response_bytes).hexdigest()
    assert exchange.claim_nonce_digest == _NONCE
    assert exchange.input_tokens == 7 and exchange.output_tokens == 3
    assert exchange.cost_micro_usd == 38
    assert exchange.parsed.text == ("answer" if protocol == "openai_compat" else "first second")
    assert exchange.parsed.request_id is None


def test_actual_catalog_variant_maps_wire_model_and_thinking_disabled_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from interfaces.research.api.settings_models_admin import (
        UserModelRecord,
        _UserOpenAICompatProvider,
    )

    policy = replace(
        _policy(), catalog_model="deepseek-flash-nothink", wire_model="deepseek-flash",
        endpoint="https://api.deepseek.com/chat/completions", thinking="disabled",
    )
    provider = _UserOpenAICompatProvider(UserModelRecord(
        id=policy.provider_id, owner_user_id="synthetic-owner", provider_kind="openai_compat",
        provider_catalog_id="deepseek", model_id=policy.catalog_model,
        display_name="Synthetic", base_url="https://api.deepseek.com",
        cred_ref="synthetic-reference", cred_fingerprint="b" * 64,
    ))
    fixture = ExchangeFixture(policy, monkeypatch)
    exchange = fixture.execute(provider)
    assert len(fixture.claims) == len(fixture.requests) == 1
    body = json.loads(fixture.requests[0].content)
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert exchange.provider_response_id == "chatcmpl-synthetic-1"


@pytest.mark.parametrize("extra", [
    {"model": "foreign-model"}, {"max_tokens": 17},
    {"messages": [{"role": "system", "content": "unadmitted"}]},
    {"thinking": {"type": "enabled"}}, {"tools": []}, {"stream": True},
    {"temperature": False}, {"max_tokens": True},
])
def test_hostile_real_builder_output_refuses_before_claim(
    extra: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    provider = OpenAICompatProvider(
        name="synthetic-owner-model", base_url="https://api.openai.com", extra_body=extra,
    )
    with pytest.raises(gate.CanonicalHttpRefused):
        fixture.execute(provider)
    assert fixture.claims == [] and fixture.requests == []


@pytest.mark.parametrize("attack", ["url", "key", "header", "duplicate_auth"])
def test_constructed_url_and_headers_cannot_approve_themselves(
    attack: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AlteredBuilder(OpenAICompatProvider):
        def build_request(self, **kwargs: Any) -> BuiltProviderRequest:
            built = super().build_request(**kwargs)
            if attack == "url":
                return replace(built, url="https://unapproved.invalid/v1/chat/completions")
            headers = dict(built.headers)
            if attack == "key":
                headers["Authorization"] = "Bearer foreign-key"
            elif attack == "header":
                headers["Cookie"] = "unapproved=1"
            else:
                headers["authorization"] = headers["Authorization"]
            return replace(built, headers=headers)

    fixture = ExchangeFixture(_policy(), monkeypatch)
    with pytest.raises(gate.CanonicalHttpRefused):
        fixture.execute(AlteredBuilder(name="selected", base_url="https://api.openai.com"))
    assert fixture.claims == [] and fixture.requests == []


@pytest.mark.parametrize("raw", [
    b'{"model":"a","model":"b"}', b'{"temperature":NaN}',
    b'{"temperature":Infinity}', b'{"temperature":1e999}', b'\xff', b'[]',
])
def test_final_gate_rejects_ambiguous_or_nonfinite_actual_json(
    raw: bytes, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    with (gate._FinalRequestGate(fixture.policy, _SECRET, fixture.claim) as transport,
          pytest.raises(gate.CanonicalHttpRefused)):
        transport.handle_request(_request(fixture.policy, content=raw))
    assert fixture.claims == [] and fixture.requests == []


@pytest.mark.parametrize("headers", [
    [("Host", "foreign.invalid")], [("Content-Encoding", "gzip")],
    [("X-Api-Key", "second-auth")], [("Content-Length", "0")],
    [("Authorization", f"Bearer {_SECRET}")],
])
def test_final_gate_rejects_actual_header_changes(
    headers: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    with (gate._FinalRequestGate(fixture.policy, _SECRET, fixture.claim) as transport,
          pytest.raises(gate.CanonicalHttpRefused)):
        transport.handle_request(_request(fixture.policy, headers=headers))
    assert fixture.claims == [] and fixture.requests == []


@pytest.mark.parametrize("extension", ["sni_hostname", "trace", "timeout"])
def test_final_gate_rejects_transport_extension_changes(
    extension: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    called = False

    def trace(*args: Any) -> None:
        nonlocal called
        called = True

    extensions: dict[str, Any] = {"timeout": dict(_TIMEOUT)}
    extensions[extension] = trace if extension == "trace" else "unapproved"
    with (gate._FinalRequestGate(fixture.policy, _SECRET, fixture.claim) as transport,
          pytest.raises(gate.CanonicalHttpRefused, match="request_extensions_changed")):
        transport.handle_request(_request(fixture.policy, extensions=extensions))
    assert fixture.claims == [] and fixture.requests == [] and not called


def test_arbitrary_request_stream_is_not_iterated_before_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    class ForeignStream(httpx.SyncByteStream):
        iterated = False

        def __iter__(self) -> Iterator[bytes]:
            self.iterated = True
            yield b"unapproved"

    fixture = ExchangeFixture(_policy(), monkeypatch)
    stream = ForeignStream()
    with (gate._FinalRequestGate(fixture.policy, _SECRET, fixture.claim) as transport,
          pytest.raises(gate.CanonicalHttpRefused, match="request_shape_changed")):
        transport.handle_request(_request(fixture.policy, stream=stream))
    assert not stream.iterated and fixture.claims == [] and fixture.requests == []


@pytest.mark.parametrize("field,value", [
    ("registration_generation", 4), ("price_snapshot", "replacement"),
    ("prompt", "changed source"), ("credential_fingerprint", "c" * 64),
])
def test_mutated_policy_after_gate_creation_refuses_before_claim(
    field: str, value: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    request = _request(fixture.policy)
    with gate._FinalRequestGate(fixture.policy, _SECRET, fixture.claim) as transport:
        object.__setattr__(fixture.policy, field, value)
        with pytest.raises(gate.CanonicalHttpRefused, match="policy_changed"):
            transport.handle_request(request)
    assert fixture.claims == [] and fixture.requests == []


@pytest.mark.parametrize("outcome", ["generation_changed", "lost", "invalid_nonce"])
def test_claim_refusal_or_invalid_return_never_delegates(
    outcome: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)

    def claim(digest: str) -> str:
        fixture.claims.append(digest)
        if outcome == "generation_changed":
            raise gate.CanonicalHttpRefused("current_registration_changed")
        if outcome == "lost":
            raise gate.CanonicalClaimLost("another_worker")
        return "invalid"

    with pytest.raises(gate.CanonicalHttpRefused):
        gate.execute_owned_http(fixture.policy, _provider(fixture.policy), _SECRET, claim)
    # This callback ran; the test does not claim a durable write was rolled back.
    assert len(fixture.claims) == 1 and fixture.requests == []


def test_foreign_registered_client_hooks_and_auth_are_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    class ForeignAuth(httpx.Auth):
        def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
            called.append("auth")
            yield request

    def foreign_send(request: httpx.Request) -> httpx.Response:
        called.append("send")
        return httpx.Response(200, json={})

    fixture = ExchangeFixture(_policy(), monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(foreign_send), auth=ForeignAuth(),
                      event_hooks={"request": [lambda request: called.append("hook")]}) as foreign:
        provider = OpenAICompatProvider(name="selected", base_url="https://api.openai.com", client=foreign)
        fixture.execute(provider)
    assert called == [] and len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("status", [307, 401, 429, 500])
def test_redirect_auth_and_retryable_status_never_send_again(
    status: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    fixture.respond = lambda request: httpx.Response(
        status, headers={"Location": "https://unapproved.invalid", "WWW-Authenticate": "Basic"},
    )
    with pytest.raises(gate.CanonicalHttpRefused, match="response_status"):
        fixture.execute()
    assert len(fixture.claims) == len(fixture.requests) == 1


def test_second_entry_does_not_reclaim_or_send(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)
    with gate._FinalRequestGate(fixture.policy, _SECRET, fixture.claim) as transport:
        transport.handle_request(_request(fixture.policy)).close()
        with pytest.raises(gate.CanonicalHttpRefused, match="second_exchange"):
            transport.handle_request(_request(fixture.policy))
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
def test_hostile_instance_parser_cannot_replace_private_response_text(
    protocol: Protocol, monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fabricated(response: httpx.Response, **kwargs: Any) -> RawProviderResponse:
        nonlocal called
        called = True
        return RawProviderResponse(text="fabricated private text", raw_usage={}, finish_reason="stop", latency_ms=0)

    fixture = ExchangeFixture(_policy(protocol), monkeypatch)
    provider = _provider(fixture.policy)
    # Deliberately hostile instance attribute. Production must call the shared
    # implementation directly; only the inner factory is monkeypatched here.
    provider.parse_response = fabricated  # type: ignore[method-assign]
    exchange = fixture.execute(provider)
    assert not called
    assert exchange.parsed.text == ("answer" if protocol == "openai_compat" else "first second")
    assert len(fixture.claims) == len(fixture.requests) == 1


def test_builder_cannot_mutate_policy_before_the_gate_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = _policy()

    class MutatingBuilder(OpenAICompatProvider):
        def build_request(self, **kwargs: Any) -> BuiltProviderRequest:
            object.__setattr__(policy, "registration_generation", policy.registration_generation + 1)
            return super().build_request(**kwargs)

    fixture = ExchangeFixture(policy, monkeypatch)
    with pytest.raises(gate.CanonicalHttpRefused, match="policy_changed"):
        fixture.execute(MutatingBuilder(name="selected", base_url="https://api.openai.com"))
    assert fixture.claims == [] and fixture.requests == []


def test_two_owner_inputs_share_adapter_without_sharing_key_or_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    first_policy = _policy()
    second_policy = replace(first_policy, prompt="second owner private input", credential_fingerprint="d" * 64)
    fixture = ExchangeFixture(first_policy, monkeypatch)
    provider = _provider(first_policy)
    first = gate.execute_owned_http(first_policy, provider, _SECRET, fixture.claim)
    second = gate.execute_owned_http(second_policy, provider, "second-synthetic-key", fixture.claim)
    assert len(fixture.claims) == len(fixture.requests) == 2
    assert first.request_digest != second.request_digest
    assert [request.headers["authorization"] for request in fixture.requests] == [
        f"Bearer {_SECRET}", "Bearer second-synthetic-key",
    ]
    assert [json.loads(request.content)["messages"][0]["content"] for request in fixture.requests] == [
        first_policy.prompt, second_policy.prompt,
    ]
    assert provider._client is None


def test_timeout_after_claim_has_one_possible_send_and_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = ExchangeFixture(_policy(), monkeypatch)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    fixture.respond = timeout
    with pytest.raises(httpx.ReadTimeout):
        fixture.execute()
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
@pytest.mark.parametrize("attack", ["model", "id", "usage", "bool_count", "negative", "too_large", "cache", "extra_bill"])
def test_post_send_unverified_identity_and_usage_retain_claim_and_send_facts(
    protocol: Protocol, attack: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(protocol)
    fixture = ExchangeFixture(policy, monkeypatch)
    payload = _payload(policy)
    count_key = "prompt_tokens" if protocol == "openai_compat" else "input_tokens"
    if attack == "model":
        payload["model"] = "unverified-model"
    elif attack == "id":
        payload.pop("id")
    elif attack == "usage":
        payload.pop("usage")
    elif attack in {"bool_count", "negative", "too_large"}:
        payload["usage"][count_key] = {"bool_count": True, "negative": -1, "too_large": 1 << 31}[attack]
    elif attack == "cache":
        if protocol == "openai_compat":
            payload["usage"]["prompt_tokens_details"] = {"cached_tokens": 1}
        else:
            payload["usage"]["cache_creation_input_tokens"] = 1
    else:
        payload["usage"]["unpriced_tokens"] = 1
    fixture.respond = lambda request: httpx.Response(200, json=payload)
    with pytest.raises(gate.CanonicalHttpRefused):
        fixture.execute()
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
@pytest.mark.parametrize("expose_error_body", [False, True])
def test_post_send_secret_reflection_never_becomes_text(
    protocol: Protocol, expose_error_body: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(protocol), monkeypatch)
    provider = _provider(fixture.policy)
    provider._expose_error_body = expose_error_body
    payload = _payload(fixture.policy)
    if protocol == "openai_compat":
        payload["choices"][0]["message"]["content"] = _SECRET
    else:
        # Neither JSON nor an individual part includes the complete secret.
        payload["content"] = [{"type": "text", "text": _SECRET[:9]},
                              {"type": "text", "text": _SECRET[9:]}]
    fixture.respond = lambda request: httpx.Response(200, json=payload)
    with pytest.raises((gate.CanonicalHttpRefused, ProviderError)) as failure:
        fixture.execute(provider)
    assert _SECRET not in str(failure.value)
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
@pytest.mark.parametrize("field", ["rendered_text", "claim_text"])
@pytest.mark.parametrize("fenced", [False, True])
def test_structured_answer_decoding_cannot_reconstruct_secret(
    protocol: Protocol, field: str, fenced: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(protocol), monkeypatch)
    escaped = "".join(f"\\u{ord(char):04x}" for char in _SECRET)
    text = ('{"rendered_text":"' + escaped + '","claims":[]}' if field == "rendered_text"
            else '{"rendered_text":"Safe answer","claims":[{"text":"' + escaped + '"}]}')
    if fenced:
        text = "Answer follows. ```json\n" + text + "\n```"
    payload = _payload(fixture.policy)
    if protocol == "openai_compat":
        payload["choices"][0]["message"]["content"] = text
    else:
        payload["content"] = [{"type": "text", "text": text}]
    fixture.respond = lambda request: httpx.Response(200, json=payload)
    with pytest.raises(gate.CanonicalHttpRefused, match="response_secret_reflection"):
        fixture.execute()
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
def test_structured_answer_scan_refuses_excessive_ambiguous_objects(protocol, monkeypatch):
    fixture = ExchangeFixture(_policy(protocol), monkeypatch)
    payload = _payload(fixture.policy)
    if protocol == "openai_compat":
        payload["choices"][0]["message"]["content"] = "{" * 64 + "}" * 64
    else:
        payload["content"] = [{"type": "text", "text": "{" * 64 + "}" * 64}]
    fixture.respond = lambda request: httpx.Response(200, json=payload)
    with pytest.raises(gate.CanonicalHttpRefused, match="structured_response_decode_limit"):
        fixture.execute()
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
def test_response_header_secret_does_not_become_result_metadata(
    protocol: Protocol, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(protocol), monkeypatch)
    fixture.respond = lambda request: httpx.Response(
        200, json=_payload(fixture.policy), headers={"x-request-id": _SECRET},
    )
    exchange = fixture.execute()
    assert exchange.parsed.text == ("answer" if protocol == "openai_compat" else "first second")
    assert exchange.parsed.request_id is None and exchange.parsed.extra == {}
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("protocol", ["openai_compat", "anthropic"])
def test_verified_overrun_returns_full_usage_for_accounting_without_clamping(
    protocol: Protocol, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = ExchangeFixture(_policy(protocol), monkeypatch)
    payload = _payload(fixture.policy)
    if protocol == "openai_compat":
        payload["usage"] = {"prompt_tokens": 1_000_000, "completion_tokens": 2_000_000,
                            "total_tokens": 3_000_000}
    else:
        payload["usage"] = {"input_tokens": 1_000_000, "output_tokens": 2_000_000}
    fixture.respond = lambda request: httpx.Response(200, json=payload)
    exchange = fixture.execute()
    assert exchange.input_tokens == 1_000_000 and exchange.output_tokens == 2_000_000
    assert exchange.cost_micro_usd == 18_000_000
    assert exchange.cost_micro_usd > fixture.policy.reserved_cents * 10_000
    assert len(fixture.claims) == len(fixture.requests) == 1


@pytest.mark.parametrize("excess", [0, 1])
def test_response_two_mib_transport_cap_and_stream_close(
    excess: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy()
    payload_bytes = json.dumps(_payload(policy)).encode()

    class ResponseStream(httpx.SyncByteStream):
        closed = False

        def __iter__(self) -> Iterator[bytes]:
            yield payload_bytes + b" " * (1024 * 1024 - len(payload_bytes))
            yield b" " * (1024 * 1024 + excess)

        def close(self) -> None:
            self.closed = True

    fixture = ExchangeFixture(policy, monkeypatch)
    stream = ResponseStream()
    fixture.respond = lambda request: httpx.Response(200, stream=stream)
    if excess:
        with pytest.raises(gate.CanonicalHttpRefused, match="response_body_limit"):
            fixture.execute()
    else:
        exchange = fixture.execute()
        assert exchange.parsed.text == "answer" and exchange.cost_micro_usd == 38
    assert stream.closed and len(fixture.claims) == len(fixture.requests) == 1

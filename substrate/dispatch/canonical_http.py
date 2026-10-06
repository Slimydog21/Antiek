"""Private, single-exchange HTTP for an independently admitted owner request."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal

import httpx

from substrate.dispatch.base import RawProviderResponse, response_contains_secret
from substrate.dispatch.providers.anthropic import AnthropicProvider
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider

_RESPONSE_LIMIT = 2 * 1024 * 1024
_TIMEOUT_SECONDS = 120.0
_PROTOCOL_VERSION = "owned-canonical-http.v1"
_ANSWER_DECODE_ATTEMPTS = 32


class CanonicalHttpRefused(RuntimeError):
    """No request was delegated, or response evidence was unusable."""


class CanonicalClaimLost(CanonicalHttpRefused):
    """The final durable claim belongs to another worker."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode()).hexdigest()


def _reject_constant(_value: str) -> None:
    raise CanonicalHttpRefused("nonfinite_json")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalHttpRefused("duplicate_json_key")
        result[key] = value
    return result


def _strict_json(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise CanonicalHttpRefused("invalid_json") from None
    if type(value) is not dict:
        raise CanonicalHttpRefused("invalid_json_object")
    _finite_json(value)
    return value


def _finite_json(value: object) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is float and not math.isfinite(item):
            raise CanonicalHttpRefused("nonfinite_json")
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)


def _same_json(actual: object, expected: object) -> bool:
    # Python equality equates false with zero. Wire authorization does not.
    if type(actual) is not type(expected):
        return False
    if type(actual) is dict and type(expected) is dict:
        return (actual.keys() == expected.keys()
                and all(_same_json(actual[key], expected[key]) for key in actual))
    if type(actual) is list and type(expected) is list:
        return (len(actual) == len(expected)
                and all(_same_json(left, right) for left, right in zip(actual, expected, strict=True)))
    return bool(actual == expected)


@dataclass(frozen=True, slots=True)
class AdmittedCanonicalPolicy:
    protocol: Literal["openai_compat", "anthropic"]
    provider_id: str
    catalog_model: str
    wire_model: str
    endpoint: str
    prompt: str = field(repr=False)
    output_limit: int
    temperature: float | None
    thinking: Literal["disabled"] | None
    input_rate: Decimal
    output_rate: Decimal
    price_snapshot: str
    credential_fingerprint: str
    registration_generation: int
    version: str = _PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if (self.protocol not in {"openai_compat", "anthropic"}
            or self.version != _PROTOCOL_VERSION
            or type(self.output_limit) is not int or not 1 <= self.output_limit <= 16_000
            or type(self.registration_generation) is not int
            or self.registration_generation < 1
            or not self.prompt
            or not self.input_rate.is_finite() or self.input_rate <= 0
            or not self.output_rate.is_finite() or self.output_rate <= 0
            or (self.temperature is not None and (
                type(self.temperature) is not float or not math.isfinite(self.temperature)
            ))):
            raise CanonicalHttpRefused("unsupported_policy")
        url = httpx.URL(self.endpoint)
        if (url.scheme != "https" or url.userinfo or url.query or url.fragment
            or url.port not in (None, 443) or str(url) != self.endpoint):
            raise CanonicalHttpRefused("unsupported_endpoint")

    @property
    def input_limit(self) -> int:
        # A local conservative reservation includes the message framing. It
        # does not certify the upstream tokenizer or provider billing limit.
        return len(self.prompt.encode("utf-8")) + len(self.wire_model.encode()) + 64

    @property
    def reserved_cents(self) -> int:
        return int(((self.input_rate * self.input_limit
                     + self.output_rate * self.output_limit) * 100)
                   .to_integral_value(rounding=ROUND_CEILING))

    def expected_body(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "model": self.wire_model, "max_tokens": self.output_limit,
            "messages": [{"role": "user", "content": self.prompt}],
        }
        if self.temperature is not None:
            value["temperature"] = self.temperature
        if self.thinking is not None:
            value["thinking"] = {"type": self.thinking}
        return value

    def _identity(self, *, include_generation: bool) -> dict[str, object]:
        value: dict[str, object] = {
            "version": self.version, "protocol": self.protocol,
            "provider_id": self.provider_id, "catalog_model": self.catalog_model,
            "wire_model": self.wire_model, "endpoint": self.endpoint,
            "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
            "output_limit": self.output_limit, "input_limit": self.input_limit,
            "temperature": self.temperature, "thinking": self.thinking,
            "input_rate": str(self.input_rate), "output_rate": str(self.output_rate),
            "price_snapshot": self.price_snapshot,
            "credential_fingerprint": self.credential_fingerprint,
        }
        if include_generation:
            value["registration_generation"] = self.registration_generation
        return value

    def input_digest(self) -> str:
        """Bind durable inputs without making a worker lease a replay identity."""
        return _digest(self._identity(include_generation=False))

    def digest(self) -> str:
        return _digest(self._identity(include_generation=True))


@dataclass(frozen=True, slots=True)
class CanonicalExchange:
    parsed: RawProviderResponse = field(repr=False)
    input_tokens: int
    output_tokens: int
    cost_micro_usd: int
    request_digest: str
    response_digest: str
    claim_nonce_digest: str
    provider_response_id: str


def _wire_digest(
    policy: AdmittedCanonicalPolicy, request: httpx.Request, body: bytes,
) -> str:
    headers = [(key.decode("ascii").lower(), value.decode("ascii"))
               for key, value in request.headers.raw]
    sanitized = [(key, policy.credential_fingerprint if key in {
        "authorization", "x-api-key",
    } else value) for key, value in headers]
    return _digest({
        "version": policy.version, "policy_digest": policy.digest(),
        "method": request.method, "url": str(request.url),
        "headers": sorted(sanitized), "body_sha256": hashlib.sha256(body).hexdigest(),
        "transport": "http1-only/no-proxy/no-retry/no-redirect/no-env/v1",
    })


def _validate_request(
    policy: AdmittedCanonicalPolicy, request: httpx.Request, secret: str,
) -> tuple[bytes, str]:
    if (type(request) is not httpx.Request or request.method != "POST"
        or str(request.url) != policy.endpoint or type(request.stream) is not httpx.ByteStream):
        raise CanonicalHttpRefused("request_shape_changed")
    body = request.content
    if len(body) > 2 * len(policy.prompt.encode()) + 32_768:
        raise CanonicalHttpRefused("request_body_limit")
    decoded = _strict_json(body)
    if not _same_json(decoded, policy.expected_body()):
        raise CanonicalHttpRefused("request_body_changed")
    headers: dict[bytes, bytes] = {}
    for key, value in request.headers.raw:
        normalized = key.lower()
        if normalized in headers:
            raise CanonicalHttpRefused("duplicate_header")
        headers[normalized] = value
    expected = {
        b"host": request.url.netloc,
        b"accept": b"application/json", b"accept-encoding": b"identity",
        b"connection": b"keep-alive", b"user-agent": b"Antiek-OwnedCanonical/1",
        b"content-type": b"application/json", b"content-length": str(len(body)).encode(),
    }
    if policy.protocol == "openai_compat":
        expected[b"authorization"] = b"Bearer " + secret.encode()
    else:
        expected[b"x-api-key"] = secret.encode()
        expected[b"anthropic-version"] = b"2023-06-01"
    if set(headers) != set(expected) or any(
        not hmac.compare_digest(headers[key], value) for key, value in expected.items()
    ):
        raise CanonicalHttpRefused("request_headers_changed")
    if request.extensions != {
        "timeout": {key: _TIMEOUT_SECONDS for key in ("connect", "read", "write", "pool")},
    }:
        raise CanonicalHttpRefused("request_extensions_changed")
    return body, _wire_digest(policy, request, body)


def _new_inner_transport() -> httpx.BaseTransport:
    return httpx.HTTPTransport(http1=True, http2=False, retries=0, trust_env=False)


class _FinalRequestGate(httpx.BaseTransport):
    def __init__(
        self, policy: AdmittedCanonicalPolicy, secret: str,
        claim: Callable[[str], str],
    ) -> None:
        self.policy = policy
        self.policy_digest = policy.digest()
        self.secret = secret
        self.claim = claim
        self.inner = _new_inner_transport()
        self.request_digest: str | None = None
        self.response_digest: str | None = None
        self.nonce: str | None = None
        self.entered = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.entered:
            raise CanonicalHttpRefused("second_exchange")
        self.entered = True
        if self.policy.digest() != self.policy_digest:
            raise CanonicalHttpRefused("policy_changed")
        body, original_digest = _validate_request(self.policy, request, self.secret)
        snapshot = httpx.Request(
            request.method, request.url, headers=list(request.headers.raw), content=body,
            extensions={"timeout": dict(request.extensions["timeout"])},
        )
        _, final_digest = _validate_request(self.policy, snapshot, self.secret)
        if original_digest != final_digest:
            raise CanonicalHttpRefused("snapshot_changed")
        # The callback validates current guarded authority and claims the
        # original allocation. Every guard releases before delegation below.
        self.nonce = self.claim(final_digest)
        if type(self.nonce) is not str or len(self.nonce) != 64 or any(
            character not in "0123456789abcdef" for character in self.nonce
        ):
            raise CanonicalHttpRefused("claim_evidence_invalid")
        self.request_digest = final_digest
        response = self.inner.handle_request(snapshot)
        try:
            if response.headers.get("content-encoding", "identity") != "identity":
                raise CanonicalHttpRefused("response_encoding")
            pieces: list[bytes] = []
            count = 0
            if not isinstance(response.stream, httpx.SyncByteStream):
                raise CanonicalHttpRefused("response_stream_changed")
            for chunk in response.stream:
                count += len(chunk)
                if count > _RESPONSE_LIMIT:
                    raise CanonicalHttpRefused("response_body_limit")
                pieces.append(chunk)
            content = b"".join(pieces)
            self.response_digest = hashlib.sha256(content).hexdigest()
            return httpx.Response(response.status_code, headers=response.headers,
                                  content=content, extensions=response.extensions)
        finally:
            response.close()

    def close(self) -> None:
        self.inner.close()


def _count(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key)
    if type(value) is not int or not 0 <= value <= (1 << 31) - 1:
        raise CanonicalHttpRefused("response_usage_unknown")
    return value


def _structured_answer_contains_secret(text: str, secret: str) -> bool:
    """Check the caller's one JSON-object decoding before retaining an answer."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json\n"):
            text = text[5:]
        elif text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    attempts = 0
    while start != -1:
        end = text.rfind("}")
        while end > start:
            if attempts >= _ANSWER_DECODE_ATTEMPTS:
                raise CanonicalHttpRefused("structured_response_decode_limit")
            attempts += 1
            try:
                value = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                end = text.rfind("}", start, end)
            except RecursionError:
                raise CanonicalHttpRefused("structured_response_decode_limit") from None
            else:
                if type(value) is dict:
                    return (response_contains_secret(value, secret)
                            or secret in str(value.get("rendered_text", "")))
                break
        start = text.find("{", start + 1)
    return False


def validate_owned_response_text(text: str, secret: str) -> None:
    """Validate both a fresh answer and retained text before caller decoding."""
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise CanonicalHttpRefused("response_text_limit")
    if secret in text or _structured_answer_contains_secret(text, secret):
        raise CanonicalHttpRefused("response_secret_reflection")


def _response_facts(
    policy: AdmittedCanonicalPolicy, response: httpx.Response, secret: str,
) -> tuple[int, int, str]:
    if response.status_code != 200:
        raise CanonicalHttpRefused("response_status")
    data = _strict_json(response.content)
    if response_contains_secret(data, secret) or secret in response.text:
        raise CanonicalHttpRefused("response_secret_reflection")
    if data.get("model") != policy.wire_model:
        raise CanonicalHttpRefused("response_model_changed")
    response_id = data.get("id")
    usage = data.get("usage")
    if (type(response_id) is not str or not response_id or len(response_id) > 256
        or type(usage) is not dict):
        raise CanonicalHttpRefused("response_identity_unknown")
    if policy.protocol == "openai_compat":
        if set(data) - {"id", "object", "created", "model", "choices", "usage", "system_fingerprint", "service_tier"}:
            raise CanonicalHttpRefused("unsupported_response_fields")
        if ("created" in data and (type(data["created"]) is not int or data["created"] < 0)):
            raise CanonicalHttpRefused("response_identity_unknown")
        if data.get("service_tier") not in (None, "default"):
            raise CanonicalHttpRefused("unsupported_billing_dimension")
        if data.get("object") != "chat.completion":
            raise CanonicalHttpRefused("response_protocol_changed")
        choices = data.get("choices")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise CanonicalHttpRefused("response_choices")
        choice = choices[0]
        message = choice.get("message")
        if (type(choice.get("index")) is not int or choice["index"] != 0
            or set(choice) - {"index", "finish_reason", "message", "logprobs"}
            or choice.get("logprobs") is not None
            or choice.get("finish_reason") not in {"stop", "length"}
            or type(message) is not dict or message.get("role") != "assistant"
            or type(message.get("content")) is not str
            or set(message) - {"role", "content"}):
            raise CanonicalHttpRefused("unsupported_response_parts")
        input_tokens = _count(usage, "prompt_tokens")
        output_tokens = _count(usage, "completion_tokens")
        if _count(usage, "total_tokens") != input_tokens + output_tokens:
            raise CanonicalHttpRefused("response_usage_contradiction")
        if set(usage) - {"prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_details", "completion_tokens_details"}:
            raise CanonicalHttpRefused("unsupported_billing_dimension")
        for name, allowed in (("prompt_tokens_details", {"cached_tokens"}),
                              ("completion_tokens_details", {"reasoning_tokens"})):
            if name in usage:
                details = usage[name]
                if type(details) is not dict or set(details) - allowed:
                    raise CanonicalHttpRefused("unsupported_billing_dimension")
                if any(type(value) is not int or value != 0 for value in details.values()):
                    raise CanonicalHttpRefused("unsupported_billing_dimension")
    else:
        if set(data) - {"id", "type", "role", "model", "content", "stop_reason", "stop_sequence", "usage"}:
            raise CanonicalHttpRefused("unsupported_response_fields")
        if data.get("stop_sequence") is not None:
            raise CanonicalHttpRefused("unsupported_response_parts")
        if data.get("type") != "message" or data.get("role") != "assistant":
            raise CanonicalHttpRefused("response_protocol_changed")
        if data.get("stop_reason") not in {"end_turn", "max_tokens"}:
            raise CanonicalHttpRefused("unsupported_response_parts")
        parts = data.get("content")
        if (type(parts) is not list or not parts or any(
            type(part) is not dict or set(part) != {"type", "text"}
            or part["type"] != "text" or type(part["text"]) is not str for part in parts
        )):
            raise CanonicalHttpRefused("unsupported_response_parts")
        input_tokens = _count(usage, "input_tokens")
        output_tokens = _count(usage, "output_tokens")
        if set(usage) - {"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}:
            raise CanonicalHttpRefused("unsupported_billing_dimension")
        if any(_count(usage, key) != 0 for key in (
            "cache_creation_input_tokens", "cache_read_input_tokens",
        ) if key in usage):
            raise CanonicalHttpRefused("unsupported_billing_dimension")
    return input_tokens, output_tokens, response_id


def execute_owned_http(
    policy: AdmittedCanonicalPolicy,
    provider: OpenAICompatProvider | AnthropicProvider,
    secret: str, claim: Callable[[str], str],
) -> CanonicalExchange:
    if not secret:
        raise CanonicalHttpRefused("credential_unavailable")
    started = time.monotonic()
    policy_digest = policy.digest()
    snapshot_policy = replace(policy)
    if ((policy.protocol == "openai_compat" and isinstance(provider, OpenAICompatProvider))
        or (policy.protocol == "anthropic" and isinstance(provider, AnthropicProvider))):
        built = provider.build_request(
            model=policy.catalog_model, prompt=policy.prompt,
            max_tokens=policy.output_limit, temperature=policy.temperature or 0.0,
            api_key=secret,
        )
    else:
        raise CanonicalHttpRefused("provider_protocol_changed")
    if policy.digest() != policy_digest:
        raise CanonicalHttpRefused("policy_changed")
    gate = _FinalRequestGate(snapshot_policy, secret, claim)
    with httpx.Client(
        transport=gate, timeout=_TIMEOUT_SECONDS, trust_env=False, follow_redirects=False,
        http1=True, http2=False,
        headers={"Accept": "application/json", "Accept-Encoding": "identity",
                 "User-Agent": "Antiek-OwnedCanonical/1"},
    ) as client:
        response = client.post(
            built.url, headers=built.headers, json=built.body, timeout=_TIMEOUT_SECONDS,
        )
        input_tokens, output_tokens, response_id = _response_facts(snapshot_policy, response, secret)
        latency = int((time.monotonic() - started) * 1000)
        # Use the shared parser implementation, not an instance override that
        # could replace the text after the private response was validated.
        if snapshot_policy.protocol == "openai_compat" and isinstance(provider, OpenAICompatProvider):
            parsed = OpenAICompatProvider.parse_response(
                provider, response, model=snapshot_policy.wire_model,
                api_key=secret, latency_ms=latency, request_url=snapshot_policy.endpoint,
            )
        elif isinstance(provider, AnthropicProvider):
            parsed = AnthropicProvider.parse_response(
                provider, response, model=snapshot_policy.wire_model,
                api_key=secret, latency_ms=latency,
            )
        else:
            raise CanonicalHttpRefused("provider_protocol_changed")
        validate_owned_response_text(parsed.text, secret)
        parsed = replace(parsed, request_id=None, extra={})
        if gate.request_digest is None or gate.response_digest is None or gate.nonce is None:
            raise CanonicalHttpRefused("exchange_evidence_missing")
        cost = (snapshot_policy.input_rate * input_tokens
                + snapshot_policy.output_rate * output_tokens) * 1_000_000
        return CanonicalExchange(
            parsed, input_tokens, output_tokens,
            int(cost.to_integral_value(rounding=ROUND_CEILING)),
            gate.request_digest, gate.response_digest, gate.nonce, response_id,
        )

"""Unmounted, one-use audio HTTP protocol; no payer or route admission."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import math
import re
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from acquisition.voice.audio_bound import NormalizedAudio
from acquisition.voice.audio_cost import QualifiedAudioTariff
from acquisition.voice.audio_request import (
    MAX_REQUEST_BYTES,
    PreparedAudioRequest,
    validate_audio_request,
)
from runtime.research_runner.audio_provider_catalog import AudioModelDescriptor

PROTOCOL = "owned-canonical-audio-http.v1"
TIMEOUT_SECONDS = 120.0
RESPONSE_LIMIT = 2 * 1024 * 1024
_TRANSPORT = "http1/no-proxy/no-env/no-redirect/no-retry/v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _sha_shape(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True)
class AudioCredential:
    """Explicit in-memory material, not a credential-store or owner decision."""

    secret: str = field(repr=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.secret) is not str
            or not self.secret
            or any(not 33 <= ord(character) <= 126 for character in self.secret)
        ):
            raise ValueError("credential_invalid")
        object.__setattr__(self, "fingerprint", _sha(self.secret.encode("ascii")))


@dataclass(frozen=True, slots=True)
class CanonicalAudioPolicy:
    prepared: PreparedAudioRequest = field(repr=False)
    audio: NormalizedAudio = field(repr=False)
    capability: AudioModelDescriptor
    tariff: QualifiedAudioTariff
    now: datetime
    credential_fingerprint: str
    language: str | None = None
    version: str = PROTOCOL
    timeout_seconds: float = TIMEOUT_SECONDS
    response_limit: int = RESPONSE_LIMIT
    request_limit: int = MAX_REQUEST_BYTES

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != PROTOCOL
            or type(self.timeout_seconds) is not float
            or self.timeout_seconds != TIMEOUT_SECONDS
            or type(self.response_limit) is not int
            or self.response_limit != RESPONSE_LIMIT
            or type(self.request_limit) is not int
            or self.request_limit != MAX_REQUEST_BYTES
            or not _sha_shape(self.credential_fingerprint)
        ):
            raise ValueError("policy_invalid")
        validate_audio_request(
            self.prepared,
            self.audio,
            self.capability,
            self.tariff,
            now=self.now,
            language=self.language,
        )

    def digest(self) -> str:
        self.__post_init__()
        return _digest(
            {
                "version": self.version,
                "body_sha256": self.prepared.body_sha256,
                "byte_count": self.prepared.byte_count,
                "audio_binding_sha256": self.prepared.quote.audio_binding_sha256,
                "capability": asdict(self.capability),
                "tariff_sha256": self.tariff.digest,
                "now": self.now.isoformat(),
                "language": self.language,
                "credential_fingerprint": self.credential_fingerprint,
                "request_limit": self.request_limit,
                "response_limit": self.response_limit,
                "timeout_seconds": self.timeout_seconds,
                "transport": _TRANSPORT,
            }
        )


@dataclass(frozen=True, slots=True)
class AudioHttpEvidence:
    wire_digest: str | None = None
    response_digest: str | None = None
    claim_nonce_digest: str | None = None
    claim_attempted: bool = False
    claim_won: bool = False
    delegated: bool = False
    response_retired: bool | None = None
    client_retired: bool | None = None
    transport_retired: bool | None = None
    route_blocked: bool = False
    no_retry: bool = True
    protocol: str = PROTOCOL


class AudioHttpRefused(RuntimeError):
    """Value-free pre-delegation refusal; not a refund or retry decision."""

    def __init__(self, code: str, evidence: AudioHttpEvidence | None = None) -> None:
        self.code = code
        self.evidence = evidence or AudioHttpEvidence()
        super().__init__(code)


class AudioHttpAmbiguous(AudioHttpRefused):
    """A winning claim exists; funds/outcome require separate reconciliation."""


@dataclass(frozen=True, slots=True)
class CanonicalAudioExchange:
    transcript: str = field(repr=False)
    language: str | None
    provider_duration_seconds: int | float | None
    provider_usage_seconds: int | float | None
    evidence: AudioHttpEvidence


def _freeze(policy: CanonicalAudioPolicy) -> CanonicalAudioPolicy:
    if type(policy) is not CanonicalAudioPolicy:
        raise ValueError("policy_invalid")
    frozen = copy.deepcopy(policy)
    frozen.__post_init__()
    return frozen


def _credential(credential: AudioCredential, policy: CanonicalAudioPolicy) -> str:
    if type(credential) is not AudioCredential:
        raise ValueError("credential_invalid")
    validated = AudioCredential(credential.secret)
    if not hmac.compare_digest(
        validated.fingerprint, credential.fingerprint
    ) or not hmac.compare_digest(validated.fingerprint, policy.credential_fingerprint):
        raise ValueError("credential_invalid")
    return validated.secret


def _extensions() -> dict[str, object]:
    return {"timeout": {key: TIMEOUT_SECONDS for key in ("connect", "read", "write", "pool")}}


def _headers(policy: CanonicalAudioPolicy, secret: str) -> dict[str, str]:
    return {
        "Host": "api.openai.com",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "User-Agent": "Antiek-OwnedCanonicalAudio/1",
        "Content-Type": policy.prepared.content_type,
        "Content-Length": str(policy.prepared.byte_count),
        "Authorization": "Bearer " + secret,
    }


def _build_request(policy: CanonicalAudioPolicy, secret: str) -> httpx.Request:
    return httpx.Request(
        "POST",
        "https://api.openai.com/v1/audio/transcriptions",
        headers=_headers(policy, secret),
        content=policy.prepared.body,
        extensions=_extensions(),
    )


def _wire(policy: CanonicalAudioPolicy, request: httpx.Request, secret: str) -> str:
    if (
        type(request) is not httpx.Request
        or request.method != "POST"
        or str(request.url) != "https://api.openai.com/v1/audio/transcriptions"
        or type(request.stream) is not httpx.ByteStream
    ):
        raise ValueError("request_invalid")
    body = request.content
    if type(body) is not bytes or len(body) > MAX_REQUEST_BYTES or body != policy.prepared.body:
        raise ValueError("request_invalid")
    chunks = tuple(request.stream)
    if len(chunks) != 1 or type(chunks[0]) is not bytes or chunks[0] != body:
        raise ValueError("request_invalid")
    headers: dict[str, str] = {}
    for key, value in request.headers.raw:
        name = key.decode("ascii").lower()
        if name in headers:
            raise ValueError("request_invalid")
        headers[name] = value.decode("ascii")
    expected = {key.lower(): value for key, value in _headers(policy, secret).items()}
    if headers != expected:
        raise ValueError("request_invalid")
    if request.extensions != _extensions() or type(request.extensions.get("timeout")) is not dict:
        raise ValueError("request_invalid")
    timeout = request.extensions["timeout"]
    if any(type(value) is not float for value in timeout.values()):
        raise ValueError("request_invalid")
    sanitized = {
        key: policy.credential_fingerprint if key == "authorization" else value
        for key, value in headers.items()
    }
    return _digest(
        {
            "protocol": PROTOCOL,
            "policy_digest": policy.digest(),
            "method": request.method,
            "url": str(request.url),
            "headers": sanitized,
            "extensions": _extensions(),
            "body_sha256": _sha(body),
            "transport": _TRANSPORT,
        }
    )


def _new_inner_transport() -> httpx.BaseTransport:
    return httpx.HTTPTransport(http1=True, http2=False, retries=0, trust_env=False)


def _retirement(inner: httpx.BaseTransport) -> Callable[[], None]:
    closer = inner.close
    attempted = retired = False

    def close() -> None:
        nonlocal attempted, retired
        if attempted:
            if not retired:
                raise ValueError("transport_retirement_unconfirmed")
            return
        attempted = True
        closer()
        retired = True

    return close


class _FinalAudioGate(httpx.BaseTransport):
    def __init__(
        self,
        policy: CanonicalAudioPolicy,
        secret: str,
        claim: Callable[[str], str],
        inner: httpx.BaseTransport,
        retire: Callable[[], None] | None = None,
    ) -> None:
        self._policy = _freeze(policy)
        self._policy_digest = self._policy.digest()
        self._secret = secret
        self._claim = claim
        self._inner = inner
        self._retire = _retirement(inner) if retire is None else retire
        self._lock = threading.Lock()
        self._entered = False
        self.wire_digest: str | None = None
        self.response_digest: str | None = None
        self.nonce_digest: str | None = None
        self.claim_attempted = False
        self.claim_won = False
        self.delegated = False
        self.response_retired: bool | None = None

    def evidence(
        self,
        *,
        client: bool | None = None,
        transport: bool | None = None,
        route_blocked: bool = False,
    ) -> AudioHttpEvidence:
        return AudioHttpEvidence(
            self.wire_digest,
            self.response_digest,
            self.nonce_digest,
            self.claim_attempted,
            self.claim_won,
            self.delegated,
            self.response_retired,
            client,
            transport,
            route_blocked,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            if self._entered:
                raise AudioHttpRefused("second_exchange", self.evidence())
            self._entered = True
        failure = False
        try:
            policy = _freeze(self._policy)
            if policy.digest() != self._policy_digest:
                raise ValueError("policy_invalid")
            secret, claim, delegate = self._secret, self._claim, self._inner.handle_request
            response_limit = policy.response_limit
            original_digest = _wire(policy, request, secret)
            snapshot = httpx.Request(
                request.method,
                request.url,
                headers=list(request.headers.raw),
                content=bytes(request.content),
                extensions=_extensions(),
            )
            final_digest = _wire(policy, snapshot, secret)
            if final_digest != original_digest:
                raise ValueError("snapshot_invalid")
        except BaseException:
            failure = True
        if failure:
            raise AudioHttpRefused("request_or_policy_invalid", self.evidence())
        self.wire_digest = final_digest
        self.claim_attempted = True
        nonce: object = None
        try:
            nonce = claim(final_digest)
        except BaseException:
            failure = True
        if failure or not _sha_shape(nonce):
            raise AudioHttpRefused("claim_refused", self.evidence())
        assert isinstance(nonce, str)
        self.nonce_digest = _sha(nonce.encode("ascii"))
        self.claim_won = True
        self.delegated = True  # Invocation boundary, not proof of provider receipt.
        response: httpx.Response | None = None
        content: bytes | None = None
        status: int | None = None
        code = "transport_outcome_unknown"
        retire_response: Callable[[], None] | None = None
        try:
            response = delegate(snapshot)
            retire_response = response.close
            if not isinstance(response, httpx.Response) or not isinstance(
                response.stream, httpx.SyncByteStream
            ):
                raise ValueError("response_invalid")
            encoding = response.headers.get_list("content-encoding")
            if encoding not in ([], ["identity"]):
                code = "response_encoding"
                raise ValueError("response_invalid")
            content_types = response.headers.get_list("content-type")
            if (
                len(content_types) != 1
                or content_types[0].split(";", 1)[0].strip().lower() != "application/json"
            ):
                code = "response_content_type"
                raise ValueError("response_invalid")
            lengths = response.headers.get_list("content-length")
            if lengths and (
                len(lengths) != 1
                or re.fullmatch(r"[0-9]+", lengths[0]) is None
                or int(lengths[0]) > response_limit
            ):
                code = "response_size"
                raise ValueError("response_invalid")
            pieces: list[bytes] = []
            count = 0
            for chunk in response.stream:
                if type(chunk) is not bytes or not chunk or count + len(chunk) > response_limit:
                    code = "response_size"
                    raise ValueError("response_invalid")
                count += len(chunk)
                pieces.append(chunk)
            if lengths and int(lengths[0]) != count:
                code = "response_size"
                raise ValueError("response_invalid")
            content = b"".join(pieces)
            self.response_digest = _sha(content)
            status = response.status_code
        except BaseException:
            failure = True
        finally:
            if retire_response is not None:
                self.response_retired = False
                try:
                    retire_response()
                    self.response_retired = True
                except BaseException:
                    code, failure = "response_retirement_unconfirmed", True
        if failure or content is None or status is None:
            raise AudioHttpAmbiguous(code, self.evidence())
        return httpx.Response(status, content=content, headers={"Content-Type": "application/json"})

    def close(self) -> None:
        self._retire()


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("response_invalid")
        result[key] = value
    return result


def _constant(_value: str) -> Any:
    raise ValueError("response_invalid")


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value.encode("utf-8", "strict")
        return [value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("response_invalid")
    if isinstance(value, dict):
        return [
            text for key, item in value.items() for part in (key, item) for text in _strings(part)
        ]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _number(value: object) -> int | float:
    if (
        type(value) not in (int, float)
        or not isinstance(value, (int, float))
        or value < 0
        or not math.isfinite(value)
    ):
        raise ValueError("response_invalid")
    return value


def _response(
    response: httpx.Response, secret: str
) -> tuple[str, str | None, int | float | None, int | float | None]:
    if response.status_code != 200:
        raise ValueError("provider_refused")
    parsed = json.loads(
        response.content.decode("utf-8", "strict"),
        object_pairs_hook=_unique,
        parse_constant=_constant,
    )
    if type(parsed) is not dict or type(parsed.get("text")) is not str:
        raise ValueError("response_invalid")
    strings = _strings(parsed)
    variants = {
        secret,
        quote(secret, safe=""),
        secret.encode().hex(),
        base64.b64encode(secret.encode()).decode(),
    }
    joined = "".join(strings)
    if any(variant in joined for variant in variants):
        raise ValueError("secret_echo")
    text: str = parsed["text"]
    if len(text.encode()) > RESPONSE_LIMIT:
        raise ValueError("response_invalid")
    language = parsed.get("language")
    if language is not None and type(language) is not str:
        raise ValueError("response_invalid")
    duration = _number(parsed["duration"]) if "duration" in parsed else None
    usage = None
    if "usage" in parsed:
        value = parsed["usage"]
        if (
            type(value) is not dict
            or set(value) != {"type", "seconds"}
            or value["type"] != "duration"
        ):
            raise ValueError("response_invalid")
        usage = _number(value["seconds"])
    if "model" in parsed and parsed["model"] != "whisper-1":
        raise ValueError("response_invalid")
    return text, language, duration, usage


def execute_audio_http(
    policy: CanonicalAudioPolicy, credential: AudioCredential, claim: Callable[[str], str]
) -> CanonicalAudioExchange:
    """One private exchange. The caller still owns real final admission and settlement."""
    failure = False
    try:
        frozen = _freeze(policy)
        secret = _credential(credential, frozen)
        if not callable(claim):
            raise ValueError("claim_required")
    except BaseException:
        failure = True
    if failure:
        raise AudioHttpRefused("policy_or_credential_invalid")
    inner: httpx.BaseTransport | None = None
    client: httpx.Client | None = None
    response: httpx.Response | None = None
    gate: _FinalAudioGate | None = None
    close_inner: Callable[[], None] | None = None
    close_client: Callable[[], None] | None = None
    retired_client: bool | None = None
    retired_transport: bool | None = None
    result: tuple[str, str | None, int | float | None, int | float | None] | None = None
    code, route_blocked = "exchange_failed", False
    try:
        inner = _new_inner_transport()
        close_inner = _retirement(inner)
        gate = _FinalAudioGate(frozen, secret, claim, inner, close_inner)
        # Client owns the gate, while the captured inner closer also retires its
        # original handle if a callback replaces gate attributes or client close fails.
        client = httpx.Client(
            transport=gate,
            timeout=TIMEOUT_SECONDS,
            trust_env=False,
            follow_redirects=False,
            http1=True,
            http2=False,
        )
        close_client = client.close
        response = client.send(_build_request(frozen, secret), stream=True, follow_redirects=False)
        route_blocked = response.status_code in (401, 402, 403)
        code = "credential_or_billing_refused" if route_blocked else "response_invalid_or_refused"
        result = _response(response, secret)
    except AudioHttpRefused as error:
        code, failure = error.code, True
    except BaseException:
        failure = True
    finally:
        if response is not None:
            try:
                response.close()
            except BaseException:
                code, failure = "client_response_retirement_unconfirmed", True
        if close_client is not None:
            retired_client = False
            try:
                close_client()
                retired_client = True
            except BaseException:
                code, failure = "client_retirement_unconfirmed", True
        if close_inner is not None:
            retired_transport = False
            try:
                close_inner()
                retired_transport = True
            except BaseException:
                code, failure = "transport_retirement_unconfirmed", True
    evidence = (
        gate.evidence(
            client=retired_client, transport=retired_transport, route_blocked=route_blocked
        )
        if gate
        else AudioHttpEvidence(client_retired=retired_client, transport_retired=retired_transport)
    )
    if failure or result is None:
        error_type = AudioHttpAmbiguous if evidence.claim_won else AudioHttpRefused
        raise error_type(code, evidence)
    return CanonicalAudioExchange(*result, evidence)

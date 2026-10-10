"""Real gate controls with synthetic PCM, policy, key and injected no-network transport."""

from __future__ import annotations

import copy
import hashlib
import json
import struct
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from fractions import Fraction
from typing import cast

import httpx
import pytest

from acquisition.voice.audio_bound import DecodeFacts, NormalizedAudio
from acquisition.voice.audio_cost import QualifiedAudioTariff
from acquisition.voice.audio_request import prepare_audio_request
from runtime.research_runner.audio_provider_catalog import WHISPER_TRANSCRIPTION
from substrate.dispatch import canonical_audio_http as audio

SECRET = "synthetic-asr-transport-control-key"
NONCE = hashlib.sha256(b"synthetic winning claim evidence").hexdigest()
NOW = datetime(2026, 10, 10, tzinfo=UTC)
SUCCESS = b'{"text":"Useful synthetic transcript","language":"english","duration":1.25}'


def _policy() -> audio.CanonicalAudioPolicy:
    pcm = b"\x01\x00\x02\x00\x03\x00\x04\x00"
    wav = (
        struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            len(pcm) + 36,
            b"WAVE",
            b"fmt ",
            16,
            1,
            1,
            16000,
            32000,
            2,
            16,
            b"data",
            len(pcm),
        )
        + pcm
    )

    def sha(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    facts = DecodeFacts(
        len(wav),
        len(pcm),
        0,
        sha(b""),
        True,
        True,
        0,
        False,
        False,
        True,
        True,
        True,
        0.25,
        "darwin_local_cpu_only_linux_memory_unproved",
    )
    normalized = NormalizedAudio(wav, sha(wav), len(wav), sha(wav), sha(pcm), len(pcm), 4, facts)
    capability = copy.deepcopy(WHISPER_TRANSCRIPTION)
    tariff = QualifiedAudioTariff(
        capability,
        "USD",
        Fraction(3, 500),
        Fraction(60),
        Fraction(1),
        Fraction(1),
        "synthetic-transport-control-v1",
        sha(b"synthetic tariff qualification"),
        True,
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 11, 1, tzinfo=UTC),
    )
    prepared = prepare_audio_request(normalized, capability, tariff, now=NOW, language="en")
    return audio.CanonicalAudioPolicy(
        prepared, normalized, capability, tariff, NOW, sha(SECRET.encode()), language="en"
    )


class TrackedStream(httpx.SyncByteStream):
    def __init__(
        self, chunks: tuple[bytes, ...], *, read_failure: bool = False, close_failure: bool = False
    ) -> None:
        self.chunks = chunks
        self.read_failure = read_failure
        self.close_failure = close_failure
        self.closes = 0

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks
        if self.read_failure:
            raise RuntimeError(SECRET)

    def close(self) -> None:
        self.closes += 1
        if self.close_failure:
            raise RuntimeError(SECRET)


class FakeTransport(httpx.BaseTransport):
    def __init__(
        self,
        body: bytes = SUCCESS,
        *,
        status: int = 200,
        headers: list[tuple[str, str]] | None = None,
        stream: TrackedStream | None = None,
        failure: bool = False,
        close_failure: bool = False,
    ) -> None:
        self.status = status
        self.headers = [("Content-Type", "application/json")] if headers is None else headers
        self.stream = TrackedStream((body,)) if stream is None else stream
        self.failure = failure
        self.close_failure = close_failure
        self.requests: list[httpx.Request] = []
        self.closes = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure:
            raise RuntimeError(SECRET)
        return httpx.Response(
            self.status, headers=self.headers, stream=self.stream, request=request
        )

    def close(self) -> None:
        self.closes += 1
        if self.close_failure:
            raise RuntimeError(SECRET)


def _install(monkeypatch: pytest.MonkeyPatch, inner: FakeTransport) -> None:
    monkeypatch.setattr(audio, "_new_inner_transport", lambda: inner)


def _claim(log: list[str]) -> Callable[[str], str]:
    def claim(digest: str) -> str:
        assert not log
        log.append(digest)
        return NONCE

    return claim


def _error(exc: audio.AudioHttpRefused) -> None:
    assert SECRET not in str(exc) and SECRET not in repr(exc.evidence)
    assert exc.__context__ is None
    assert exc.evidence.no_retry


def test_exact_positive_claim_precedes_real_delegation_and_private_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy()
    claims: list[str] = []
    inner = FakeTransport()
    _install(monkeypatch, inner)
    original = inner.handle_request

    def checked(request: httpx.Request) -> httpx.Response:
        assert len(claims) == 1
        return original(request)

    monkeypatch.setattr(inner, "handle_request", checked)
    result = audio.execute_audio_http(policy, audio.AudioCredential(SECRET), _claim(claims))
    assert result.transcript == "Useful synthetic transcript"
    assert result.language == "english" and result.provider_duration_seconds == 1.25
    assert result.provider_usage_seconds is None
    assert len(inner.requests) == len(claims) == inner.stream.closes == inner.closes == 1
    request = inner.requests[0]
    assert type(request.stream) is httpx.ByteStream and request.content == policy.prepared.body
    assert str(request.url) == "https://api.openai.com/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer " + SECRET
    assert request.extensions == {
        "timeout": {k: 120.0 for k in ("connect", "read", "write", "pool")}
    }
    assert result.evidence.wire_digest == claims[0]
    assert result.evidence.response_digest == hashlib.sha256(SUCCESS).hexdigest()
    assert result.evidence.claim_nonce_digest == hashlib.sha256(NONCE.encode()).hexdigest()
    assert (
        result.evidence.claim_won and result.evidence.delegated and result.evidence.claim_attempted
    )
    assert (
        result.evidence.response_retired
        and result.evidence.client_retired
        and result.evidence.transport_retired
    )
    receipt = json.dumps(asdict(result.evidence))
    assert SECRET not in receipt and result.transcript not in receipt
    assert SECRET not in repr(audio.AudioCredential(SECRET)) and result.transcript not in repr(
        result
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("body", b"tampered"),
        ("body_sha256", "0" * 64),
        ("byte_count", True),
        ("boundary", "other"),
        ("content_type", "text/plain"),
        ("method", "GET"),
        ("endpoint", "https://evil.invalid"),
        ("request_path", "/other"),
        ("language", "fr"),
    ],
)
def test_reflected_prepared_tamper_refuses_before_any_claim_or_factory(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    policy = _policy()
    calls: list[str] = []
    object.__setattr__(policy.prepared, field, value)

    def factory() -> httpx.BaseTransport:
        calls.append("factory")
        raise AssertionError("not reached")

    monkeypatch.setattr(audio, "_new_inner_transport", factory)
    with pytest.raises(audio.AudioHttpRefused) as caught:
        audio.execute_audio_http(policy, audio.AudioCredential(SECRET), _claim(calls))
    _error(caught.value)
    assert (
        not calls
        and not caught.value.evidence.claim_attempted
        and not caught.value.evidence.delegated
    )


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("policy", "timeout_seconds", 120),
        ("policy", "response_limit", 1),
        ("policy", "request_limit", 1),
        ("policy", "version", "owned-canonical-http.v1"),
        ("policy", "credential_fingerprint", "0" * 64),
        ("policy", "now", datetime(2030, 1, 1, tzinfo=UTC)),
        ("tariff", "digest", "0" * 64),
        ("tariff", "qualified", False),
        ("capability", "model_id", "other"),
        ("audio", "wav_sha256", "0" * 64),
        ("quote", "reserved_cents", 0),
    ],
)
def test_authoritative_policy_and_quote_tamper_refuses_before_send(
    monkeypatch: pytest.MonkeyPatch, target: str, field: str, value: object
) -> None:
    policy = _policy()
    claims: list[str] = []
    targets = {
        "policy": policy,
        "tariff": policy.tariff,
        "capability": policy.capability,
        "audio": policy.audio,
        "quote": policy.prepared.quote,
    }
    object.__setattr__(targets[target], field, value)
    inner = FakeTransport()
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpRefused) as caught:
        audio.execute_audio_http(policy, audio.AudioCredential(SECRET), _claim(claims))
    _error(caught.value)
    assert not claims and not inner.requests


@pytest.mark.parametrize("secret", ["", " ", "key\nvalue", "key\x00value", "clé", "key\x7fvalue"])
def test_credential_validation_precedes_header_construction(secret: str) -> None:
    with pytest.raises(ValueError, match="^credential_invalid$"):
        audio.AudioCredential(secret)


def test_reflected_credential_material_requires_matching_current_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = audio.AudioCredential(SECRET)
    claims: list[str] = []
    object.__setattr__(credential, "secret", "other-control-key")
    inner = FakeTransport()
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpRefused) as caught:
        audio.execute_audio_http(_policy(), credential, _claim(claims))
    _error(caught.value)
    assert not claims and not inner.requests


@pytest.mark.parametrize(
    "mutation",
    [
        "url",
        "method",
        "body",
        "header",
        "duplicate",
        "timeout",
        "extension",
        "stream",
        "stream_bytes",
    ],
)
def test_actual_wire_gate_rejects_mutation_before_claim(mutation: str) -> None:
    policy, inner = _policy(), FakeTransport()
    claims: list[str] = []
    gate = audio._FinalAudioGate(policy, SECRET, _claim(claims), inner)
    request = audio._build_request(policy, SECRET)
    if mutation == "url":
        request.url = httpx.URL("https://api.openai.com/v1/audio/transcriptions?extra=1")
    elif mutation == "method":
        request.method = "GET"
    elif mutation == "body":
        request.__dict__["_content"] = b"changed"
    elif mutation == "header":
        request.headers["X-Unapproved"] = "value"
    elif mutation == "duplicate":
        request.headers = httpx.Headers(
            [*request.headers.raw, (b"Authorization", b"Bearer " + SECRET.encode())]
        )
    elif mutation == "timeout":
        request.extensions["timeout"]["read"] = 120
    elif mutation == "extension":
        request.extensions["trace"] = "not approved"
    elif mutation == "stream_bytes":
        request.stream = httpx.ByteStream(b"different from cached content")
    else:
        request.stream = TrackedStream((policy.prepared.body,))
    try:
        with pytest.raises(audio.AudioHttpRefused) as caught:
            gate.handle_request(request)
        _error(caught.value)
        assert not claims and not inner.requests
    finally:
        gate.close()
    assert inner.closes == 1


def test_synchronous_callback_cannot_replace_request_policy_or_delegation() -> None:
    policy, inner, foreign = _policy(), FakeTransport(), FakeTransport()
    request = audio._build_request(policy, SECRET)
    claims: list[str] = []
    gate: audio._FinalAudioGate

    def claim(digest: str) -> str:
        claims.append(digest)
        request.headers["authorization"] = "Bearer other"
        request.__dict__["_content"] = b"changed"
        request.extensions["timeout"]["read"] = 1.0
        object.__setattr__(policy.tariff, "qualified", False)
        object.__setattr__(gate._policy, "response_limit", 1)
        gate._inner = foreign
        gate._claim = lambda _: "0" * 64
        inner.__dict__["handle_request"] = foreign.handle_request
        return NONCE

    gate = audio._FinalAudioGate(policy, SECRET, claim, inner)
    original_body = policy.prepared.body
    response = gate.handle_request(request)
    try:
        assert len(claims) == len(inner.requests) == 1 and not foreign.requests
        delegated = inner.requests[0]
        assert delegated is not request and delegated.content == original_body
        assert delegated.headers["authorization"] == "Bearer " + SECRET
        assert delegated.extensions["timeout"]["read"] == 120.0
        assert gate.wire_digest == claims[0]
    finally:
        response.close()
        gate.close()
    assert inner.closes == 1 and foreign.closes == 0


def test_caller_mutation_during_transport_creation_cannot_change_frozen_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, inner = _policy(), FakeTransport()
    claims: list[str] = []
    original = policy.prepared.body

    def factory() -> httpx.BaseTransport:
        object.__setattr__(policy.prepared, "body", b"changed")
        object.__setattr__(policy.tariff, "qualified", False)
        return inner

    monkeypatch.setattr(audio, "_new_inner_transport", factory)
    result = audio.execute_audio_http(policy, audio.AudioCredential(SECRET), _claim(claims))
    assert result.evidence.claim_won and inner.requests[0].content == original


@pytest.mark.parametrize("nonce", [None, True, "", "f" * 63, "G" * 64])
def test_malformed_winning_evidence_never_delegates_and_is_not_retryable(nonce: object) -> None:
    policy, inner = _policy(), FakeTransport()
    calls: list[str] = []

    def claim(digest: str) -> str:
        calls.append(digest)
        return cast(str, nonce)

    gate = audio._FinalAudioGate(policy, SECRET, claim, inner)
    try:
        with pytest.raises(audio.AudioHttpRefused) as caught:
            gate.handle_request(audio._build_request(policy, SECRET))
        _error(caught.value)
        assert caught.value.evidence.claim_attempted and not caught.value.evidence.claim_won
        assert not caught.value.evidence.delegated and len(calls) == 1 and not inner.requests
        with pytest.raises(audio.AudioHttpRefused, match="^second_exchange$"):
            gate.handle_request(audio._build_request(policy, SECRET))
        assert len(calls) == 1
    finally:
        gate.close()


def test_lost_claim_exception_is_value_free_and_closes_owned_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = FakeTransport()
    calls: list[str] = []
    _install(monkeypatch, inner)

    def claim(digest: str) -> str:
        calls.append(digest)
        raise RuntimeError(SECRET)

    with pytest.raises(audio.AudioHttpRefused) as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), claim)
    _error(caught.value)
    assert caught.value.evidence.claim_attempted and not caught.value.evidence.claim_won
    assert not inner.requests and inner.closes == 1
    assert caught.value.evidence.client_retired and caught.value.evidence.transport_retired


def test_second_exchange_cannot_reclaim_after_success() -> None:
    policy, inner = _policy(), FakeTransport()
    claims: list[str] = []
    gate = audio._FinalAudioGate(policy, SECRET, _claim(claims), inner)
    response = gate.handle_request(audio._build_request(policy, SECRET))
    response.close()
    try:
        with pytest.raises(audio.AudioHttpRefused, match="^second_exchange$"):
            gate.handle_request(audio._build_request(policy, SECRET))
        assert len(claims) == len(inner.requests) == 1
    finally:
        gate.close()


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b'{"text":3}',
        b'{"text":"a","text":"b"}',
        b"\xff",
        b'{"text":"a","duration":NaN}',
        b'{"text":"a","duration":1e999}',
        b'{"text":"a","duration":-1}',
        b'{"text":"a","duration":true}',
        b'{"text":"a","language":3}',
        b'{"text":"a","usage":{"type":"tokens","seconds":1}}',
        b'{"text":"a","model":"other"}',
        b'{"text":"\\ud800"}',
        json.dumps({"text": SECRET}).encode(),
        json.dumps({"text": "fine", "segments": [{"text": SECRET}]}).encode(),
    ],
)
def test_strict_response_refusals_are_ambiguous_after_winning_claim(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    inner = FakeTransport(body)
    claims: list[str] = []
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpAmbiguous) as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), _claim(claims))
    _error(caught.value)
    assert caught.value.evidence.claim_won and caught.value.evidence.delegated
    assert caught.value.evidence.response_digest == hashlib.sha256(body).hexdigest()
    assert inner.stream.closes == inner.closes == len(inner.requests) == len(claims) == 1


@pytest.mark.parametrize(
    "status,blocked",
    [(401, True), (402, True), (403, True), (429, False), (500, False), (307, False)],
)
def test_provider_refusal_never_retries_redirects_or_reports_free_success(
    monkeypatch: pytest.MonkeyPatch, status: int, blocked: bool
) -> None:
    inner = FakeTransport(status=status)
    claims: list[str] = []
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpAmbiguous) as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), _claim(claims))
    _error(caught.value)
    assert caught.value.evidence.route_blocked is blocked
    assert len(claims) == len(inner.requests) == inner.closes == inner.stream.closes == 1


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
        [
            ("Content-Type", "application/json"),
            ("Content-Encoding", "identity"),
            ("Content-Encoding", "identity"),
        ],
        [("Content-Type", "text/plain")],
        [("Content-Type", "application/json"), ("Content-Length", str(audio.RESPONSE_LIMIT + 1))],
        [("Content-Type", "application/json"), ("Content-Length", "1")],
    ],
)
def test_header_size_and_encoding_refusals_retire_real_response(
    monkeypatch: pytest.MonkeyPatch, headers: list[tuple[str, str]]
) -> None:
    inner = FakeTransport(headers=headers)
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpAmbiguous) as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), lambda _: NONCE)
    _error(caught.value)
    assert inner.stream.closes == inner.closes == 1


def test_stream_limit_is_enforced_before_appending_overflow_and_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = TrackedStream((b"x" * audio.RESPONSE_LIMIT, b"x"))
    inner = FakeTransport(stream=stream)
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpAmbiguous, match="^response_size$") as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), lambda _: NONCE)
    _error(caught.value)
    assert caught.value.evidence.response_digest is None and stream.closes == inner.closes == 1


@pytest.mark.parametrize("boundary", ["delegate", "read", "response_close", "transport_close"])
def test_acquired_handle_faults_remain_value_free_unknown_and_nonretryable(
    monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    stream = TrackedStream(
        (SUCCESS,), read_failure=boundary == "read", close_failure=boundary == "response_close"
    )
    inner = FakeTransport(
        stream=stream, failure=boundary == "delegate", close_failure=boundary == "transport_close"
    )
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpAmbiguous) as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), lambda _: NONCE)
    _error(caught.value)
    assert caught.value.evidence.claim_won and caught.value.evidence.delegated and inner.closes == 1
    if boundary != "delegate":
        assert stream.closes == 1
    if boundary == "response_close":
        assert caught.value.evidence.response_retired is False
    if boundary == "transport_close":
        assert caught.value.evidence.transport_retired is False


def test_optional_provider_duration_and_usage_remain_metadata_not_quote_or_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy()
    inner = FakeTransport(
        b'{"text":"synthetic","duration":700,"usage":{"type":"duration","seconds":701}}'
    )
    _install(monkeypatch, inner)
    result = audio.execute_audio_http(policy, audio.AudioCredential(SECRET), lambda _: NONCE)
    assert result.provider_duration_seconds == 700 and result.provider_usage_seconds == 701
    assert policy.prepared.quote.duration_seconds == Fraction(4, 16000)
    assert "reserved_cents" not in asdict(result.evidence) and "settled_cents" not in asdict(
        result.evidence
    )


def test_private_transport_constructor_explicitly_disables_retry_environment_and_http2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    inner = FakeTransport()

    def factory(**kwargs: object) -> httpx.BaseTransport:
        calls.append(kwargs)
        return inner

    monkeypatch.setattr(httpx, "HTTPTransport", factory)
    assert audio._new_inner_transport() is inner
    assert calls == [{"http1": True, "http2": False, "retries": 0, "trust_env": False}]
    inner.close()


def test_client_construction_failure_retires_acquired_inner_without_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = FakeTransport()
    claims: list[str] = []
    _install(monkeypatch, inner)

    def factory(**_kwargs: object) -> httpx.Client:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(httpx, "Client", factory)
    with pytest.raises(audio.AudioHttpRefused) as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), _claim(claims))
    _error(caught.value)
    assert not claims and not inner.requests and inner.closes == 1
    assert caught.value.evidence.client_retired is None and caught.value.evidence.transport_retired


def test_empty_stream_chunk_is_refused_instead_of_unbounded_zero_byte_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = FakeTransport(stream=TrackedStream((b"", SUCCESS)))
    _install(monkeypatch, inner)
    with pytest.raises(audio.AudioHttpAmbiguous, match="^response_size$") as caught:
        audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), lambda _: NONCE)
    _error(caught.value)
    assert inner.stream.closes == inner.closes == 1


@pytest.mark.parametrize("close_failure", [False, True])
def test_actual_client_options_and_captured_closers_survive_callback_mutation(
    monkeypatch: pytest.MonkeyPatch, close_failure: bool
) -> None:
    inner = FakeTransport()
    _install(monkeypatch, inner)
    real_client = httpx.Client
    clients: list[httpx.Client] = []
    options: list[dict[str, object]] = []
    closes: list[str] = []

    def factory(**kwargs: object) -> httpx.Client:
        options.append(kwargs.copy())
        client = real_client(
            transport=cast(httpx.BaseTransport, kwargs["transport"]),
            timeout=cast(float, kwargs["timeout"]),
            trust_env=cast(bool, kwargs["trust_env"]),
            follow_redirects=cast(bool, kwargs["follow_redirects"]),
            http1=cast(bool, kwargs["http1"]),
            http2=cast(bool, kwargs["http2"]),
        )
        clients.append(client)
        close = client.close

        def retire() -> None:
            closes.append("captured-client")
            close()
            if close_failure:
                raise RuntimeError(SECRET)

        client.__dict__["close"] = retire
        return client

    monkeypatch.setattr(httpx, "Client", factory)

    def claim(_digest: str) -> str:
        clients[0].__dict__["close"] = lambda: closes.append("replacement-client")
        inner.__dict__["close"] = lambda: closes.append("replacement-inner")
        return NONCE

    if close_failure:
        with pytest.raises(
            audio.AudioHttpAmbiguous, match="^client_retirement_unconfirmed$"
        ) as caught:
            audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), claim)
        _error(caught.value)
        assert caught.value.evidence.client_retired is False
        assert caught.value.evidence.transport_retired
    else:
        result = audio.execute_audio_http(_policy(), audio.AudioCredential(SECRET), claim)
        assert result.evidence.client_retired and result.evidence.transport_retired
    assert len(inner.requests) == inner.closes == 1 and closes == ["captured-client"]
    supplied = options[0]
    assert set(supplied) == {
        "transport",
        "timeout",
        "trust_env",
        "follow_redirects",
        "http1",
        "http2",
    }
    assert supplied["timeout"] == 120.0 and supplied["trust_env"] is False
    assert (
        supplied["follow_redirects"] is False
        and supplied["http1"] is True
        and supplied["http2"] is False
    )

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

import substrate.multimedia.tts_gateway_server as gateway_module
from substrate.multimedia.tts_gateway_server import (
    ProviderSpeechResult,
    TTSGatewayConflict,
    TTSGatewayOutcomeUnknown,
    TTSGatewayServerRuntime,
    synthesize_gateway_request,
)


def _body(*, text: str = "A concise history of flight.") -> dict[str, object]:
    return {
        "asset_id": "asset-1", "channels": 1, "chapter_id": "chapter-1",
        "endpoint_capability": "text-to-speech", "model": "gpt-4o-mini-tts",
        "paragraph_ids": ["paragraph-1"], "provider": "openai",
        "revision_id": "revision-1", "route_policy": "balanced",
        "sample_rate_hz": 24000, "schema_version": "antiek.chapter-tts-request.v1",
        "script_line_ids": ["line-1"], "source_chunk_ids": ["chunk-1"],
        "speed": 1.0, "text": text, "title": "Flight", "voice": "narrator",
    }


def _envelope(account: str = "a" * 64, *, text: str = "A concise history of flight."):
    body = _body(text=text)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    return {
        "account_identity_digest": account, "endpoint_capability": "text-to-speech",
        "model": "gpt-4o-mini-tts", "provider": "openai", "request_body": body,
        "request_body_digest": digest, "schema_version": "antiek.tts-gateway-request.v1",
    }, f"antiek-tts-{digest}"


def _runtime(tmp_path: Path, synthesize, *, account: str = "a" * 64):
    output = tmp_path / f"audio-{account[0]}"
    output.mkdir(mode=0o700)
    return TTSGatewayServerRuntime(
        db_path=str(tmp_path / "gateway.duckdb"), output_dir=str(output),
        integrity_key=b"i" * 32, bearer_token="gateway-secret", account_identity_digest=account,
        provider="openai", model="gpt-4o-mini-tts", logical_voice="narrator",
        provider_voice="alloy", synthesize=synthesize,
    )


def test_completed_submission_is_called_once_sealed_and_replayed(tmp_path: Path) -> None:
    calls: list[tuple[object, str, str]] = []

    def provider(body, client_request_id, voice):
        calls.append((body, client_request_id, voice))
        return ProviderSpeechResult(b"real-audio", "audio/mpeg", "req_provider_1")

    runtime = _runtime(tmp_path, provider)
    envelope, key = _envelope()
    first = synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    second = synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    assert first == second
    assert len(calls) == 1
    assert calls[0][1].startswith("antiek-") and calls[0][2] == "alloy"
    files = list(Path(runtime.output_dir).iterdir())
    assert len(files) == 1 and files[0].stat().st_mode & 0o777 == 0o600


def test_ambiguous_provider_failure_is_never_called_again(tmp_path: Path) -> None:
    calls = 0

    def provider(*_args):
        nonlocal calls
        calls += 1
        raise TimeoutError("ambiguous")

    runtime = _runtime(tmp_path, provider)
    envelope, key = _envelope()
    with pytest.raises(TTSGatewayOutcomeUnknown):
        synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    with pytest.raises(TTSGatewayOutcomeUnknown):
        synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    assert calls == 1


def test_invalid_provider_evidence_becomes_unknown_without_retry(tmp_path: Path) -> None:
    calls = 0

    def provider(*_args):
        nonlocal calls
        calls += 1
        return ProviderSpeechResult(b"audio", "audio/mpeg", "bad request id")

    runtime = _runtime(tmp_path, provider)
    envelope, key = _envelope()
    for _ in range(2):
        with pytest.raises(TTSGatewayOutcomeUnknown):
            synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    assert calls == 1


def test_concurrent_replay_observes_sending_and_never_calls_twice(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def provider(*_args):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(5)
        return ProviderSpeechResult(b"audio", "audio/mpeg", "req_1")

    runtime = _runtime(tmp_path, provider)
    envelope, key = _envelope()
    outcome: list[object] = []
    worker = threading.Thread(
        target=lambda: outcome.append(
            synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
        )
    )
    worker.start()
    assert entered.wait(5)
    with pytest.raises(TTSGatewayOutcomeUnknown):
        synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    release.set()
    worker.join(5)
    assert not worker.is_alive() and len(outcome) == 1 and calls == 1


def test_crash_after_provider_success_never_resubmits(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def provider(*_args):
        nonlocal calls
        calls += 1
        return ProviderSpeechResult(b"audio", "audio/mpeg", "req_1")

    monkeypatch.setattr(gateway_module, "_seal_audio", lambda *_args, **_kwargs: 1 / 0)
    runtime = _runtime(tmp_path, provider)
    envelope, key = _envelope()
    for _ in range(2):
        with pytest.raises(TTSGatewayOutcomeUnknown):
            synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    assert calls == 1


def test_unknown_persistence_failure_still_surfaces_unknown(tmp_path: Path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, lambda *_args: (_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(
        gateway_module, "_mark_unknown", lambda *_args: (_ for _ in ()).throw(RuntimeError())
    )
    envelope, key = _envelope()
    with pytest.raises(TTSGatewayOutcomeUnknown, match="durable state"):
        synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)


def test_account_drift_conflicts_with_existing_idempotency_authority(tmp_path: Path) -> None:
    def provider(*_args):
        return ProviderSpeechResult(b"audio", "audio/mpeg", "req_1")
    first_runtime = _runtime(tmp_path, provider)
    envelope, key = _envelope()
    synthesize_gateway_request(envelope, idempotency_key=key, runtime=first_runtime)
    second_runtime = TTSGatewayServerRuntime(
        **{**first_runtime.__dict__, "account_identity_digest": "b" * 64}
    )
    second_envelope, _ = _envelope("b" * 64)
    with pytest.raises(TTSGatewayConflict):
        synthesize_gateway_request(second_envelope, idempotency_key=key, runtime=second_runtime)


def test_completed_audio_tampering_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path, lambda *_args: ProviderSpeechResult(b"audio", "audio/mpeg", "req_1")
    )
    envelope, key = _envelope()
    synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    next(Path(runtime.output_dir).iterdir()).write_bytes(b"tampered")
    with pytest.raises(TTSGatewayConflict, match="integrity"):
        synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda envelope, key: (envelope, key + "x"),
        lambda envelope, key: ({**envelope, "account_identity_digest": "b" * 64}, key),
        lambda envelope, key: ({**envelope, "request_body": {**envelope["request_body"], "text": "changed"}}, key),
        lambda envelope, key: ({**envelope, "request_body": {**envelope["request_body"], "text": "x" * 4097}}, key),
    ],
)
def test_request_authority_validation_precedes_provider(tmp_path: Path, mutation) -> None:
    runtime = _runtime(tmp_path, lambda *_args: pytest.fail("provider must not run"))
    envelope, key = mutation(*_envelope())
    with pytest.raises(ValueError):
        synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)

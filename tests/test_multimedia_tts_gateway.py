from __future__ import annotations

import base64
import json

import pytest

from substrate.multimedia.narration_run import prepare_narration_run
from substrate.multimedia.planner import EvidenceChunk, MultimediaPlanRequest, build_multimedia_plan
from substrate.multimedia.tts_gateway import (
    GatewayResponse,
    TTSSynthesisGateway,
    TTSSynthesisGatewayError,
)


def _request():
    plan = build_multimedia_plan(
        MultimediaPlanRequest(
            topic="Gateway narration",
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
            sources=("Evidence",),
        ),
        (
            EvidenceChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="Gateway evidence.",
                section_path="section 1",
            ),
        ),
    )
    return prepare_narration_run(
        plan,
        asset_id="asset-1",
        revision_id="rev-1",
        routes={
            chapter.chapter_id: ("trusted-tts", "voice-1")
            for chapter in plan.chapters
            if any(
                line.line_id.split("-line-", 1)[0] == chapter.chapter_id
                for line in plan.script_lines
            )
        },
    ).chapters[0]


def _response(request, **changes) -> GatewayResponse:
    value = {
        "audio_base64": base64.b64encode(b"audio-bytes").decode(),
        "mime_type": "audio/mpeg",
        "model": request.model,
        "provider": request.provider,
        "provider_request_id": "provider-request-1",
        "request_body_digest": request.body_digest,
        "schema_version": "antiek.tts-gateway-response.v1",
        "status": "completed",
    }
    value.update(changes)
    return GatewayResponse(
        200,
        {"Content-Type": "application/json; charset=utf-8"},
        json.dumps(value).encode(),
    )


def test_posts_exact_canonical_request_once_with_digest_idempotency() -> None:
    request = _request()
    calls = []

    def poster(url, headers, body, timeout, ceiling):
        calls.append((url, headers, body, timeout, ceiling))
        return _response(request)

    gateway = TTSSynthesisGateway(
        endpoint_url="https://tts.example.test/v1/synthesize",
        bearer_token="server-secret",
        account_identity_digest="a" * 64,
        timeout_seconds=12,
        poster=poster,
    )
    result = gateway(request)
    assert result.audio_bytes == b"audio-bytes"
    assert result.provider_request_id == "provider-request-1"
    assert len(calls) == 1
    url, headers, body, timeout, ceiling = calls[0]
    assert url == "https://tts.example.test/v1/synthesize"
    assert headers["Authorization"] == "Bearer server-secret"
    assert headers["Idempotency-Key"] == f"antiek-tts-{request.body_digest}"
    assert timeout == 12
    assert ceiling > 64 * 1024 * 1024
    envelope = json.loads(body)
    assert envelope["request_body"] == json.loads(request.body_json)
    assert envelope["request_body_digest"] == request.body_digest
    assert "text" in envelope["request_body"]
    assert "server-secret" not in body.decode()


@pytest.mark.parametrize(
    "response",
    [
        GatewayResponse(302, {"Content-Type": "application/json"}, b"{}"),
        GatewayResponse(500, {"Content-Type": "application/json"}, b"{}"),
        GatewayResponse(200, {"Content-Type": "text/html"}, b"{}"),
        GatewayResponse(200, {"Content-Type": "application/json"}, b"not-json"),
    ],
)
def test_redirect_status_content_type_and_malformed_json_fail(response) -> None:
    gateway = TTSSynthesisGateway(
        endpoint_url="https://tts.example.test/synthesize",
        bearer_token="secret",
        account_identity_digest="a" * 64,
        poster=lambda *_args: response,
    )
    with pytest.raises(TTSSynthesisGatewayError):
        gateway(_request())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"request_body_digest": "f" * 64}, "authority"),
        ({"provider": "other"}, "authority"),
        ({"model": "other"}, "authority"),
        ({"status": "pending"}, "authority"),
        ({"provider_request_id": "bad id"}, "authority"),
        ({"mime_type": "text/plain"}, "authority"),
        ({"audio_base64": "%%%"}, "audio"),
        ({"extra": "field"}, "shape"),
    ],
)
def test_response_authority_and_shape_drift_fail(changes, message) -> None:
    request = _request()
    gateway = TTSSynthesisGateway(
        endpoint_url="https://tts.example.test/synthesize",
        bearer_token="secret",
        account_identity_digest="a" * 64,
        poster=lambda *_args: _response(request, **changes),
    )
    with pytest.raises(TTSSynthesisGatewayError, match=message):
        gateway(request)


def test_ambiguous_transport_is_attempted_once_and_never_retried() -> None:
    calls = 0

    def fail(*_args):
        nonlocal calls
        calls += 1
        raise TimeoutError("response lost")

    gateway = TTSSynthesisGateway(
        endpoint_url="https://tts.example.test/synthesize",
        bearer_token="secret",
        account_identity_digest="a" * 64,
        poster=fail,
    )
    with pytest.raises(TTSSynthesisGatewayError, match="unknown"):
        gateway(_request())
    assert calls == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint_url": "http://tts.example.test/synthesize"},
        {"endpoint_url": "https://user@tts.example.test/synthesize"},
        {"endpoint_url": "https://tts.example.test:8443/synthesize"},
        {"endpoint_url": "https://tts.example.test/synthesize?redirect=x"},
        {"bearer_token": "bad\nheader"},
        {"account_identity_digest": "not-a-digest"},
        {"timeout_seconds": 0},
    ],
)
def test_configuration_fails_closed(changes) -> None:
    values = {
        "endpoint_url": "https://tts.example.test/synthesize",
        "bearer_token": "secret",
        "account_identity_digest": "a" * 64,
        **changes,
    }
    with pytest.raises(ValueError):
        TTSSynthesisGateway(**values)

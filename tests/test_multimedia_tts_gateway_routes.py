from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_tts_gateway_routes import (
    get_multimedia_tts_gateway_runtime,
    multimedia_tts_gateway_router,
    multimedia_tts_gateway_runtime_from_environment,
)
from substrate.multimedia.tts_gateway_server import ProviderSpeechResult
from tests.test_multimedia_tts_gateway_server import _envelope, _runtime


def _client(runtime) -> TestClient:
    app = FastAPI()
    app.include_router(multimedia_tts_gateway_router, prefix="/multimedia")
    app.dependency_overrides[get_multimedia_tts_gateway_runtime] = lambda: runtime
    return TestClient(app)


def test_route_authenticates_and_returns_exact_bounded_contract(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path, lambda *_args: ProviderSpeechResult(b"audio", "audio/mpeg", "req_1")
    )
    envelope, key = _envelope()
    client = _client(runtime)
    assert client.post("/multimedia/tts-gateway/synthesize", json=envelope).status_code == 401
    response = client.post(
        "/multimedia/tts-gateway/synthesize", json=envelope,
        headers={"Authorization": "Bearer gateway-secret", "Idempotency-Key": key},
    )
    assert response.status_code == 200
    assert response.json() == {
        "audio_base64": "YXVkaW8=", "mime_type": "audio/mpeg", "model": "gpt-4o-mini-tts",
        "provider": "openai", "provider_request_id": "req_1",
        "request_body_digest": envelope["request_body_digest"],
        "schema_version": "antiek.tts-gateway-response.v1", "status": "completed",
    }


def test_route_preserves_integer_speed_for_exact_digest(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path, lambda *_args: ProviderSpeechResult(b"audio", "audio/mpeg", "req_1")
    )
    envelope, key = _envelope()
    envelope["request_body"]["speed"] = 1
    encoded = json.dumps(
        envelope["request_body"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    import hashlib

    digest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    envelope["request_body_digest"] = digest
    response = _client(runtime).post(
        "/multimedia/tts-gateway/synthesize", json=envelope,
        headers={
            "Authorization": "Bearer gateway-secret", "Idempotency-Key": f"antiek-tts-{digest}"
        },
    )
    assert response.status_code == 200


def _configuration(root: Path) -> dict[str, str]:
    root.mkdir(mode=0o700)
    output = root / "audio"
    output.mkdir(mode=0o700)
    prefix = "ANTIEK_MULTIMEDIA_TTS_GATEWAY_"
    return {
        prefix + "DB_PATH": str(root / "gateway.duckdb"), prefix + "OUTPUT_DIR": str(output),
        prefix + "INTEGRITY_KEY_HEX": "11" * 32, prefix + "BEARER_TOKEN": "gateway-token",
        prefix + "ACCOUNT_IDENTITY_DIGEST": "a" * 64, prefix + "OPENAI_API_KEY": "provider-key",
        prefix + "MODEL": "gpt-4o-mini-tts", prefix + "LOGICAL_VOICE": "narrator",
        prefix + "PROVIDER_VOICE": "alloy", prefix + "TIMEOUT_SECONDS": "30",
    }


def test_environment_runtime_calls_fixed_openai_origin_with_trace_id(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(url=str(request.url), headers=dict(request.headers), body=json.loads(request.content))
        return httpx.Response(
            200, headers={"Content-Type": "audio/mpeg", "X-Request-Id": "req_openai_1"},
            content=b"provider-audio",
        )

    runtime = multimedia_tts_gateway_runtime_from_environment(
        _configuration(tmp_path / "runtime"), transport=httpx.MockTransport(handler)
    )
    assert runtime is not None
    envelope, key = _envelope()
    result = __import__(
        "substrate.multimedia.tts_gateway_server", fromlist=["synthesize_gateway_request"]
    ).synthesize_gateway_request(envelope, idempotency_key=key, runtime=runtime)
    assert result.provider_request_id == "req_openai_1"
    assert observed["url"] == "https://api.openai.com/v1/audio/speech"
    assert observed["headers"]["x-client-request-id"].startswith("antiek-")
    assert observed["headers"]["authorization"] == "Bearer provider-key"
    assert observed["body"] == {
        "input": "A concise history of flight.", "model": "gpt-4o-mini-tts",
        "response_format": "mp3", "speed": 1.0, "voice": "alloy",
    }


def test_environment_is_disabled_empty_and_fails_partial_or_shared_secret(tmp_path: Path) -> None:
    assert multimedia_tts_gateway_runtime_from_environment({}) is None
    config = _configuration(tmp_path / "partial")
    config.pop("ANTIEK_MULTIMEDIA_TTS_GATEWAY_MODEL")
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_tts_gateway_runtime_from_environment(config)
    config = _configuration(tmp_path / "shared")
    config["ANTIEK_MULTIMEDIA_TTS_GATEWAY_OPENAI_API_KEY"] = "gateway-token"
    with pytest.raises(RuntimeError, match="invalid"):
        multimedia_tts_gateway_runtime_from_environment(config)


def test_multimedia_registration_installs_exact_gateway_runtime(tmp_path: Path, monkeypatch) -> None:
    runtime = multimedia_tts_gateway_runtime_from_environment(
        _configuration(tmp_path / "runtime"),
        transport=httpx.MockTransport(lambda _request: pytest.fail("provider must stay lazy")),
    )
    assert runtime is not None
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_tts_gateway_runtime_from_environment", lambda: runtime
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reconciliation_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_knowledge_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_playback_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_narration_authorization_runtime_from_environment",
        lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reviewed_visual_runtime_from_environment",
        lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_production_worker_runtime_from_environment",
        lambda *, store: None,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    assert app.dependency_overrides[get_multimedia_tts_gateway_runtime]() is runtime

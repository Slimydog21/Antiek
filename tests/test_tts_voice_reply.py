"""Read SPR-07 — voice replies (backend TTS synthesis).

The async voice-reply path: an AI reply is synthesized to mp3 on demand.
Synthesis is gated on the operator key (no key ⇒ RuntimeError, never a
silent credit burn) and the HTTP poster is injectable so this test does
no network call.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.speech import register_speech_routes
from substrate.dispatch.providers.openai_tts import OpenAITTSProvider


def _speech_client_with_provider(monkeypatch, provider_cls) -> TestClient:
    """Mount only the speech route with a fake provider class."""
    import substrate.dispatch.providers.openai_tts as openai_tts

    monkeypatch.setattr(openai_tts, "OpenAITTSProvider", provider_cls)
    app = FastAPI()
    register_speech_routes(app)
    return TestClient(app)


def test_synthesize_uses_injected_poster_and_passes_text_and_voice():
    captured = {}

    def fake_poster(url, headers, body):
        captured["url"] = url
        captured["body"] = body
        captured["auth"] = headers.get("Authorization")
        return b"ID3-fake-mp3-bytes"

    provider = OpenAITTSProvider(api_key="sk-test", voice="alloy")
    audio = provider.synthesize("The Stoics held that virtue suffices.", voice="nova", poster=fake_poster)

    assert audio == b"ID3-fake-mp3-bytes"
    assert captured["url"].endswith("/audio/speech")
    assert captured["body"]["input"] == "The Stoics held that virtue suffices."
    assert captured["body"]["voice"] == "nova"  # per-call voice overrides default
    assert captured["auth"] == "Bearer sk-test"


def test_synthesize_without_key_raises_not_burns():
    provider = OpenAITTSProvider(api_key=None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY missing"):
        provider.synthesize("hello")


def test_synthesize_empty_text_rejected():
    provider = OpenAITTSProvider(api_key="sk-test")
    with pytest.raises(ValueError, match="empty"):
        provider.synthesize("   ", poster=lambda u, h, b: b"x")


def test_endpoint_returns_503_without_key(monkeypatch):
    """The /speech/tts route surfaces a clean 503 when no key is set,
    rather than crashing."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    resp = client.post("/speech/tts", json={"text": "hello"})
    assert resp.status_code == 503
    assert "tts_unavailable" in resp.json()["detail"]


def test_endpoint_returns_mp3_and_passes_voice_to_provider(monkeypatch):
    calls = []

    class FakeProvider:
        def synthesize(self, text, voice=None):
            calls.append({"text": text, "voice": voice})
            return b"ID3-route-audio"

    client = _speech_client_with_provider(monkeypatch, FakeProvider)

    resp = client.post("/speech/tts", json={"text": "hello reader", "voice": "nova"})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"ID3-route-audio"
    assert calls == [{"text": "hello reader", "voice": "nova"}]


def test_endpoint_accepts_missing_voice_and_passes_none_to_provider(monkeypatch):
    calls = []

    class FakeProvider:
        def synthesize(self, text, voice=None):
            calls.append({"text": text, "voice": voice})
            return b"ID3-route-audio"

    client = _speech_client_with_provider(monkeypatch, FakeProvider)

    resp = client.post("/speech/tts", json={"text": "hello reader"})

    assert resp.status_code == 200
    assert resp.content == b"ID3-route-audio"
    assert calls == [{"text": "hello reader", "voice": None}]


def test_endpoint_maps_provider_value_error_to_400(monkeypatch):
    class RejectingProvider:
        def synthesize(self, text, voice=None):
            raise ValueError("cannot synthesize empty text")

    client = _speech_client_with_provider(monkeypatch, RejectingProvider)

    resp = client.post("/speech/tts", json={"text": "   "})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "cannot synthesize empty text"


@pytest.mark.parametrize("text", ["", "x" * 8001])
def test_endpoint_rejects_request_model_text_bounds_before_provider(monkeypatch, text):
    class ProviderShouldNotBeCalled:
        def synthesize(self, text, voice=None):  # pragma: no cover
            raise AssertionError("provider should not be called")

    client = _speech_client_with_provider(monkeypatch, ProviderShouldNotBeCalled)

    resp = client.post("/speech/tts", json={"text": text})

    assert resp.status_code == 422


def test_endpoint_maps_provider_runtime_error_to_503(monkeypatch):
    class UnavailableProvider:
        def synthesize(self, text, voice=None):
            raise RuntimeError("OPENAI_API_KEY missing")

    client = _speech_client_with_provider(monkeypatch, UnavailableProvider)

    resp = client.post("/speech/tts", json={"text": "hello"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "tts_unavailable: OPENAI_API_KEY missing"


def test_endpoint_maps_provider_constructor_runtime_error_to_503(monkeypatch):
    """Defensive guard for future providers that validate credentials at init."""

    class UnavailableProvider:
        def __init__(self):
            raise RuntimeError("OPENAI_API_KEY missing")

    client = _speech_client_with_provider(monkeypatch, UnavailableProvider)

    resp = client.post("/speech/tts", json={"text": "hello"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "tts_unavailable: OPENAI_API_KEY missing"

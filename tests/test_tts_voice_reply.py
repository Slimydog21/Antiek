"""Read SPR-07 — voice replies (backend TTS synthesis).

The async voice-reply path: an AI reply is synthesized to mp3 on demand.
Synthesis is gated on the operator key (no key ⇒ RuntimeError, never a
silent credit burn) and the HTTP poster is injectable so this test does
no network call.
"""

from __future__ import annotations

import pytest

from substrate.dispatch.providers.openai_tts import OpenAITTSProvider


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

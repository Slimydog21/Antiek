"""Speak — the token-gated invitee VOICE route (Product Depth SPR-08 M3).

The headline invitee fix: a non-power-user on a phone taps to talk and their
VOICE — not typed text — becomes their answer. These tests pin the mechanism
the sprint promises:

  • the token is the credential (bad token → 404, never an auth 401);
  • it reuses the SINGLE voice owner (a stub Transcriber injected at the same
    seam the operator path uses) → submit_answer → the same answer→claim
    bridge the typed /answer route uses (no second pipeline);
  • consent precedes recording (answer-before-consent → 403);
  • HONEST NO-KEY: with no transcriber and no provider, transcription raises
    AsrError → 503 — never a fabricated transcript.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.speak_routes as speak_routes
from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


class StubTranscriber:
    """Stands in for WhisperTranscriber — the ONE voice owner's interface."""

    def __init__(self, text: str = "He taught me to bake bread before dawn."):
        self._text = text

    def transcribe(self, audio_bytes, *, filename, language=None):
        class _T:
            text = self._text

        return _T()


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-voice-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # No model provider — so the no-key path is the DEFAULT unless a test
    # injects a stub transcriber.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _token_from_link(link: str) -> str:
    return link.split("token=", 1)[1]


def _invited_token(client) -> str:
    pid = client.post("/speak/projects", json={"title": "Dad's biography"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "aunt@x.com"}).json()
    return _token_from_link(iv["link"])


def test_invitee_voice_bridges_to_an_answer(client, monkeypatch):
    """A recorded blob → the single voice owner → the answer→claim bridge."""
    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", StubTranscriber())
    token = _invited_token(client)
    # Consent precedes recording.
    assert client.post(f"/speak/invite/{token}/consent", json={"scopes": ["record"]}).status_code == 200
    # Tap-to-talk: the recorded blob is the raw body; question_id rides the query.
    r = client.post(
        f"/speak/invite/{token}/voice?question_id=q1&duration_seconds=8",
        content=b"\x00\x01\x02fake-webm-opus",
        headers={"Content-Type": "audio/webm"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["question_id"] == "q1"
    assert body["document_id"], "the answer landed a voice-note document (single-writer bridge)"
    assert "bread" in body["transcript"]
    # The landing reflects the contribution — proving it went through the SAME
    # answer turn the typed route uses, not a parallel store.
    landing = client.get(f"/speak/invite/{token}").json()
    assert any("bread" in t["text"] for t in landing["transcript"])


def test_invitee_voice_requires_consent(client, monkeypatch):
    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", StubTranscriber())
    token = _invited_token(client)
    # Record before consent → 403 (the same gate the typed answer enforces).
    r = client.post(
        f"/speak/invite/{token}/voice?question_id=q1",
        content=b"audio-bytes",
        headers={"Content-Type": "audio/webm"},
    )
    assert r.status_code == 403


def test_invitee_voice_bad_token_404(client, monkeypatch):
    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", StubTranscriber())
    r = client.post(
        "/speak/invite/not-a-real-token/voice?question_id=q1",
        content=b"audio",
        headers={"Content-Type": "audio/webm"},
    )
    assert r.status_code == 404


def test_invitee_voice_honest_no_key_503(client):
    """No transcriber injected + no OPENAI_API_KEY → transcription can't run.
    The honest answer is 503 with a real reason — never a fabricated
    transcript and never a silently-distilled mishearing."""
    # _INVITEE_TRANSCRIBER stays None (the fixture clears OPENAI_API_KEY).
    token = _invited_token(client)
    assert client.post(f"/speak/invite/{token}/consent", json={"scopes": ["record"]}).status_code == 200
    r = client.post(
        f"/speak/invite/{token}/voice?question_id=q1",
        content=b"\x00\x01real-audio",
        headers={"Content-Type": "audio/webm"},
    )
    assert r.status_code == 503, r.text
    # No answer was recorded — nothing fabricated landed.
    landing = client.get(f"/speak/invite/{token}").json()
    assert landing["transcript"] == [] or all(
        t.get("role") != "informant" for t in landing["transcript"]
    )


def test_invitee_voice_empty_body_400(client, monkeypatch):
    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", StubTranscriber())
    token = _invited_token(client)
    client.post(f"/speak/invite/{token}/consent", json={"scopes": ["record"]})
    r = client.post(
        f"/speak/invite/{token}/voice?question_id=q1",
        content=b"",
        headers={"Content-Type": "audio/webm"},
    )
    assert r.status_code == 400


def test_invitee_voice_surface_open_while_operator_authed(client, monkeypatch):
    """The voice route is under /speak/invite/ — the token is the credential,
    so it must stay reachable when operator auth is ON (404 for a bad token,
    not an auth 401)."""
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")
    r = client.post(
        "/speak/invite/some-token/voice?question_id=q1",
        content=b"audio",
        headers={"Content-Type": "audio/webm"},
    )
    assert r.status_code not in (401, 403), "invitee voice surface must be open (token-gated)"
    assert r.status_code == 404  # reached the endpoint; token invalid

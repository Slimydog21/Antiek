"""Speak _read must not call ensure_initialized (note-taker contend)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-skip-ensure-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    calls: list[str] = []
    import interfaces.research.api.speak_routes as sr

    real = sr.ensure_initialized

    def wrapped(path=None, **kwargs):
        calls.append("ensure")
        return real(path, **kwargs)

    monkeypatch.setattr(sr, "ensure_initialized", wrapped)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app), calls


def test_invite_landing_does_not_ensure_initialized(client):
    c, calls = client
    # Create via write path (ensures schema)
    priv = c.post(
        "/speak/projects",
        json={"title": "Dad", "publish_intent": "private_never_published"},
    ).json()
    iv = c.post(
        f"/speak/projects/{priv['project_id']}/invites",
        json={"informant_email": "a@x.com"},
    ).json()
    calls.clear()
    r = c.get(f"/speak/invite/{iv['token']}")
    assert r.status_code == 200, r.text
    assert calls == [], f"ensure_initialized called on invite GET: {calls}"


def test_opportunities_read_skips_ensure(client):
    c, calls = client
    c.post(
        "/speak/projects",
        json={"title": "Pub", "publish_intent": "will_be_public"},
    )
    calls.clear()
    r = c.get("/speak/opportunities")
    assert r.status_code == 200
    assert calls == []

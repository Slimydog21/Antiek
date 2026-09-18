"""Invite landing stays responsive under write-lock contention."""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-invite-nb-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app), db


def test_invite_landing_fast_while_writer_holds_lock(env):
    client, db = env
    priv = client.post(
        "/speak/projects",
        json={"title": "Dad", "publish_intent": "private_never_published"},
    ).json()
    iv = client.post(
        f"/speak/projects/{priv['project_id']}/invites",
        json={"informant_email": "aunt@x.com"},
    ).json()
    token = iv["token"]

    release = threading.Event()
    held = threading.Event()

    def hold_writer():
        with connect_write(db, purpose="test:hold-for-invite", timeout_s=30) as con:
            con.execute("SELECT 1")
            held.set()
            release.wait(timeout=15)

    t = threading.Thread(target=hold_writer, daemon=True)
    t.start()
    assert held.wait(timeout=5)

    t0 = time.monotonic()
    r = client.get(f"/speak/invite/{token}")
    elapsed = time.monotonic() - t0
    release.set()
    t.join(timeout=5)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interview_id"] == iv["interview_id"]
    # Must not sit behind write flock / write_log close (was multi-second hangs).
    assert elapsed < 2.0, f"invite landing took {elapsed:.3f}s under writer hold"

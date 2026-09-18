"""Unauth public Speak browse — feed + opportunities open under operator auth."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-unauth-browse-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_feed_and_opportunities_open_while_operator_auth_on(client, monkeypatch):
    """Logged-out browse must not 401 when operator auth is enforced."""
    r = client.post(
        "/speak/projects",
        json={
            "title": "Uncle Theo",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    )
    assert r.status_code == 201, r.text
    project_id = r.json()["project_id"]

    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")

    feed = client.get("/speak/feed")
    assert feed.status_code == 200, feed.text
    ids = [x["project_id"] for x in feed.json()["projects"]]
    assert project_id in ids

    opps = client.get("/speak/opportunities")
    assert opps.status_code == 200, opps.text
    data = opps.json()
    assert data["honesty"]["auth"] == "unauthenticated_read_only"
    assert "gated_G7" in data["honesty"]["open_contribution_without_invite"]
    pub_ids = [o["project_id"] for o in data["public_opportunities"]]
    assert project_id in pub_ids

    blocked = client.post("/speak/projects", json={"title": "Nope"})
    assert blocked.status_code in (401, 403)


def test_opportunities_honest_empty_g7(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")
    r = client.get("/speak/opportunities")
    assert r.status_code == 200
    body = r.json()
    assert body["public_opportunities"] == []
    assert "gated_G7" in body["honesty"]["open_contribution_without_invite"]

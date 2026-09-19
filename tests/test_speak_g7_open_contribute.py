"""G7 open contribution — stranger self-serve mint for will_be_public only."""

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
    tmpdir = tempfile.mkdtemp(prefix="speak-g7-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_open_contribute_gated_without_g7(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", raising=False)
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    r = client.post(f"/speak/projects/{pub['project_id']}/open-contribute")
    assert r.status_code == 403
    assert "G7" in r.json()["detail"] or "ecosystem" in r.json()["detail"].lower()


def test_open_contribute_mints_token_for_public_when_g7(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    pid = pub["project_id"]
    r = client.post(f"/speak/projects/{pid}/open-contribute")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["honesty"]["open_contribution"] == "live_g7_will_be_public_only"
    assert body["honesty"]["private_projects"] == "invite_only_unchanged"
    assert body["token"]
    assert body["invite_path"] == f"/speak/invite/{body['token']}"
    # Door resolves unauth
    land = client.get(body["invite_path"])
    assert land.status_code == 200
    # Opportunities honesty flips to live
    opps = client.get("/speak/opportunities").json()
    assert opps["honesty"]["open_contribution_without_invite"] == "live"


def test_open_contribute_refuses_private_even_with_g7(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    priv = client.post(
        "/speak/projects",
        json={
            "title": "Dad private",
            "publish_intent": "private_never_published",
        },
    ).json()
    r = client.post(f"/speak/projects/{priv['project_id']}/open-contribute")
    assert r.status_code == 403
    detail = r.json()["detail"].lower()
    assert "private" in detail or "invite-only" in detail


def test_open_contribute_unauth_when_operator_auth_on(client, monkeypatch):
    """Stranger browse must mint without operator token once G7 is on."""
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={"title": "Public", "publish_intent": "will_be_public"},
    ).json()
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")
    r = client.post(f"/speak/projects/{pub['project_id']}/open-contribute")
    assert r.status_code == 201, r.text
    # Private mutate still blocked
    blocked = client.post("/speak/projects", json={"title": "Nope"})
    assert blocked.status_code in (401, 403)

"""Speak dual-push / continuous-ping MVP tests."""

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
    tmpdir = tempfile.mkdtemp(prefix="speak-pushes-test-")
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


def test_pushes_lists_public_heuristic_and_private_repings(client):
    # Public-intent project with zero voices → top opportunity.
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Needs voices",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    # Private project with an invitee still in flight.
    priv = client.post(
        "/speak/projects",
        json={
            "title": "Dad private",
            "subject_ref": "Dad",
            "publish_intent": "private_never_published",
        },
    ).json()
    iv = client.post(
        f"/speak/projects/{priv['project_id']}/invites",
        json={"informant_email": "aunt@x.com"},
    ).json()
    assert iv.get("token")

    pushes = client.get("/speak/pushes").json()
    assert pushes["honesty"]["public_ranking"].startswith("fewest_voices")
    assert "no_email" in pushes["honesty"]["private_delivery"]
    pub_ids = [o["project_id"] for o in pushes["public_opportunities"]]
    assert pub["project_id"] in pub_ids
    # Public ranking reason is honest (not ML).
    reason = next(
        o["rank_reason"]
        for o in pushes["public_opportunities"]
        if o["project_id"] == pub["project_id"]
    )
    assert "heuristic" in reason
    assert "profile" in reason.lower() or "not ml" in reason.lower()

    priv_ids = [r["interview_id"] for r in pushes["private_repings"]]
    assert iv["interview_id"] in priv_ids
    row = next(r for r in pushes["private_repings"] if r["interview_id"] == iv["interview_id"])
    assert row["invite_path"] == f"/speak/invite/{iv['token']}"
    assert row["who"] == "aunt@x.com"


def test_reping_generates_followups_and_returns_invite_door(client):
    priv = client.post(
        "/speak/projects",
        json={"title": "Bio", "publish_intent": "private_never_published"},
    ).json()
    iv = client.post(
        f"/speak/projects/{priv['project_id']}/invites",
        json={"informant_email": "friend@x.com"},
    ).json()
    token = iv["token"]
    assert client.post(
        f"/speak/invite/{token}/consent", json={"scopes": ["record"]}
    ).status_code == 200
    client.post(
        f"/speak/invite/{token}/answer",
        json={"question_id": "q1", "transcript": "He loved the bakery before dawn."},
    )

    r = client.post("/speak/pushes/reping", json={"interview_id": iv["interview_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_reason"] is None
    assert body["invite_path"] == f"/speak/invite/{token}"
    assert body["pending_question_count"] >= 0
    # Door still resolves.
    assert client.get(f"/speak/invite/{token}").status_code == 200


def test_reping_skips_declined_consent_scoped(client):
    priv = client.post(
        "/speak/projects",
        json={"title": "Bio", "publish_intent": "private_never_published"},
    ).json()
    iv = client.post(
        f"/speak/projects/{priv['project_id']}/invites",
        json={"informant_email": "nope@x.com"},
    ).json()
    assert client.post(f"/speak/invite/{iv['token']}/decline").status_code == 200
    r = client.post("/speak/pushes/reping", json={"interview_id": iv["interview_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped_reason"] and "declined" in body["skipped_reason"]
    assert body["followups_added"] == 0

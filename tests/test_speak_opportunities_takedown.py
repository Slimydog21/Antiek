"""Public opportunities honour takedowns (LB-34).

GET /speak/opportunities is open to logged-out visitors and lists every
will_be_public project with its title and subject. A subject who demanded
removal (an active ``subject`` takedown) must stop being advertised there
and in the operator's /speak/pushes, and an interview under an active
takedown must stop counting as a voice: the count would otherwise still
reveal the withdrawn testimony. Reversing the takedown restores both.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.speak import takedown as takedown_mod


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-opportunities-takedown-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    for variable in ("ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_EMAIL", "ANTIEK_AUTH_SECRET",
                     "ANTIEK_DEV_LOGIN_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr("acquisition.voice.adapter.default_embedding_provider", lambda: StubEmbedding())
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return {"client": TestClient(app), "db": db}


def _public_project(client, title: str, subject: str) -> str:
    r = client.post("/speak/projects", json={"title": title, "subject_ref": subject,
                                              "publish_intent": "will_be_public"})
    assert r.status_code in (200, 201), r.text
    return r.json()["project_id"]


def _listed(client) -> dict[str, dict]:
    opportunities = client.get("/speak/opportunities").json()["public_opportunities"]
    return {o["project_id"]: o for o in opportunities}


def _pushed(client) -> set[str]:
    return {o["project_id"] for o in client.get("/speak/pushes").json()["public_opportunities"]}


def test_a_taken_down_subject_is_no_longer_advertised(env):
    c = env["client"]
    kept = _public_project(c, "Harbour memories", "Aunt Rosa")
    removed = _public_project(c, "Uncle Theo's war", "Uncle Theo")
    assert set(_listed(c)) == {kept, removed}

    t = c.post(f"/speak/projects/{removed}/takedowns",
               json={"target_kind": "subject", "target_id": "Uncle Theo", "reason": "asked to be removed"})
    assert t.status_code == 201, t.text

    assert set(_listed(c)) == {kept}
    assert _pushed(c) == {kept}

    with connect_write(env["db"], purpose="test/reverse-takedown") as con:
        takedown_mod.reverse_takedown(con, takedown_id=t.json()["takedown_id"], project_id=removed)
    assert set(_listed(c)) == {kept, removed}


def test_a_claim_takedown_does_not_hide_the_project(env):
    c = env["client"]
    pid = _public_project(c, "Harbour memories", "Aunt Rosa")
    c.post(f"/speak/projects/{pid}/takedowns", json={"target_kind": "claim", "target_id": "clm-1"})
    assert pid in _listed(c)


def test_a_taken_down_interview_is_not_counted_as_a_voice(env):
    c = env["client"]
    pid = _public_project(c, "Harbour memories", "Aunt Rosa")
    first = c.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    c.post(f"/speak/projects/{pid}/invites", json={"informant_email": "b@x.com"})
    assert _listed(c)[pid]["voice_count"] == 2

    c.post(f"/speak/projects/{pid}/takedowns",
           json={"target_kind": "interview", "target_id": first["interview_id"]})
    assert _listed(c)[pid]["voice_count"] == 1

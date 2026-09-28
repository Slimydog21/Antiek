"""Public opportunities honour takedowns (LB-34).

GET /speak/opportunities is open to logged-out visitors and lists every
will_be_public project with its title and subject. An active takedown means
stop publishing, whatever its target: the publish gate refuses a project under
any active takedown, and /speak/feed hides the same projects. So a project
with any active takedown (subject, interview or claim) is not advertised here
or in the operator's /speak/pushes, and reversing the takedown restores it.
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


@pytest.mark.parametrize("target_kind", ["interview", "claim"])
def test_any_active_takedown_hides_the_project(env, target_kind):
    """Not only a subject takedown: an interview or a claim takedown also stops
    publication, as the publish gate and /speak/feed already rule."""
    c = env["client"]
    kept = _public_project(c, "Harbour memories", "Aunt Rosa")
    pid = _public_project(c, "Uncle Theo's war", "Uncle Theo")
    invite = c.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    target_id = invite["interview_id"] if target_kind == "interview" else "clm-1"
    t = c.post(f"/speak/projects/{pid}/takedowns", json={"target_kind": target_kind, "target_id": target_id})
    assert t.status_code == 201, t.text

    assert set(_listed(c)) == {kept}
    assert _pushed(c) == {kept}

    with connect_write(env["db"], purpose="test/reverse-takedown") as con:
        takedown_mod.reverse_takedown(con, takedown_id=t.json()["takedown_id"], project_id=pid)
    assert set(_listed(c)) == {kept, pid}
    assert _listed(c)[pid]["voice_count"] == 1


def test_opportunities_and_feed_hide_the_same_projects(env):
    """The two unauthenticated lists agree: one predicate, one answer."""
    c = env["client"]
    ids = [_public_project(c, f"Project {k}", f"Subject {k}") for k in "abc"]
    c.post(f"/speak/projects/{ids[0]}/takedowns", json={"target_kind": "subject", "target_id": "Subject a"})
    c.post(f"/speak/projects/{ids[1]}/takedowns", json={"target_kind": "claim", "target_id": "clm-9"})
    feed = c.get("/speak/feed")
    assert feed.status_code == 200, feed.text
    body = feed.json()
    rows = body if isinstance(body, list) else next(v for v in body.values() if isinstance(v, list))
    feed_ids = {r["project_id"] for r in rows}
    assert set(_listed(c)) == {ids[2]}
    assert feed_ids & set(ids) == {ids[2]}

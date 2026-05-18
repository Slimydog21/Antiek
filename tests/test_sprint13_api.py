"""Tests for Sprint 13 API additions: deliverables + sections + voice notes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sprint13-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. POST /deliverables
# ─────────────────────────────────────────────────────────────────────


def test_post_deliverable_returns_id_and_metadata(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/deliverables", json={
        "title": "Substrate Compounding Analysis",
        "deliverable_kind": "research_memo",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Substrate Compounding Analysis"
    assert body["deliverable_kind"] == "research_memo"
    assert body["status"] == "draft"
    assert body["deliverable_id"].startswith("dlv-")
    assert body["section_count"] == 0


def test_post_deliverable_invalid_kind_rejected(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/deliverables", json={
        "title": "Bad",
        "deliverable_kind": "not_a_real_kind",
    })
    assert resp.status_code == 422


def test_post_deliverable_empty_title_rejected(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/deliverables", json={
        "title": "",
        "deliverable_kind": "research_memo",
    })
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# 2. GET /deliverables (list)
# ─────────────────────────────────────────────────────────────────────


def test_list_deliverables_empty(temp_substrate):
    client = _client(temp_substrate)
    resp = client.get("/deliverables")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0


def test_list_deliverables_returns_summaries(temp_substrate):
    client = _client(temp_substrate)
    for title in ("Memo A", "Memo B", "Memo C"):
        r = client.post("/deliverables", json={
            "title": title, "deliverable_kind": "research_memo",
        })
        assert r.status_code == 201
    resp = client.get("/deliverables")
    body = resp.json()
    assert body["count"] == 3
    titles = {d["title"] for d in body["deliverables"]}
    assert titles == {"Memo A", "Memo B", "Memo C"}


# ─────────────────────────────────────────────────────────────────────
# 3. POST /sections + GET /deliverables/{id}
# ─────────────────────────────────────────────────────────────────────


def test_post_section_then_get_deliverable_includes_section(temp_substrate):
    client = _client(temp_substrate)
    d = client.post("/deliverables", json={
        "title": "Memo", "deliverable_kind": "research_memo",
    }).json()
    did = d["deliverable_id"]

    s = client.post("/sections", json={
        "deliverable_id": did, "section_index": 0, "title": "Intro",
    })
    assert s.status_code == 201
    sid = s.json()["section_id"]
    assert sid.startswith("sec-")

    detail = client.get(f"/deliverables/{did}").json()
    assert len(detail["sections"]) == 1
    assert detail["sections"][0]["section_id"] == sid
    assert detail["sections"][0]["title"] == "Intro"
    assert detail["sections"][0]["block_count"] == 0


def test_post_section_for_unknown_deliverable_404(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/sections", json={
        "deliverable_id": "dlv-does-not-exist",
        "section_index": 0,
        "title": "x",
    })
    assert resp.status_code == 404


def test_get_deliverable_404(temp_substrate):
    client = _client(temp_substrate)
    resp = client.get("/deliverables/dlv-nope")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# 4. POST /sections/attach-block
# ─────────────────────────────────────────────────────────────────────


def test_attach_block_to_section_increments_block_count(temp_substrate):
    client = _client(temp_substrate)
    d = client.post("/deliverables", json={
        "title": "Memo", "deliverable_kind": "research_memo",
    }).json()
    s = client.post("/sections", json={
        "deliverable_id": d["deliverable_id"], "section_index": 0,
        "title": "Intro",
    }).json()

    r = client.post("/sections/attach-block", json={
        "section_id": s["section_id"],
        "block_kind": "insight",
        "block_id": "node-substrate-001",
        "block_index": 0,
    })
    assert r.status_code == 202

    detail = client.get(f"/deliverables/{d['deliverable_id']}").json()
    assert detail["sections"][0]["block_count"] == 1


def test_attach_block_unknown_section_404(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/sections/attach-block", json={
        "section_id": "sec-nope",
        "block_kind": "insight",
        "block_id": "node-x",
        "block_index": 0,
    })
    assert resp.status_code == 404


def test_attach_block_invalid_kind_422(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/sections/attach-block", json={
        "section_id": "sec-x",
        "block_kind": "not_a_real_kind",
        "block_id": "node-x",
        "block_index": 0,
    })
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# 5. POST /voice-notes/ingest
# ─────────────────────────────────────────────────────────────────────


_LONG_TRANSCRIPT = (
    "I want to think about how the substrate's recursive note-taking "
    "behavior actually compounds. The naive view is that each step "
    "adds linear value. But the actual mechanism is multiplicative."
)


def test_post_voice_note_ingest_happy(temp_substrate):
    client = _client(temp_substrate)
    r = client.post("/voice-notes/ingest", json={
        "transcript": _LONG_TRANSCRIPT,
        "duration_seconds": 60.0,
        "language": "en",
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "ingested"
    assert body["document_id"].startswith("doc-vn-")
    assert body["chunks_written"] >= 1


def test_post_voice_note_ingest_short_skipped(temp_substrate):
    client = _client(temp_substrate)
    r = client.post("/voice-notes/ingest", json={
        "transcript": "Too short.",
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "skipped"
    assert body["skipped_reason"] == "low_word_count"


def test_post_voice_note_empty_rejected(temp_substrate):
    client = _client(temp_substrate)
    r = client.post("/voice-notes/ingest", json={
        "transcript": "",
    })
    assert r.status_code == 422

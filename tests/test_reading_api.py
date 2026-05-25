"""DRW SPR-10 transport — the reading-surface REST API.

Exercises the wired router via create_app over a tmp DB: a document ingested
(SPR-08) + distilled (SPR-03) is served with its content-anchored notes;
editing creates a version preserving the original; challenging a note refines
it in place or escalates; document-scoped gaps are graph-grounded.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import pytest

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
import interfaces.research.api.reading_routes as rr


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _FakeDistiller:
    def __init__(self, insights, questions):
        self._i, self._q = insights, questions

    def distill(self, text, *, source_event_ids=(), context=""):
        from roles.note_taker.distill import Distillation, DistilledQuestion
        from roles.note_taker.parser import ExtractedNote
        return Distillation(
            insights=[ExtractedNote(note_id=f"n{i}", text=t, confidence="moderate",
                                    source_event_ids=("ev",)) for i, t in enumerate(self._i)],
            questions=[DistilledQuestion(text=q) for q in self._q],
        )


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="reading-api-test-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr(rr, "_embedding_provider", lambda: _StubEmbedding())
    # Ensure schema + the insight/question node types are migrated.
    from substrate.graph.schema import init_database_at_path
    init_database_at_path(db)
    return {"db": db, "events": os.path.join(tmpdir, "events")}


def _ingest_and_distill(env, raw_text, insights, questions):
    """Ingest a document (SPR-08) + run the SPR-03 note pass over it, so the
    reading surface has a document with anchored notes."""
    from runtime.db_lock import connect_write
    from substrate.research_bridge.ingest_file import ingest_file, distill_ingested_document
    con = connect_write(env["db"], purpose="seed")
    try:
        result = ingest_file(con, data=raw_text, filename="doc.md", investigation_id="inv-read")
    finally:
        con.close()

    async def _run():
        return await distill_ingested_document(
            result, investigation_id="inv-read",
            distiller=_FakeDistiller(insights, questions),
            db_path=env["db"], events_dir=env["events"],
        )
    asyncio.run(_run())
    return result.document_id


@pytest.fixture
def client(env):
    return TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))


# --------------------------------------------------------------------------
# Document + notes
# --------------------------------------------------------------------------


def test_get_document_with_raw_text(client, env):
    raw = "# Report\n\nGPUs gate model scale. Capital is abundant in this market."
    doc_id = _ingest_and_distill(env, raw, ["GPUs gate model scale."], [])
    r = client.get(f"/reading/documents/{doc_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "GPUs gate model scale" in body["raw_text"]
    assert body["versions"][0]["version"] == 1


def test_document_notes_are_content_anchored(client, env):
    raw = "# Report\n\nGPUs gate model scale. Capital is abundant in this market."
    doc_id = _ingest_and_distill(env, raw, ["GPUs gate model scale."], ["What is the moat?"])
    r = client.get(f"/reading/documents/{doc_id}/notes")
    assert r.status_code == 200
    notes = r.json()["notes"]
    kinds = {n["kind"] for n in notes}
    assert "insight" in kinds and "question" in kinds
    # The insight anchors to its source-chunk TEXT (locatable in raw_text by
    # WHITESPACE-NORMALIZED content match — not a fragile offset, and robust
    # to the paragraph-join reflow + later edits).
    def _norm(s: str) -> str:
        return " ".join(s.split())
    insight = next(n for n in notes if n["kind"] == "insight")
    assert insight["anchors"]
    assert all(_norm(anchor) in _norm(raw) for anchor in insight["anchors"])


def test_get_document_404(client):
    assert client.get("/reading/documents/nope").status_code == 404


# --------------------------------------------------------------------------
# Versioning — edit preserves the original
# --------------------------------------------------------------------------


def test_edit_creates_version_preserving_original(client, env):
    raw = "# Doc\n\noriginal body text"
    doc_id = _ingest_and_distill(env, raw, ["original body text"], [])
    r = client.post(f"/reading/documents/{doc_id}/versions",
                    json={"new_text": "# Doc\n\nedited body text"})
    assert r.status_code == 200, r.text
    new_id = r.json()["new_document_id"]
    assert new_id != doc_id and not r.json()["unchanged"]
    # Original preserved.
    assert "original body text" in client.get(f"/reading/documents/{doc_id}").json()["raw_text"]
    assert "edited body text" in client.get(f"/reading/documents/{new_id}").json()["raw_text"]


def test_edit_to_identical_text_is_noop(client, env):
    raw = "# Doc\n\nsame text"
    doc_id = _ingest_and_distill(env, raw, ["same text"], [])
    r = client.post(f"/reading/documents/{doc_id}/versions", json={"new_text": raw})
    assert r.json()["unchanged"] is True and r.json()["new_document_id"] == doc_id


# --------------------------------------------------------------------------
# Living-note challenge — refine in place, or escalate to spin
# --------------------------------------------------------------------------


def test_challenge_with_resolution_refines_in_place(client, env):
    raw = "# Doc\n\nAcme is a small bakery."
    doc_id = _ingest_and_distill(env, raw, ["Acme is a small bakery."], [])
    node_id = client.get(f"/reading/documents/{doc_id}/notes").json()["notes"][0]["node_id"]
    r = client.post(f"/reading/notes/{node_id}/challenge",
                    json={"challenge_text": "It has 500 staff", "document_id": doc_id,
                          "resolution": "Acme is a mid-sized bakery chain."})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True
    assert r.json()["new_text"] == "Acme is a mid-sized bakery chain."


def test_challenge_without_resolution_escalates(client, env):
    raw = "# Doc\n\nMargins are healthy."
    doc_id = _ingest_and_distill(env, raw, ["Margins are healthy."], [])
    node_id = client.get(f"/reading/documents/{doc_id}/notes").json()["notes"][0]["node_id"]
    r = client.post(f"/reading/notes/{node_id}/challenge",
                    json={"challenge_text": "Source for margins?", "document_id": doc_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalated"] is True
    assert body["reserved_child_investigation_id"]   # the spin-research seam


# --------------------------------------------------------------------------
# Document-scoped gaps — graph-grounded
# --------------------------------------------------------------------------


def test_document_gaps_are_scoped_and_grounded(client, env):
    raw = "# Doc\n\nA claim worth questioning."
    # An open question (no resolved_by) anchored to the doc → an unanswered gap.
    doc_id = _ingest_and_distill(env, raw, [], ["Why is this the case?"])
    r = client.get(f"/reading/documents/{doc_id}/gaps")
    assert r.status_code == 200
    gaps = r.json()["gaps"]
    # Every surfaced gap traces to a node anchored to THIS document.
    doc_note_ids = {n["node_id"] for n in client.get(f"/reading/documents/{doc_id}/notes").json()["notes"]}
    for g in gaps:
        assert set(g["backing_node_ids"]) & doc_note_ids   # grounded + scoped

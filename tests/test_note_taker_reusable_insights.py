"""Note-taker deposits must be assemblable + reusable knowledge units."""

from __future__ import annotations

from pathlib import Path

import duckdb

from processing.embedding import default_embedding_provider
from runtime.db_lock import connect_write
from substrate.context_pack.knowledge_reuse import (
    assemble_context_pack_with_reuse,
    retrieve_prior_units,
)
from substrate.event_log import emit_typed, iter_physical_events
from substrate.flywheel.investigation_start_reuse import (
    maybe_reuse_prior_knowledge_at_start,
)
from substrate.flywheel.reuse_gate import filter_reusable
from substrate.graph.insight_question import (
    knowledge_unit_of,
    promote_from_note_event,
)
from substrate.graph.retrieval_substrate import make_substrate_from_con
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import (
    EvidenceRetrieveDeliveredPayload,
    NoteEmergedPayload,
)

DOC_ID = "doc-book-test"
NOTE_TEXT = (
    "The page-1 verification path is blocked because the retrieved "
    "'page 1' chunks are placeholders in this corpus."
)
EVIDENCE_ANSWER = (
    "The page-1 verification path is blocked because the retrieved "
    "'page 1' chunks are placeholders rather than full facsimile text."
)
CHUNK_TEXT = (
    "## Page 1\n\n"
    "Four score and seven years ago our fathers brought forth on this "
    "continent, a new nation, conceived in Liberty, and dedicated to the "
    "proposition that all men are created equal. Now we are engaged in a "
    "great civil war, testing whether that nation, or any nation so "
    "conceived and so dedicated, can long endure. We are met on a great "
    "battle-field of that war. We have come to dedicate a portion of that "
    "field, as a final resting place for those who here gave their lives "
    "that that nation might live. It is altogether fitting and proper that "
    "we should do this. The page-1 verification path is blocked because "
    "the retrieved page 1 chunks are placeholders in some corpora."
)


def _seed_doc(db: str) -> None:
    emb = default_embedding_provider()
    with connect_write(db, purpose="test/seed-doc") as con:
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
            [DOC_ID, "Gettysburg fixture", "public_domain"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
            [
                "chunk-test-gettysburg",
                DOC_ID,
                0,
                CHUNK_TEXT,
                emb.encode(CHUNK_TEXT),
                64,
            ],
        )


def _promote_grounded_note(db: str, events: Path, inv: str) -> str:
    ev_id = emit_typed(
        inv,
        EvidenceRetrieveDeliveredPayload(
            sub_question="Is page 1 verification blocked by placeholders?",
            answer=EVIDENCE_ANSWER,
            supporting_claims=[],
            evidentiary_gaps=[],
            insufficient_evidence=True,
        ),
        events_dir=str(events),
        role="evidence_retriever",
        document_id=DOC_ID,
    )
    note_eid = emit_typed(
        inv,
        NoteEmergedPayload(
            note_id="n-test-1",
            note_text=NOTE_TEXT,
            source_event_ids=[ev_id],
            confidence="high",
            node_id=None,
        ),
        events_dir=str(events),
        role="note_taker",
        document_id=DOC_ID,
        parent_event_id=ev_id,
    )
    note_event = next(
        e
        for e in iter_physical_events(inv, events_dir=str(events))
        if e.get("event_id") == note_eid
    )
    nid = promote_from_note_event(
        note_event,
        enabled=True,
        emit_graph_events=False,
        events_dir=str(events),
    )
    assert nid
    return nid


def test_promote_from_note_grounds_and_passes_reuse_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    init_database_at_path(db)
    _seed_doc(db)

    nid = _promote_grounded_note(db, events, "inv-prior-notes")

    with connect_write(db, purpose="test/ku") as con:
        unit = knowledge_unit_of(con, nid, score_groundedness=True)
    assert unit.provenance.source_document_id == DOC_ID
    assert unit.provenance.chunk_id
    assert unit.groundedness_score is not None
    assert unit.groundedness_score >= 0.5
    assert unit.servability.serves_full_text is True

    con = duckdb.connect(db)
    try:
        sub = make_substrate_from_con(
            "brute_force", con, model=default_embedding_provider()
        )
        units = retrieve_prior_units(
            sub, question_text="Why is page-1 verification blocked by placeholders?"
        )
        assert units, "expected retrieved units"
        admitted, decisions = filter_reusable(
            units, investigation_id="inv-reuse", owner=True
        )
        assert admitted, f"expected admitted; decisions={[(getattr(d,'reason',d)) for d in decisions]}"
        result = assemble_context_pack_with_reuse(
            role="decomposer",
            investigation_id="inv-reuse-b",
            layers=[],
            units=units,
            events_dir=str(events),
            owner=True,
        )
        assert result.injected, "expected non-empty inject"
    finally:
        con.close()


def test_maybe_reuse_start_injects_after_grounded_promote(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    init_database_at_path(db)
    _seed_doc(db)
    _promote_grounded_note(db, events, "inv-a")

    eid = maybe_reuse_prior_knowledge_at_start(
        investigation_id="inv-b",
        question_text="Why is page-1 verification blocked by placeholders?",
        db_path=db,
        events_dir=str(events),
    )
    assert eid
    rows = list(iter_physical_events("inv-b", events_dir=str(events)))
    reused = [r for r in rows if r.get("action_type") == "knowledge.reused"]
    assert len(reused) == 1
    ids = (reused[0].get("payload") or {}).get("reused_unit_ids") or []
    assert ids, f"expected non-empty reused_unit_ids, got {reused[0].get('payload')}"

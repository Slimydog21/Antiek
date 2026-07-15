"""Read SPR-07 M3 — the in-book FloatMenu NOTE becomes a searchable graph node.

The write-then-search round-trip M3 demands:

    highlight in-book → FloatMenu Note (marginalia.noted) → the note becomes a
    USER-sourced per-book insight node edged to the document → a later
    block_search / per-book query returns it.

Before this, ``marginalia.noted`` was never promoted, so the in-book note was
neither searchable (block_search) nor a graph node. These tests pin the fix
AND the §9 invariant: the promoted node carries ``source_kind="user"`` and is
never conflated with a model-emerged insight (which carries no source_kind).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.event_log import emit_typed
from substrate.graph import insight_question as iq
from substrate.graph.backfill_insight_question import backfill
from substrate.graph.insight_question import (
    insight_node_id,
    promote_from_marginalia_event,
    promote_from_note_event,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import MarginaliaNotedPayload
from substrate.write.block_search import search_blocks


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[: self.dimension]]


@pytest.fixture(autouse=True)
def _hash_embeddings():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def graph_env(monkeypatch):
    """Temp graph DB + isolated event dir, with the promotion path's default
    db pointed at the temp DB (so the con=None path never touches prod). Seeds
    one book document + a chunk so the round-trip can resolve a real book."""
    d = tempfile.mkdtemp()
    db_path = os.path.join(d, "graph.duckdb")
    events_dir = os.path.join(d, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setattr(iq, "graph_db_path", lambda: db_path)
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="test/seed") as con:
        insert_document(con, document_id="book-1", source_tier=2,
                        document_type="book", title="A Book on Moats")
        chunk_id = insert_chunk(con, document_id="book-1", chunk_index=0,
                                text="provenance is the moat")
    return {"db_path": db_path, "events_dir": events_dir, "chunk_id": chunk_id}


def _marginalia_event(*, note_text, note_id="mn-1", excerpt="provenance is the moat",
                      document_id="book-1", chunk_id=None, event_id="ev-mn-1",
                      derived_grounding=None):
    """A marginalia.noted event row as the promotion path receives it (the
    on-disk dict shape: action_type + payload + envelope fields)."""
    return {
        "event_id": event_id,
        "investigation_id": "read-book-1",
        "document_id": document_id,
        "action_type": "marginalia.noted",
        "payload": {
            "action_type": "marginalia.noted",
            "note_id": note_id,
            "note_text": note_text,
            "excerpt": excerpt,
            "source_kind": "user",
            "chunk_id": chunk_id,
            **(derived_grounding or {}),
        },
    }


# ── M3 — marginalia.noted → user-sourced per-book node ──────────────────


def test_marginalia_promotes_to_user_sourced_insight_node(graph_env):
    nid = promote_from_marginalia_event(
        _marginalia_event(note_text="The moat is provenance, not the model."),
        enabled=True,
    )
    assert nid == insight_node_id("The moat is provenance, not the model.")
    con = connect_read(graph_env["db_path"])
    try:
        row = con.execute(
            "SELECT node_type, metadata FROM nodes WHERE node_id=?", [nid]
        ).fetchone()
        assert row is not None
        assert row[0] == "insight"
        meta = json.loads(row[1])
        # §9 — the node is tagged user-sourced, distinguishable from a
        # model-emerged insight (which carries no source_kind).
        assert meta["source_kind"] == "user"
        # Grounded on its book (the document edge intent — documents are not
        # nodes, so grounding rides node metadata + the chunk reference).
        assert meta["source_document_id"] == "book-1"
        assert meta["origin_note_id"] == "mn-1"
        assert meta["excerpt"] == "provenance is the moat"
    finally:
        con.close()


def test_marginalia_promotion_preserves_complete_derived_revision_grounding(graph_env):
    grounding = {
        "derived_revision_id": "rev_" + "a" * 32,
        "derived_content_sha256": "b" * 64,
        "derived_generation": 7,
    }
    nid = promote_from_marginalia_event(
        _marginalia_event(note_text="This is grounded.", derived_grounding=grounding),
        enabled=True,
    )
    with connect_read(graph_env["db_path"]) as con:
        row = con.execute("SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()
    assert row is not None
    metadata = json.loads(row[0])
    assert {key: metadata[key] for key in grounding} == grounding


def test_marginalia_promotion_drops_incomplete_derived_grounding(graph_env):
    nid = promote_from_marginalia_event(
        _marginalia_event(
            note_text="Do not invent provenance.",
            derived_grounding={"derived_revision_id": "rev_" + "a" * 32},
        ),
        enabled=True,
    )
    with connect_read(graph_env["db_path"]) as con:
        row = con.execute("SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()
    assert row is not None
    metadata = json.loads(row[0])
    assert "derived_revision_id" not in metadata


def test_marginalia_is_opt_in(graph_env):
    assert promote_from_marginalia_event(
        _marginalia_event(note_text="x"), enabled=False
    ) is None
    con = connect_read(graph_env["db_path"])
    try:
        assert con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='insight'"
        ).fetchone()[0] == 0
    finally:
        con.close()


def test_marginalia_node_distinct_from_model_emerged(graph_env):
    """§9 — a user marginalia note and a model-distilled note are never
    conflated: the user node carries source_kind 'user', the model node
    carries none (its absence IS 'model')."""
    user_nid = promote_from_marginalia_event(
        _marginalia_event(note_text="User: scale gates margin."),
        enabled=True,
    )
    model_nid = promote_from_note_event(
        {"event_id": "ev2", "investigation_id": "inv1",
         "payload": {"note_text": "Model: scale lowers unit cost.",
                     "note_id": "n-model", "confidence": "high"}},
        enabled=True,
    )
    con = connect_read(graph_env["db_path"])
    try:
        um = json.loads(con.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [user_nid]).fetchone()[0])
        mm = json.loads(con.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [model_nid]).fetchone()[0])
        assert um.get("source_kind") == "user"
        assert "source_kind" not in mm   # model-emerged carries no user label
    finally:
        con.close()


def test_marginalia_dedups_on_normalized_text(graph_env):
    a = promote_from_marginalia_event(
        _marginalia_event(note_text="Provenance is the moat.", event_id="e1"),
        enabled=True,
    )
    b = promote_from_marginalia_event(
        _marginalia_event(note_text="  provenance   IS the  Moat.  ",
                          note_id="mn-2", event_id="e2"),
        enabled=True,
    )
    assert a == b
    con = connect_read(graph_env["db_path"])
    try:
        assert con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='insight'"
        ).fetchone()[0] == 1
    finally:
        con.close()


# ── M3 — the write-then-search ROUND TRIP ───────────────────────────────


def test_roundtrip_note_then_search_returns_per_book_node(graph_env):
    """The M3 round-trip: an in-book NOTE → a node → a later search returns it,
    and a per-book filter returns it grounded on its book — even with NO chunk
    anchor (the realistic reader-client case: book detail exposes no chunk id)."""
    nid = promote_from_marginalia_event(
        _marginalia_event(
            note_text="The defensible moat here is provenance over the corpus.",
            chunk_id=None,  # reader client has no chunk id this sprint (FIX 2)
        ),
        enabled=True,
    )
    con = connect_read(graph_env["db_path"])
    try:
        # 1) a free-text search returns the per-book note.
        hits = search_blocks(con, query="provenance moat", limit=10)
        ids = [h.node_id for h in hits]
        assert nid in ids
        # 2) a per-book filter returns it, resolved to its book via the
        #    node-metadata grounding (no chunk anchor needed).
        per_book = search_blocks(con, query="", source_document_id="book-1", limit=10)
        per_book_hit = next((h for h in per_book if h.node_id == nid), None)
        assert per_book_hit is not None
        assert per_book_hit.document_id == "book-1"
        assert per_book_hit.document_title == "A Book on Moats"
    finally:
        con.close()


def test_roundtrip_with_chunk_anchor_resolves_book(graph_env):
    """When the host DOES resolve a chunk (the documented follow-up path),
    the node anchors to the chunk and search resolves the book through it."""
    nid = promote_from_marginalia_event(
        _marginalia_event(
            note_text="A chunk-anchored marginalia insight.",
            chunk_id=graph_env["chunk_id"],
        ),
        enabled=True,
    )
    con = connect_read(graph_env["db_path"])
    try:
        meta = json.loads(con.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()[0])
        assert meta["chunk_id"] == graph_env["chunk_id"]
        hits = search_blocks(con, query="", source_document_id="book-1", limit=10)
        assert nid in {h.node_id for h in hits}
    finally:
        con.close()


# ── M3 — backfill catches historical in-book notes ──────────────────────


def test_backfill_promotes_marginalia_events(graph_env):
    """A marginalia.noted event already on the log (no on-emit promotion) is
    caught by the backfill, so the safety net holds."""
    emit_typed(
        "read-book-1",
        MarginaliaNotedPayload(
            note_id="mn-bf", note_text="A backfilled in-book note about moats.",
            excerpt="provenance is the moat", chunk_id=None),
        role="reader", document_id="book-1", events_dir=graph_env["events_dir"],
    )
    report = backfill(
        db_path=graph_env["db_path"], events_dir=graph_env["events_dir"],
        embedding_provider=_FakeEmbedding(),
    )
    assert report.marginalia_scanned == 1
    assert report.marginalia_promoted == 1

    # idempotent: a second backfill promotes nothing new. Run it BEFORE
    # opening a read connection — a read-only handle held open while a
    # write connection opens the same DuckDB file is a config conflict.
    report2 = backfill(
        db_path=graph_env["db_path"], events_dir=graph_env["events_dir"],
        embedding_provider=_FakeEmbedding(),
    )
    assert report2.marginalia_promoted == 0
    assert report2.marginalia_already_present == 1

    nid = insight_node_id("A backfilled in-book note about moats.")
    con = connect_read(graph_env["db_path"])
    try:
        meta = json.loads(con.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()[0])
        assert meta["source_kind"] == "user"
        assert meta["source_document_id"] == "book-1"
    finally:
        con.close()

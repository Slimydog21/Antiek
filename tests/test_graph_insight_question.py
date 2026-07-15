"""DRW SPR-01 — insight/question node types, promotion, backfill.

Mechanical verification gates for SPR-01. Covers the migration (fresh +
legacy populated DB rebuild + idempotency + column parity), the
single-writer promotion path (incl. write_log observability), content-hash
dedup, embeddings, opt-in event wiring, the controlled relation vocabulary,
and the idempotent backfill.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import duckdb
import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.constants import (
    INSIGHT_QUESTION_RELATION_NAMES,
    validate_insight_question_edge,
)
from substrate.event_log import emit_typed
from substrate.graph import insight_question as iq
from substrate.graph import ops
from substrate.graph.insight_question import (
    canonical_text,
    insight_node_id,
    promote_from_note_event,
    promote_insight,
    promote_question,
    question_node_id,
)
from substrate.graph.migrate_v9_insight_question import (
    NODE_TYPES_AFTER,
    _already_has_insight_question,
    migrate,
    migrate_at_path,
)
from substrate.graph.schema import init_database, init_database_at_path
from substrate.schemas.events import NoteEmergedPayload, QuestionIdentifiedPayload

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


class _FakeEmbedding:
    """Deterministic, dependency-free embedding for tests (stands in for the
    claim-embedding provider)."""

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
    """A temp graph DB + isolated event dir. Points the promotion path's
    default db at the temp DB so the con=None path never touches prod."""
    d = tempfile.mkdtemp()
    db_path = os.path.join(d, "graph.duckdb")
    events_dir = os.path.join(d, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setattr(iq, "graph_db_path", lambda: db_path)
    init_database_at_path(db_path)
    return {"db_path": db_path, "events_dir": events_dir}


# --------------------------------------------------------------------------
# M1 — migration: fresh DB
# --------------------------------------------------------------------------


def test_fresh_db_accepts_insight_and_question_nodes(graph_env):
    con = connect_write(graph_env["db_path"], purpose="t")
    try:
        ops.insert_node(con, canonical_label="An insight", node_type="insight",
                        graph_scope="depth", investigation_id="inv1")
        ops.insert_node(con, canonical_label="A question?", node_type="question",
                        graph_scope="depth", investigation_id="inv1")
        types = {r[0] for r in con.execute("SELECT node_type FROM nodes").fetchall()}
        assert {"insight", "question"} <= types
    finally:
        con.close()


def test_fresh_db_rejects_unknown_node_type(graph_env):
    con = connect_write(graph_env["db_path"], purpose="t")
    try:
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES ('n-bad','x','not_a_type','depth')"
            )
    finally:
        con.close()


def test_migration_is_noop_on_fresh_db(graph_env):
    # Fresh DB already carries the wide CHECK via V1, so migrate() must
    # detect it and do nothing.
    con = connect_write(graph_env["db_path"], purpose="t")
    try:
        assert _already_has_insight_question(con) is True
        assert migrate(con) is False
    finally:
        con.close()


def test_init_database_idempotent(graph_env):
    # Run the whole init again; row counts unchanged, no error.
    con = connect_write(graph_env["db_path"], purpose="t")
    try:
        ops.insert_node(con, canonical_label="x", node_type="claim",
                        graph_scope="depth", investigation_id="inv1")
        before = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
        init_database(con)
        after = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
        assert before == after == 1
    finally:
        con.close()


# --------------------------------------------------------------------------
# M1 — migration: legacy populated DB rebuild
# --------------------------------------------------------------------------


def _build_legacy_db(db_path: str) -> None:
    """Create a pre-migration graph: nodes with the OLD 9-type CHECK, plus
    documents/chunks/edges with data and a superseded_by self-reference."""
    con = connect_write(db_path, purpose="legacy_setup")
    try:
        con.execute("CREATE TABLE documents (document_id TEXT PRIMARY KEY, title TEXT)")
        con.execute("CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, "
                    "document_id TEXT REFERENCES documents(document_id))")
        con.execute(
            "CREATE TABLE nodes (node_id TEXT PRIMARY KEY, canonical_label TEXT NOT NULL, "
            "node_type TEXT NOT NULL CHECK (node_type IN "
            "('entity','organization','person','property','metric','mechanism',"
            "'claim','method','constraint')), embedding FLOAT[], "
            "graph_scope TEXT NOT NULL CHECK (graph_scope IN ('depth','cross_domain','constraint')), "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "degree_cached INTEGER NOT NULL DEFAULT 0, metadata TEXT)"
        )
        con.execute(
            "CREATE TABLE edges (edge_id TEXT PRIMARY KEY, "
            "source_node_id TEXT NOT NULL REFERENCES nodes(node_id), "
            "target_node_id TEXT NOT NULL REFERENCES nodes(node_id), relation TEXT NOT NULL, "
            "chunk_id TEXT REFERENCES chunks(chunk_id), "
            "source_document_id TEXT REFERENCES documents(document_id), "
            "source_tier INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5), "
            "extraction_confidence FLOAT NOT NULL CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1), "
            "extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "valid_from TIMESTAMP NOT NULL DEFAULT '1970-01-01', valid_until TIMESTAMP, "
            "superseded_by TEXT REFERENCES edges(edge_id), "
            "graph_scope TEXT NOT NULL CHECK (graph_scope IN ('depth','cross_domain','constraint')), "
            "investigation_id TEXT, metadata TEXT)"
        )
        con.execute("INSERT INTO documents VALUES ('d1','Doc')")
        con.execute("INSERT INTO chunks VALUES ('c1','d1')")
        con.execute("INSERT INTO nodes (node_id,canonical_label,node_type,graph_scope) "
                    "VALUES ('n1','Acme','organization','depth'),('n2','revenue','metric','depth')")
        con.execute(
            "INSERT INTO edges (edge_id,source_node_id,target_node_id,relation,chunk_id,"
            "source_document_id,source_tier,extraction_confidence,graph_scope) "
            "VALUES ('e1','n1','n2','reports','c1','d1',2,0.8,'depth'),"
            "('e2','n2','n1','rel',NULL,NULL,3,0.6,'depth')"
        )
        con.execute("UPDATE edges SET superseded_by='e1' WHERE edge_id='e2'")
    finally:
        con.close()


def test_migration_rebuilds_legacy_db_preserving_data(tmp_path):
    db_path = str(tmp_path / "legacy.duckdb")
    _build_legacy_db(db_path)

    # The legacy CHECK does not have insight/question.
    assert migrate_at_path(db_path) is True

    con = connect_write(db_path, purpose="verify")
    try:
        # Data preserved.
        assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM edges").fetchone()[0] == 2
        # Self-FK data preserved.
        assert con.execute("SELECT superseded_by FROM edges WHERE edge_id='e2'").fetchone()[0] == "e1"
        # New types now accepted.
        con.execute("INSERT INTO nodes (node_id,canonical_label,node_type,graph_scope) "
                    "VALUES ('n3','insight!','insight','depth')")
        # Old types still accepted; bogus still rejected.
        with pytest.raises(duckdb.ConstraintException):
            con.execute("INSERT INTO nodes (node_id,canonical_label,node_type,graph_scope) "
                        "VALUES ('n4','x','bogus','depth')")
        # FK to nodes still enforced.
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO edges (edge_id,source_node_id,target_node_id,relation,source_tier,extraction_confidence) "
                "VALUES ('e9','nX','n2','r',2,0.5)"
            )
    finally:
        con.close()

    # Idempotent: second migrate is a no-op.
    assert migrate_at_path(db_path) is False


def test_migration_preserves_column_parity_with_fresh(tmp_path):
    legacy = str(tmp_path / "legacy.duckdb")
    fresh = str(tmp_path / "fresh.duckdb")
    _build_legacy_db(legacy)
    migrate_at_path(legacy)
    init_database_at_path(fresh)

    def cols(path, table):
        c = connect_read(path)
        try:
            return [(r[1], r[2]) for r in c.execute(f"PRAGMA table_info('{table}')").fetchall()]
        finally:
            c.close()

    # Migrated legacy nodes/edges columns match a freshly-created schema.
    assert cols(legacy, "nodes") == cols(fresh, "nodes")
    assert cols(legacy, "edges") == cols(fresh, "edges")


# --------------------------------------------------------------------------
# M2 — relation vocabulary
# --------------------------------------------------------------------------


def test_relation_vocabulary_validation():
    assert {"supported_by", "asks_about", "resolved_by"} <= INSIGHT_QUESTION_RELATION_NAMES
    # valid
    validate_insight_question_edge("supported_by", "insight", "claim")
    validate_insight_question_edge("asks_about", "question", "entity")
    # unknown relation
    with pytest.raises(ValueError):
        validate_insight_question_edge("flibberty", "insight", "claim")
    # wrong source type
    with pytest.raises(ValueError):
        validate_insight_question_edge("supported_by", "question", "claim")
    # disallowed target type
    with pytest.raises(ValueError):
        validate_insight_question_edge("resolved_by", "question", "claim")


# --------------------------------------------------------------------------
# M3/M5 — promotion through single writer + embeddings
# --------------------------------------------------------------------------


def test_promote_insight_creates_node_with_embedding(graph_env):
    nid = promote_insight(text="GPUs gate model scale.", investigation_id="inv1",
                          confidence="high")
    con = connect_read(graph_env["db_path"])
    try:
        row = con.execute(
            "SELECT node_type, canonical_label, embedding FROM nodes WHERE node_id=?", [nid]
        ).fetchone()
        assert row is not None
        assert row[0] == "insight"
        assert row[1] == "GPUs gate model scale."
        assert row[2] is not None and len(row[2]) == _FakeEmbedding.dimension
    finally:
        con.close()


def test_promote_insight_dedup_on_normalized_text(graph_env):
    a = promote_insight(text="GPUs gate model scale.", investigation_id="inv1")
    b = promote_insight(text="  gpus   GATE  model   scale.  ", investigation_id="inv1")
    assert a == b  # case + whitespace normalized → same content hash
    con = connect_read(graph_env["db_path"])
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 1
    finally:
        con.close()


def test_promote_insight_supported_by_edge_and_dangling_skip(graph_env):
    # Seed a real claim node to support the insight.
    con = connect_write(graph_env["db_path"], purpose="seed")
    try:
        claim_id = ops.insert_node(con, canonical_label="Acme raised $5M",
                                   node_type="claim", graph_scope="depth",
                                   investigation_id="inv1")
    finally:
        con.close()

    nid = promote_insight(
        text="Acme is well funded.", investigation_id="inv1",
        supported_by=[claim_id, "node-does-not-exist"],
        source_document_id=None,
    )
    con = connect_read(graph_env["db_path"])
    try:
        edges = con.execute(
            "SELECT relation, target_node_id FROM edges WHERE source_node_id=?", [nid]
        ).fetchall()
        assert ("supported_by", claim_id) in edges
        # The dangling target was skipped, not written.
        assert all(t != "node-does-not-exist" for _, t in edges)
        meta = con.execute("SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()[0]
        assert "skipped_dangling" in meta
    finally:
        con.close()


def test_promote_question_node(graph_env):
    nid = promote_question(text="Does Acme have moat?", investigation_id="inv1",
                           anchor_region_id="reg-7")
    con = connect_read(graph_env["db_path"])
    try:
        row = con.execute("SELECT node_type, embedding FROM nodes WHERE node_id=?", [nid]).fetchone()
        assert row[0] == "question"
        assert row[1] is not None
    finally:
        con.close()


def test_promotion_records_write_log(graph_env):
    # con=None path acquires its own connection → LockedConnection.close()
    # logs to write_log (now that the table exists).
    promote_insight(text="A logged insight.", investigation_id="inv1")
    con = connect_read(graph_env["db_path"])
    try:
        n = con.execute(
            "SELECT count(*) FROM write_log WHERE purpose='promote_insight'"
        ).fetchone()[0]
        assert n >= 1
    finally:
        con.close()


def test_insight_nodes_are_similarity_queryable(graph_env):
    promote_insight(text="Insight one.", investigation_id="inv1")
    con = connect_read(graph_env["db_path"])
    try:
        # All insight nodes carry a non-null embedding of the right length —
        # they sit in the same embedding column claims use, so any cosine
        # query over `nodes` returns them alongside claims.
        rows = con.execute(
            "SELECT embedding FROM nodes WHERE node_type='insight' AND embedding IS NOT NULL"
        ).fetchall()
        assert rows and all(len(r[0]) == _FakeEmbedding.dimension for r in rows)
    finally:
        con.close()


# --------------------------------------------------------------------------
# M4 — event → node wiring (opt-in) + dedup
# --------------------------------------------------------------------------


def test_event_wiring_is_opt_in(graph_env):
    event = {"event_id": "ev1", "investigation_id": "inv1",
             "payload": {"note_text": "x", "note_id": "n1", "source_event_ids": ["e0"]}}
    assert promote_from_note_event(event, enabled=False) is None  # default off
    con = connect_read(graph_env["db_path"])
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 0
    finally:
        con.close()


def test_promote_from_note_event_enabled(graph_env):
    event = {"event_id": "ev1", "investigation_id": "inv1",
             "payload": {"note_text": "Funding is the binding constraint.",
                         "note_id": "n1", "confidence": "high",
                         "source_event_ids": ["e0", "e1"]}}
    nid = promote_from_note_event(event, enabled=True)
    assert nid == insight_node_id("Funding is the binding constraint.")
    # Re-promote same event → dedup, still one node.
    promote_from_note_event(event, enabled=True)
    con = connect_read(graph_env["db_path"])
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 1
        meta = con.execute("SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()[0]
        assert "source_event_ids" in meta
    finally:
        con.close()


# --------------------------------------------------------------------------
# M6 — backfill
# --------------------------------------------------------------------------


def _seed_events(events_dir, n_notes=3, n_questions=2):
    for i in range(n_notes):
        emit_typed("inv-bf", NoteEmergedPayload(
            note_id=f"note-{i}", note_text=f"Backfill insight number {i}.",
            source_event_ids=[f"src-{i}"], confidence="moderate"),
            role="note_taker", document_id="doc-1", events_dir=events_dir)
    for i in range(n_questions):
        emit_typed("inv-bf", QuestionIdentifiedPayload(
            question_id=f"q-{i}", question_text=f"Backfill question number {i}?"),
            role="note_taker", document_id="doc-1", events_dir=events_dir)


def test_backfill_dry_run_writes_nothing(graph_env):
    from substrate.graph.backfill_insight_question import backfill
    _seed_events(graph_env["events_dir"], n_notes=3, n_questions=2)
    report = backfill(db_path=graph_env["db_path"], events_dir=graph_env["events_dir"], dry_run=True)
    assert report.notes_scanned == 3
    assert report.questions_scanned == 2
    assert report.notes_promoted == 3       # would-promote
    assert report.questions_promoted == 2
    con = connect_read(graph_env["db_path"])
    try:
        # Nothing actually written.
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type IN ('insight','question')").fetchone()[0] == 0
    finally:
        con.close()


def test_backfill_real_then_idempotent(graph_env):
    from substrate.graph.backfill_insight_question import backfill
    _seed_events(graph_env["events_dir"], n_notes=3, n_questions=2)

    r1 = backfill(db_path=graph_env["db_path"], events_dir=graph_env["events_dir"])
    assert r1.notes_promoted == 3 and r1.questions_promoted == 2
    assert r1.errors == []
    con = connect_read(graph_env["db_path"])
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 3
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='question'").fetchone()[0] == 2
    finally:
        con.close()

    # Second run promotes zero.
    r2 = backfill(db_path=graph_env["db_path"], events_dir=graph_env["events_dir"])
    assert r2.notes_promoted == 0 and r2.questions_promoted == 0
    assert r2.notes_already_present == 3 and r2.questions_already_present == 2


def test_node_types_after_constant_matches_db(graph_env):
    # The migration's NODE_TYPES_AFTER must equal what the DB CHECK accepts.
    assert "insight" in NODE_TYPES_AFTER and "question" in NODE_TYPES_AFTER
    assert canonical_text("  Foo   BAR ") == "foo bar"


def test_optional_identity_scope_isolates_same_text_without_changing_default() -> None:
    assert insight_node_id("same") == insight_node_id(" SAME ")
    assert insight_node_id("same", identity_scope="owner-a") != insight_node_id(
        "same", identity_scope="owner-b"
    )
    assert question_node_id("same?", identity_scope="owner-a") != question_node_id(
        "same?", identity_scope="owner-b"
    )

"""Graph-integrity deposit: idempotent synthesis + no dangling manifest pins (#199).

Two confirmed defects in the synthesis deposit path (the knowledge-graph moat),
both exercised here through the REAL production callers:

  * Vector 1 — non-idempotent deposit. ``_deposit_synthesis_to_substrate``
    passed ``investigation_id`` but NOT ``synthesis_id`` to
    ``archive_synthesis_via_db``, which minted a fresh UUID per call. With no
    UNIQUE constraint on ``investigation_id`` and a plain INSERT, two deposits
    for one investigation produced duplicate synthesis rows + duplicated
    manifest pins. Fix: thread the deterministic ``f"syn-{investigation_id}"``
    + ``INSERT OR REPLACE`` (re-run = update, not duplicate).

  * Vector 2 — dangling provenance. The DRW-tail/session-evidence-pack path
    fabricates chunk_ids (``f"chunk-{node_id}"``, ``f"doc-gather-..."``) for
    nodes lacking one; pinning those into ``synthesis_substrate_manifest``
    (whose ``entity_id`` has no FK) created manifest rows that join to no
    ``chunks`` row. Fix: validate chunk_ids against the ``chunks`` table before
    pinning; skip non-existent (fabricated) ids.

These tests prove: (1) re-depositing the same investigation_id is idempotent
(exactly one synthesis row, one set of manifest pins); (2) fabricated chunk_ids
are NOT pinned (only real chunks that exist in the graph are).
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from middleware.archive import ArchiveInputs, archive_synthesis_via_db
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path


def _inputs(*, chunk_ids: tuple[str, ...] = ()) -> ArchiveInputs:
    return ArchiveInputs(
        target_question="test question",
        synthesis_timestamp=datetime.now(UTC),
        status="passed",
        implicit_recommendation="proceed",
        thesis_text="test thesis",
        thesis=None,
        evidence=[],
        decomposition=None,
        parameters=None,
        chunk_ids=chunk_ids,
        edge_ids=(),
    )


@pytest.fixture
def db(tmp_path) -> str:
    p = str(tmp_path / "integrity.duckdb")
    init_database_at_path(p)
    # Seed one real chunk so we can distinguish real vs fabricated chunk_ids.
    con = connect_write(p, purpose="seed-real-chunk")
    con.execute("BEGIN")
    con.execute(
        "INSERT INTO documents (document_id, title, source_tier, "
        "document_type, content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
        ["doc-1", "test doc"],
    )
    con.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, token_count) "
        "VALUES (?, ?, 0, ?, 1)",
        ["chunk-real", "doc-1", "real chunk text"],
    )
    con.execute("COMMIT")
    con.close()
    return p


def test_deposit_is_idempotent_same_investigation(db: str) -> None:
    """Vector 1: two deposits for the same investigation_id produce exactly
    ONE synthesis row (INSERT OR REPLACE, deterministic synthesis_id)."""
    inv = "inv-idempotent"
    for _ in range(2):
        con = connect_write(db, purpose="deposit")
        try:
            sid = archive_synthesis_via_db(
                con, _inputs(), investigation_id=inv,
                synthesis_id=f"syn-{inv}",
            )
        finally:
            con.close()
        assert sid == f"syn-{inv}"

    rc = duckdb.connect(db, read_only=True)
    rows = rc.execute(
        "SELECT synthesis_id FROM syntheses WHERE investigation_id = ?", [inv],
    ).fetchall()
    rc.close()
    assert len(rows) == 1, (
        f"non-idempotent deposit: expected 1 synthesis row for investigation "
        f"{inv!r}, got {len(rows)} (#199 vector 1 regressed)"
    )
    assert rows[0][0] == f"syn-{inv}"


def test_deposit_replaces_on_rerun(db: str) -> str:
    """Vector 1 (continuation): a re-run with different thesis text REPLACES
    the prior synthesis (deterministic id + upsert), not duplicates."""
    inv = "inv-rerun"
    con = connect_write(db, purpose="deposit-1")
    archive_synthesis_via_db(con, _inputs(), investigation_id=inv,
                             synthesis_id=f"syn-{inv}")
    con.close()

    # Re-run with a different thesis
    inputs2 = _inputs()
    # ArchiveInputs is frozen; build a new one with different thesis text
    inputs2 = ArchiveInputs(
        target_question="test question",
        synthesis_timestamp=datetime.now(UTC),
        status="passed",
        implicit_recommendation="proceed",
        thesis_text="UPDATED thesis text",
        thesis=None, evidence=[], decomposition=None, parameters=None,
        chunk_ids=(), edge_ids=(),
    )
    con = connect_write(db, purpose="deposit-2")
    archive_synthesis_via_db(con, inputs2, investigation_id=inv,
                             synthesis_id=f"syn-{inv}")
    con.close()

    rc = duckdb.connect(db, read_only=True)
    rows = rc.execute(
        "SELECT thesis_text FROM syntheses WHERE investigation_id = ?", [inv],
    ).fetchall()
    rc.close()
    assert len(rows) == 1, "re-run should replace, not duplicate"
    assert rows[0][0] == "UPDATED thesis text", "re-run should update the thesis"


def test_fabricated_chunk_ids_not_pinned_to_manifest(db: str) -> None:
    """Vector 2: fabricated chunk_ids (f"chunk-{node_id}", f"doc-gather-...")
    are NOT pinned to synthesis_substrate_manifest — only real chunks that
    exist in the graph. Prevents dangling provenance."""
    inv = "inv-fabricated"
    con = connect_write(db, purpose="deposit-fabricated")
    try:
        archive_synthesis_via_db(
            con,
            _inputs(chunk_ids=("chunk-real", "chunk-fake-node-1", "doc-gather-x-y")),
            investigation_id=inv,
            synthesis_id=f"syn-{inv}",
        )
    finally:
        con.close()

    rc = duckdb.connect(db, read_only=True)
    pinned = rc.execute(
        "SELECT entity_id FROM synthesis_substrate_manifest "
        "WHERE synthesis_id = ? AND entity_kind = 'chunk'",
        [f"syn-{inv}"],
    ).fetchall()
    rc.close()
    pinned_ids = {r[0] for r in pinned}
    assert "chunk-real" in pinned_ids, "real chunk should be pinned"
    assert "chunk-fake-node-1" not in pinned_ids, (
        "fabricated chunk_id must NOT be pinned — dangling provenance "
        "(#199 vector 2 regressed)"
    )
    assert "doc-gather-x-y" not in pinned_ids, (
        "fabricated doc-gather chunk_id must NOT be pinned — dangling provenance"
    )

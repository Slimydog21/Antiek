"""Graph-integrity deposit: idempotent synthesis + no dangling manifest pins (#199).

Two confirmed defects in the synthesis deposit path (the knowledge-graph moat),
both exercised here through the REAL production callers:

  * Vector 1 — non-idempotent deposit. ``_deposit_synthesis_to_substrate``
    passed ``investigation_id`` but NOT ``synthesis_id`` to
    ``archive_synthesis_via_db``, which minted a fresh UUID per call. With no
    UNIQUE constraint on ``investigation_id`` and a plain INSERT, two deposits
    for one investigation produced duplicate synthesis rows + duplicated
    manifest pins. Fix: thread the deterministic ``f"syn-{investigation_id}"``
    + immutable retry semantics (an exact replay is a no-op; changed content
    must use a new synthesis id).

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

import json
from dataclasses import replace
from datetime import UTC, datetime

import duckdb
import pytest

import middleware.archive.archive as archive_mod
from middleware.archive import (
    ArchiveInputs,
    SynthesisArchiveConflict,
    archive_synthesis_via_db,
    load_synthesis,
)
from runtime.db_lock import connect_write
from substrate.event_log import trajectory
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
    ONE immutable synthesis row under a deterministic synthesis_id."""
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


def test_deposit_rejects_changed_content_for_immutable_id(db: str) -> None:
    """A synthesis id identifies one snapshot, even before outcomes exist."""
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
    with (
        pytest.raises(SynthesisArchiveConflict),
        connect_write(db, purpose="deposit-2") as con,
    ):
        archive_synthesis_via_db(
            con, inputs2, investigation_id=inv, synthesis_id=f"syn-{inv}",
        )

    rc = duckdb.connect(db, read_only=True)
    rows = rc.execute(
        "SELECT thesis_text FROM syntheses WHERE investigation_id = ?", [inv],
    ).fetchall()
    rc.close()
    assert rows == [("test thesis",)]


def test_exact_redeposit_keeps_original_manifest_snapshot(db: str) -> None:
    inv = "inv-stable-manifest"
    sid = f"syn-{inv}"
    with connect_write(db, purpose="deposit-with-evidence") as con:
        archive_synthesis_via_db(
            con,
            _inputs(chunk_ids=("chunk-real",)),
            investigation_id=inv,
            synthesis_id=sid,
        )
    before = duckdb.connect(db, read_only=True)
    try:
        original = before.execute(
            "SELECT entity_kind, entity_id, pinned_at "
            "FROM synthesis_substrate_manifest WHERE synthesis_id = ?",
            [sid],
        ).fetchall()
    finally:
        before.close()
    with connect_write(db, purpose="deposit-retry") as con:
        archive_synthesis_via_db(
            con,
            _inputs(chunk_ids=("chunk-real",)),
            investigation_id=inv,
            synthesis_id=sid,
        )

    rc = duckdb.connect(db, read_only=True)
    try:
        manifest = rc.execute(
            "SELECT entity_kind, entity_id, pinned_at "
            "FROM synthesis_substrate_manifest "
            "WHERE synthesis_id = ?",
            [sid],
        ).fetchall()
    finally:
        rc.close()
    assert manifest == original

    with connect_write(db, purpose="delete-pinned-chunk") as con:
        con.execute("DELETE FROM chunks WHERE chunk_id = 'chunk-real'")
    with connect_write(db, purpose="deposit-retry-after-deletion") as con:
        assert archive_synthesis_via_db(
            con,
            _inputs(chunk_ids=("chunk-real",)),
            investigation_id=inv,
            synthesis_id=sid,
        ) == sid

    with (
        pytest.raises(SynthesisArchiveConflict, match="different manifest"),
        connect_write(db, purpose="deposit-changed-manifest") as con,
    ):
        archive_synthesis_via_db(
            con, _inputs(chunk_ids=()), investigation_id=inv, synthesis_id=sid,
        )


def test_failed_redeposit_preserves_previous_manifest(db: str) -> None:
    inv = "inv-restore-manifest"
    sid = f"syn-{inv}"
    with connect_write(db, purpose="deposit-original") as con:
        archive_synthesis_via_db(
            con,
            _inputs(chunk_ids=("chunk-real",)),
            investigation_id=inv,
            synthesis_id=sid,
        )

    invalid = replace(_inputs(chunk_ids=()), evidence="{not-json")
    with (
        pytest.raises(json.JSONDecodeError),
        connect_write(db, purpose="deposit-invalid-replacement") as con,
    ):
        archive_synthesis_via_db(
            con,
            invalid,
            investigation_id=inv,
            synthesis_id=sid,
        )

    rc = duckdb.connect(db, read_only=True)
    try:
        manifest = rc.execute(
            "SELECT entity_kind, entity_id, pinned_at "
            "FROM synthesis_substrate_manifest "
            "WHERE synthesis_id = ?",
            [sid],
        ).fetchall()
    finally:
        rc.close()
    assert [(kind, entity_id) for kind, entity_id, _ in manifest] == [
        ("chunk", "chunk-real")
    ]


def test_exact_redeposit_is_safe_after_outcome_fk_exists(db: str) -> None:
    inv = "inv-with-outcome"
    sid = f"syn-{inv}"
    inputs = _inputs(chunk_ids=("chunk-real",))
    with connect_write(db, purpose="deposit-original") as con:
        archive_synthesis_via_db(
            con, inputs, investigation_id=inv, synthesis_id=sid,
        )
        con.execute(
            "INSERT INTO outcomes (outcome_id, synthesis_id, observer) "
            "VALUES ('outcome-1', ?, 'operator')",
            [sid],
        )
    with connect_write(db, purpose="deposit-retry-after-outcome") as con:
        assert archive_synthesis_via_db(
            con, inputs, investigation_id=inv, synthesis_id=sid,
        ) == sid


def test_exact_redeposit_repairs_missing_archive_events(db: str, monkeypatch) -> None:
    inv = "inv-repair-events"
    sid = f"syn-{inv}"
    inputs = _inputs(chunk_ids=("chunk-real",))
    archived = archive_mod.emit_synthesis_archived
    manifested = archive_mod.emit_substrate_manifest_written
    monkeypatch.setattr(archive_mod, "emit_synthesis_archived", lambda **_: None)
    monkeypatch.setattr(archive_mod, "emit_substrate_manifest_written", lambda **_: None)
    with connect_write(db, purpose="deposit-without-events") as con:
        archive_synthesis_via_db(
            con, inputs, investigation_id=inv, synthesis_id=sid,
        )
    assert trajectory(inv) == []

    monkeypatch.setattr(archive_mod, "emit_synthesis_archived", archived)
    monkeypatch.setattr(archive_mod, "emit_substrate_manifest_written", manifested)
    with connect_write(db, purpose="deposit-event-repair") as con:
        archive_synthesis_via_db(
            con, inputs, investigation_id=inv, synthesis_id=sid,
        )
    assert {
        row["action_type"] for row in trajectory(inv) if row.get("synthesis_id") == sid
    } == {"synthesis.archived", "synthesis.substrate_manifest.written"}


def test_redeposit_repairs_manifest_event_with_missing_parent(db: str, monkeypatch) -> None:
    inv = "inv-repair-parent"
    sid = f"syn-{inv}"
    inputs = _inputs(chunk_ids=("chunk-real",))
    archived = archive_mod.emit_synthesis_archived
    monkeypatch.setattr(archive_mod, "emit_synthesis_archived", lambda **_: "missing")
    with connect_write(db, purpose="deposit-missing-parent") as con:
        archive_synthesis_via_db(
            con, inputs, investigation_id=inv, synthesis_id=sid,
        )
    monkeypatch.setattr(archive_mod, "emit_synthesis_archived", archived)
    with connect_write(db, purpose="deposit-parent-repair") as con:
        archive_synthesis_via_db(
            con, inputs, investigation_id=inv, synthesis_id=sid,
        )
    rows = [row for row in trajectory(inv) if row.get("synthesis_id") == sid]
    archive_id = next(
        row["event_id"] for row in rows if row["action_type"] == "synthesis.archived"
    )
    assert any(
        row["action_type"] == "synthesis.substrate_manifest.written"
        and row["parent_event_id"] == archive_id
        for row in rows
    )


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


def test_manifest_counts_equal_validated_durable_rows(db: str) -> None:
    with connect_write(db, purpose="seed-node") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('node-real', 'real node', 'claim', 'cross_domain')"
        )
    inputs = replace(
        _inputs(chunk_ids=("chunk-real", "chunk-real", "chunk-missing")),
        document_ids=("doc-1", "doc-1", "doc-missing"),
        node_ids=("node-real", "node-real", "node-missing"),
    )
    with connect_write(db, purpose="deposit-validated-manifest") as con:
        sid = archive_synthesis_via_db(
            con, inputs, investigation_id="inv-validated-manifest",
        )
    rc = duckdb.connect(db, read_only=True)
    try:
        loaded = load_synthesis(rc, sid)
        durable_count = rc.execute(
            "SELECT COUNT(*) FROM synthesis_substrate_manifest "
            "WHERE synthesis_id = ?",
            [sid],
        ).fetchone()[0]
    finally:
        rc.close()
    assert loaded.substrate_manifest_counts == {
        "document": 1, "chunk": 1, "node": 1, "edge": 0,
    }
    assert durable_count == 3

"""DuckDB backup/restore behavior and upstream self-reference regression guard.

The product's state is the DuckDB graph plus the append-only event log.
``infrastructure/ansible/templates/backup.sh.j2`` exports the graph and then
applies Antiek's schema normalizer before restore. This module pins the raw
upstream DuckDB defect and an unaffected positive control. The deployed
product-path proof lives in ``test_backup_normalize_schema.py``.

== The finding (root-caused 2026-07-03, glm-5.2 /infinite) ==

DuckDB's ``EXPORT DATABASE`` cannot round-trip a **self-referential foreign key**
— neither column-level (``parent TEXT REFERENCES t(id)``) nor table-level
(``FOREIGN KEY (parent) REFERENCES t(id)``). On export the self-ref FK is
silently dropped *and* a stray comma is left in the emitted ``schema.sql``
(a trailing ``, )`` for a lone self-ref; a double ``, ,`` when other table-level
constraints follow). Consequences for an **unnormalized raw DuckDB export**:

  1. ``IMPORT DATABASE`` **hard-fails** on the real schema. The full schema's
     ``edges`` and ``deliverable_sections`` tables (both carry a self-ref FK)
     produce malformed DDL, and IMPORT raises ``Parser Error: syntax error at
     or near ","`` at the first one.
  2. Where IMPORT does limp past a lone trailing comma, the self-ref FK is gone
     and no longer enforced — silent data-integrity loss on restore.

Only **two** self-ref FKs exist in the source schema (``edges.superseded_by`` →
``edges``; ``deliverable_sections.parent_section_id`` → ``deliverable_sections``).
Non-self-referential FKs, CHECK constraints, indexes, and data all round-trip
correctly (proven below).

SPR-02 resolved the product failure in #184 by normalizing only DuckDB's
definitively malformed top-level commas after export. The two advisory self-ref
FKs remain absent after restore (an upstream limitation), while data,
non-self-referential FKs, CHECK constraints, and indexes survive.

Tests: (1) pins the upstream self-ref-FK EXPORT bug on a minimal schema;
(2) explicitly characterizes the raw full-schema failure without misreporting
it as an unresolved product defect; (3) proves raw EXPORT/IMPORT is sound for a
self-ref-free schema. Hermetic on tmp_path; test-only; §16-clean.
"""

from __future__ import annotations

import os

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path

_BACKUP_EXPORT_OPTIONS = "(FORMAT PARQUET)"  # mirrors backup.sh.j2


def _export(src_db: str, export_dir: str) -> None:
    os.makedirs(export_dir, exist_ok=True)
    con = duckdb.connect(src_db, read_only=True)
    try:
        con.execute(f"EXPORT DATABASE '{export_dir}' {_BACKUP_EXPORT_OPTIONS}")
    finally:
        con.close()


def _import(export_dir: str, restored_db: str) -> None:
    con = duckdb.connect(restored_db)
    try:
        con.execute(f"IMPORT DATABASE '{export_dir}'")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 1. Root cause: DuckDB EXPORT/IMPORT drops a self-referential FK (minimal repro)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ddl_form", ["column", "table"])
def test_self_referential_fk_is_dropped_by_export_import(ddl_form: str, tmp_path) -> None:
    """A self-referential FK does not survive EXPORT→IMPORT (DuckDB 1.5.4).

    Parametrized over BOTH DDL forms because the real Antiek schema uses the
    column-level form (``superseded_by TEXT REFERENCES edges(edge_id)``) while a
    naive repro might use the table-level form — both are broken, and pinning
    both makes the characterization airtight against the real idiom.

    Note the two distinct failure shapes: a LONE self-ref FK exports a trailing
    ``, )`` that IMPORT *tolerates* (the FK is silently dropped, no error); a
    self-ref FK followed by sibling table-level constraints exports a mid-
    statement double comma ``, ,`` that makes IMPORT raise. This test exercises
    the lone (tolerated) shape; the full-schema negative control below exercises
    the raising shape. Green today; update when DuckDB fixes the upstream bug.
    """
    if ddl_form == "column":
        create_sql = "CREATE TABLE t(id INTEGER PRIMARY KEY, parent INTEGER REFERENCES t(id))"
    else:
        create_sql = ("CREATE TABLE t(id INTEGER PRIMARY KEY, parent INTEGER, "
                      "FOREIGN KEY (parent) REFERENCES t(id))")
    src = str(tmp_path / "src.db")
    exp = str(tmp_path / "export")
    restored = str(tmp_path / "restored.db")
    c = duckdb.connect(src)
    try:
        c.execute(create_sql)
        c.execute("INSERT INTO t VALUES (1, NULL)")
        # Baseline (codex review): the ORIGINAL db enforces the self-ref FK
        # (DuckDB does this by default for both column- and table-level forms,
        # verified as ConstraintException on a dangling parent). Without this
        # assertion the post-restore "accepted" check below could pass vacuously
        # if a future DuckDB relaxed enforcement — the contrast (rejected before
        # export, accepted after restore) is what proves the FK was dropped.
        with pytest.raises(duckdb.Error):
            c.execute("INSERT INTO t VALUES (2, 99999)")
    finally:
        c.close()
    _export(src, exp)
    _import(exp, restored)

    r = duckdb.connect(restored)
    try:
        # BUG: the self-ref FK is gone after round-trip — a dangling parent is
        # accepted on the restored DB (it would be rejected on the original).
        r.execute("INSERT INTO t VALUES (2, 99999)")
        rows = r.execute("SELECT id, parent FROM t ORDER BY id").fetchall()
        assert (2, 99999) in rows
        # and the emitted schema carries the stray-comma hallmark of the bug
        with open(os.path.join(exp, "schema.sql")) as _sf:
            schema = _sf.read()
        assert ", )" in schema or ", ," in schema
    finally:
        r.close()


# ---------------------------------------------------------------------------
# 2. Raw upstream impact: the real schema fails before Antiek normalization
# ---------------------------------------------------------------------------
def test_raw_full_schema_import_fails_only_for_known_self_ref_bug(tmp_path) -> None:
    """Raw IMPORT fails for the pinned comma bug before product normalization."""
    src = str(tmp_path / "antiek.duckdb")
    init_database_at_path(src)
    with connect_write(src, purpose="roundtrip_seed") as con:
        con.execute(
            "INSERT INTO documents(document_id, source_tier, document_type, title) "
            "VALUES ('doc-1', 3, 'paper', 'On the Calculus of Variations')"
        )
        con.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text) "
            "VALUES ('chk-1', 'doc-1', 0, 'body')"
        )
        con.execute(
            "INSERT INTO nodes(node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-1', 'Euler', 'person', 'depth')"
        )
        con.execute(
            "INSERT INTO edges(edge_id, source_node_id, target_node_id, relation, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-1', 'n-1', 'n-1', 'self_ref_ok', 3, 0.5, 'depth')"
        )

    exp = str(tmp_path / "export")
    restored = str(tmp_path / "restored.duckdb")
    _export(src, exp)
    with pytest.raises(duckdb.Error) as raised:
        _import(exp, restored)
    error = str(raised.value)
    assert "syntax error" in error and "," in error, (
        f"IMPORT failed for an unexpected reason (not the comma bug): {error}"
    )


# ---------------------------------------------------------------------------
# 3. The mechanism is sound for self-ref-free schemas (positive control)
# ---------------------------------------------------------------------------
def test_roundtrip_preserves_non_self_referential_schema(tmp_path) -> None:
    """Rows, a non-self-ref FK, a CHECK, and an index all survive round-trip.

    Proves the backup mechanism is correct in general — the defect is scoped
    specifically to self-referential FKs, not to EXPORT/IMPORT at large.
    """
    src = str(tmp_path / "src.db")
    exp = str(tmp_path / "export")
    restored = str(tmp_path / "restored.db")
    c = duckdb.connect(src)
    try:
        c.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        c.execute(
            "CREATE TABLE child(child_id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL "
            "REFERENCES parent(id), tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 5))"
        )
        c.execute("CREATE INDEX idx_child_parent ON child(parent_id)")
        c.execute("INSERT INTO parent VALUES (1), (2)")
        c.execute("INSERT INTO child VALUES (10, 1, 3), (11, 2, 5)")
    finally:
        c.close()
    _export(src, exp)
    _import(exp, restored)

    r = duckdb.connect(restored)
    try:
        rows = r.execute("SELECT child_id, parent_id, tier FROM child ORDER BY child_id").fetchall()
        assert rows == [(10, 1, 3), (11, 2, 5)]
        # non-self-ref FK still enforces
        with pytest.raises(duckdb.Error):
            r.execute("INSERT INTO child VALUES (99, 77777, 3)")
        # CHECK still enforces
        with pytest.raises(duckdb.Error):
            r.execute("INSERT INTO child VALUES (98, 1, 99)")
        # index survived
        idxs = [x[0] for x in r.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name='child'"
        ).fetchall()]
        assert "idx_child_parent" in idxs
    finally:
        r.close()

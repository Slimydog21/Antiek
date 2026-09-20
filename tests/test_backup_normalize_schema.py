"""Tests for tools/backup_normalize_schema.normalize_exported_schema_sql.

Closes the SPR-02 loop (specs/antiek-data-durability): the backup-layer fix that
makes DuckDB EXPORT/IMPORT restorable despite the self-ref-FK stray-comma bug.
The unit tests pin depth/string-awareness (a comma inside a CHECK or string is
never touched); the integration test proves the REAL Antiek schema, once
normalized, imports cleanly with data + non-self-ref FK + CHECK intact.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path, list_tables
from tools.backup_normalize_schema import normalize_exported_schema_sql

_ROOT = Path(__file__).resolve().parents[1]


def _export(src_db: str, export_dir: str) -> None:
    os.makedirs(export_dir, exist_ok=True)
    con = duckdb.connect(src_db, read_only=True)
    try:
        con.execute(f"EXPORT DATABASE '{export_dir}' (FORMAT PARQUET)")
    finally:
        con.close()


def test_deployed_backup_wires_normalizer_after_export() -> None:
    """The normalized round-trip below is the path deployed by Ansible."""
    template = (
        _ROOT / "infrastructure" / "ansible" / "templates" / "backup.sh.j2"
    ).read_text(encoding="utf-8")
    export_at = template.index('con.execute("EXPORT DATABASE')
    normalizer_at = template.index("normalize_exported_schema_sql(_raw)")
    upload_at = template.index("rclone copyto")
    assert export_at < normalizer_at < upload_at
    assert "tools/backup_normalize_schema.py" in template


# ---------------------------------------------------------------------------
# Unit: the normalizer is depth- + string-aware (never alters valid DDL)
# ---------------------------------------------------------------------------
def test_normalizer_drops_stray_commas_but_keeps_nested_and_string_commas() -> None:
    # A synthetic CREATE TABLE carrying (a) a CHECK with nested-list commas,
    # (b) a string literal containing ", )", and (c) BOTH DuckDB self-ref
    # malformations: a trailing ", )" and a mid-list empty slot ", ,".
    raw = (
        "CREATE TABLE t(\n"
        "  id INTEGER PRIMARY KEY,\n"
        "  parent INTEGER REFERENCES t(id),\n"  # self-ref → DuckDB drops it
        "  tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),\n"  # nested commas MUST survive
        "  note VARCHAR DEFAULT('a, )z'),\n"  # ", )" inside a string MUST survive
        "  ,\n"  # empty slot (dropped self-ref)
        "  CHECK (tier > 0)\n"
        ");;\n"
    )
    fixed = normalize_exported_schema_sql(raw)
    # nested IN-list commas preserved
    assert "CHECK (tier IN (1, 2, 3))" in fixed
    # string-literal ", )" preserved
    assert "DEFAULT('a, )z')" in fixed
    # the empty slot is collapsed and there is no trailing/double comma left
    assert ", ," not in fixed and ", )" not in fixed.replace("('a, )z')", "")
    # the fixed DDL parses (no comma error)
    con = duckdb.connect(":memory:")
    try:
        con.execute(fixed.replace(";;", ";"))
        # and the self-ref + table are real
        con.execute("INSERT INTO t(id, parent, tier) VALUES (1, NULL, 2)")
    finally:
        con.close()


def test_normalizer_is_idempotent_and_a_noop_on_valid_ddl() -> None:
    valid = (
        "CREATE TABLE a(x INTEGER PRIMARY KEY, y INTEGER CHECK (y IN (1, 2)));\n"
        "CREATE SEQUENCE seq;;\n"
        "CREATE INDEX idx_a_y ON a(y);;\n"
    )
    once = normalize_exported_schema_sql(valid)
    assert once == valid, "valid DDL must pass through unchanged"
    assert normalize_exported_schema_sql(once) == once, "idempotent"


# ---------------------------------------------------------------------------
# Integration: the REAL Antiek schema, normalized, imports cleanly
# ---------------------------------------------------------------------------
def test_real_schema_normalized_export_imports_with_data_and_constraints(tmp_path) -> None:
    src = str(tmp_path / "antiek.duckdb")
    init_database_at_path(src)
    with connect_write(src, purpose="normalize_seed") as con:
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
        # a self-ref edge through the malformed `edges` table
        con.execute(
            "INSERT INTO edges(edge_id, source_node_id, target_node_id, relation, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-1', 'n-1', 'n-1', 'self_ref', 3, 0.5, 'depth')"
        )

    exp = str(tmp_path / "export")
    _export(src, exp)
    schema_path = os.path.join(exp, "schema.sql")
    with open(schema_path) as f:
        raw = f.read()

    # negative control: the UN-normalized EXPORT does NOT import (the bug)
    with pytest.raises(duckdb.Error):
        duckdb.connect(str(tmp_path / "raw_restored.db")).execute(
            f"IMPORT DATABASE '{exp}'"
        )

    # normalize + import
    with open(schema_path, "w") as f:
        f.write(normalize_exported_schema_sql(raw))
    restored = str(tmp_path / "restored.duckdb")
    r = duckdb.connect(restored)
    try:
        r.execute(f"IMPORT DATABASE '{exp}'")
        # every original table present
        orig_tables = set(list_tables(duckdb.connect(src, read_only=True)))
        assert orig_tables <= set(list_tables(r)), (
            f"restore dropped tables: {sorted(orig_tables - set(list_tables(r)))}"
        )
        # seeded data round-tripped, incl. the self-ref edge
        assert r.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 1
        assert r.execute(
            "SELECT relation FROM edges WHERE edge_id = 'e-1'"
        ).fetchone()[0] == "self_ref"
        # CHECK still enforces on the restored DB
        with pytest.raises(duckdb.Error):
            r.execute(
                "INSERT INTO nodes(node_id, canonical_label, node_type, graph_scope) "
                "VALUES ('bad', 'x', 'not_a_real_type', 'depth')"
            )
        # a NON-self-ref FK still enforces on the restored DB
        with pytest.raises(duckdb.Error):
            r.execute(
                "INSERT INTO edges(edge_id, source_node_id, target_node_id, relation, "
                "source_tier, extraction_confidence, graph_scope) "
                "VALUES ('bad', 'nonexistent', 'n-1', 'rel', 3, 0.5, 'depth')"
            )
    finally:
        r.close()

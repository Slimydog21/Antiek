"""Tests for the knowledge-graph health report (graph doctor).

The pure ``derive_edge_temporal`` is unit tested directly; ``collect`` is
exercised end-to-end against a seeded in-memory DuckDB so the SQL shape queries
are real, not mocked. Non-vacuous: if the temporal split or an orphan query were
wrong, these assertions fail.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from tools.graph_doctor import GraphMetrics, collect, derive_edge_temporal, main, render

NOW = datetime(2026, 7, 1)
PAST = datetime(2026, 1, 1)
FUTURE = datetime(2026, 12, 1)


# ── pure derivation ─────────────────────────────────────────────────────────
def test_edge_temporal_split():
    rows = [
        (None, None),        # live (open-ended)
        (None, FUTURE),      # live (not yet expired)
        (None, PAST),        # expired
        ("other", None),     # superseded (wins even though open-ended)
        ("other", PAST),     # superseded (wins over expired)
    ]
    assert derive_edge_temporal(rows, NOW) == (2, 2, 1)


def test_edge_temporal_empty():
    assert derive_edge_temporal([], NOW) == (0, 0, 0)


# ── end-to-end against a seeded DuckDB ──────────────────────────────────────
@pytest.fixture()
def seeded(tmp_path):
    path = str(tmp_path / "g.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE documents(document_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT)")
    con.execute("CREATE TABLE nodes(node_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE edges(edge_id TEXT PRIMARY KEY, source_node_id TEXT, "
                "target_node_id TEXT, valid_until TIMESTAMP, superseded_by TEXT)")
    con.execute("CREATE TABLE syntheses(synthesis_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE synthesis_substrate_manifest(synthesis_id TEXT, "
                "entity_kind TEXT, entity_id TEXT)")
    con.execute("CREATE TABLE ip_holders(ip_holder_id TEXT PRIMARY KEY)")

    con.execute("INSERT INTO documents VALUES ('doc-chunked'), ('doc-orphan')")
    con.execute("INSERT INTO chunks VALUES ('ch1','doc-chunked')")  # doc-orphan has none
    con.execute("INSERT INTO nodes VALUES ('n1'),('n2'),('n-isolated')")
    con.execute("INSERT INTO edges VALUES ('e1','n1','n2',NULL,NULL)")  # n-isolated untouched
    con.execute("INSERT INTO syntheses VALUES ('s-pinned'),('s-unpinned')")
    con.execute("INSERT INTO synthesis_substrate_manifest VALUES ('s-pinned','node','n1')")
    con.close()
    return path


def test_collect_counts_and_orphans(seeded):
    m = collect(seeded, NOW)
    assert m.counts["documents"] == 2
    assert m.counts["nodes"] == 3
    assert m.counts["edges"] == 1
    assert m.documents_without_chunks == 1        # doc-orphan
    assert m.isolated_nodes == 1                  # n-isolated
    assert m.syntheses_without_manifest == 1      # s-unpinned
    assert m.total_orphans == 3


def test_render_is_readable(seeded):
    text = render(collect(seeded, NOW))
    assert "knowledge-graph health report" in text
    assert "isolated_nodes" in text
    assert "total orphan-shape rows: 3" in text


def test_missing_tables_do_not_crash(tmp_path):
    # a freshly-migrated / partial graph audits to zeros rather than raising
    path = str(tmp_path / "empty.duckdb")
    duckdb.connect(path).close()
    m = collect(path, NOW)
    assert m.counts["documents"] == 0 and m.total_orphans == 0


def test_metrics_is_dataclass_serializable():
    m = GraphMetrics(counts={"documents": 1})
    from dataclasses import asdict
    assert asdict(m)["counts"]["documents"] == 1


def test_column_drift_is_noted_not_crashed(tmp_path):
    # A renamed/dropped column must NOT crash the doctor (observability never
    # fails a build); the drift is surfaced as a schema note instead.
    path = str(tmp_path / "drift.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE documents(document_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT)")
    con.execute("CREATE TABLE nodes(node_id TEXT PRIMARY KEY)")
    # edges without superseded_by -> the temporal-split SELECT cannot bind
    con.execute("CREATE TABLE edges(edge_id TEXT PRIMARY KEY, source_node_id TEXT, "
                "target_node_id TEXT, valid_until TIMESTAMP)")
    con.execute("CREATE TABLE syntheses(synthesis_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE synthesis_substrate_manifest(synthesis_id TEXT, "
                "entity_kind TEXT, entity_id TEXT)")
    con.execute("CREATE TABLE ip_holders(ip_holder_id TEXT PRIMARY KEY)")
    con.close()
    m = collect(path, NOW)  # must not raise
    assert any("edge temporal" in n for n in m.schema_notes)
    assert "schema notes" in render(m)


def test_type_drift_valid_until_is_noted_not_crashed(tmp_path):
    # valid_until VARCHAR (type drift): the name binds so a name-only guard would
    # crash comparing str > datetime; the boundary type-check notes it instead.
    path = str(tmp_path / "typedrift.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE documents(document_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT)")
    con.execute("CREATE TABLE nodes(node_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE edges(edge_id TEXT, source_node_id TEXT, "
                "target_node_id TEXT, valid_until VARCHAR, superseded_by TEXT)")
    con.execute("INSERT INTO edges VALUES ('e1','n1','n2','2026-01-01',NULL)")
    con.execute("CREATE TABLE syntheses(synthesis_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE synthesis_substrate_manifest(synthesis_id TEXT, "
                "entity_kind TEXT, entity_id TEXT)")
    con.execute("CREATE TABLE ip_holders(ip_holder_id TEXT PRIMARY KEY)")
    con.close()
    m = collect(path, NOW)  # must not raise
    assert any("not a TIMESTAMP" in n for n in m.schema_notes)


def test_corrupt_graph_file_is_noted_and_never_fails_build(tmp_path):
    path = tmp_path / "corrupt.duckdb"
    path.write_bytes(b"not a duckdb file at all")
    m = collect(str(path), NOW)  # must not raise
    assert any("cannot open graph" in n for n in m.schema_notes)
    assert main(["--graph", str(path)]) == 0  # observability never fails a build

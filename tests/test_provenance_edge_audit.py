"""Bite tests for the provenance-edge integrity audit.

These exercise the PURE core (no database), so the gate is falsifiable without a
live DuckDB graph. The load-bearing assertion is non-vacuous: if the audit body
were replaced with ``return []`` (a stub), ``test_manifest_orphan_bites`` and
``test_edge_grounding_bites`` would FAIL — that is what makes this a real gate
rather than a green rubber stamp.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from tools.lint.provenance_edge_audit import (
    Finding,
    SchemaDriftError,
    audit_edge_grounding,
    audit_manifest,
    load_from_duckdb,
    main,
    new_findings,
    shrink_baseline,
)


def _live() -> dict[str, set[str]]:
    return {
        "document": {"doc-1"},
        "chunk": {"chunk-1"},
        "node": {"node-1", "node-2"},
        "edge": {"edge-1"},
    }


# --------------------------------------------------------------------------- #
# synthesis_substrate_manifest — the polymorphic, non-FK-enforceable surface
# --------------------------------------------------------------------------- #
def test_manifest_clean_passes():
    rows = [
        ("syn-1", "document", "doc-1"),
        ("syn-1", "chunk", "chunk-1"),
        ("syn-1", "node", "node-1"),
    ]
    assert audit_manifest(rows, _live()) == []


def test_manifest_orphan_bites():
    # syn-1 pins a chunk that was later deleted — the DB cannot catch this
    # (entity_id is polymorphic, so no FK spans documents/chunks/nodes/edges).
    rows = [
        ("syn-1", "document", "doc-1"),
        ("syn-1", "chunk", "chunk-DELETED"),
    ]
    findings = audit_manifest(rows, _live())
    assert len(findings) == 1
    assert findings[0].surface == "manifest"
    assert findings[0].ref_id == "chunk-DELETED"
    assert "missing chunk" in findings[0].detail


def test_manifest_unknown_kind_bites():
    # A smuggled entity_kind we cannot resolve must never silently pass.
    rows = [("syn-1", "spork", "whatever")]
    findings = audit_manifest(rows, _live())
    assert len(findings) == 1
    assert "unknown entity_kind" in findings[0].detail


# --------------------------------------------------------------------------- #
# edges.chunk_id / edges.source_document_id — nullable grounding columns
# --------------------------------------------------------------------------- #
def test_edge_null_grounding_is_allowed():
    # NULL grounding is legitimate (structural edge); never a finding.
    edges = [("edge-1", None, None)]
    assert audit_edge_grounding(edges, {"chunk-1"}, {"doc-1"}) == []


def test_edge_grounding_bites():
    edges = [
        ("edge-1", "chunk-1", "doc-1"),          # resolves — clean
        ("edge-2", "chunk-GONE", None),          # dangling chunk grounding
        ("edge-3", None, "doc-GONE"),            # dangling document grounding
    ]
    findings = audit_edge_grounding(edges, {"chunk-1"}, {"doc-1"})
    surfaces = sorted(f.surface for f in findings)
    assert surfaces == ["edge.chunk_id", "edge.source_document_id"]


# --------------------------------------------------------------------------- #
# Shrink-only baseline behaviour
# --------------------------------------------------------------------------- #
def test_baselined_finding_does_not_refail():
    rows = [("syn-1", "chunk", "chunk-DELETED")]
    findings = audit_manifest(rows, _live())
    assert findings, "precondition: there is a finding to baseline"
    baseline = {findings[0].key()}
    assert new_findings(findings, baseline) == []


def test_non_baselined_finding_still_fails_with_baseline_present():
    # A baseline for one orphan must NOT suppress a different, new orphan.
    rows = [
        ("syn-1", "chunk", "chunk-DELETED"),   # baselined
        ("syn-2", "document", "doc-NEW-GONE"), # new — must still bite
    ]
    findings = audit_manifest(rows, _live())
    baseline = {Finding("manifest", "chunk-DELETED",
                        "synthesis syn-1 pins missing chunk chunk-DELETED").key()}
    fresh = new_findings(findings, baseline)
    assert len(fresh) == 1
    assert fresh[0].ref_id == "doc-NEW-GONE"


def test_finding_key_is_stable_and_json_round_trips():
    f = Finding("manifest", "x", "synthesis s pins missing chunk x")
    assert f.key() == Finding("manifest", "x", "synthesis s pins missing chunk x").key()
    # keys are the baseline's on-disk identity — must be plain JSON-serializable strings
    assert json.loads(json.dumps({"baselined_keys": [f.key()]}))["baselined_keys"][0] == f.key()


def test_shrink_baseline_drops_resolved_never_adds():
    old = {"manifest\ta\tsynthesis s pins missing chunk a",
           "manifest\tb\tsynthesis s pins missing document b"}
    current = {"manifest\ta\tsynthesis s pins missing chunk a",
               "edge.chunk_id\tc\tedge c grounds on missing chunk c"}
    # b's key resolved (absent from current) -> dropped; c's NEW key not added.
    assert shrink_baseline(old, current) == ["manifest\ta\tsynthesis s pins missing chunk a"]


# --------------------------------------------------------------------------- #
# DB extraction + schema-strict handling (real DuckDB)
# --------------------------------------------------------------------------- #
def _make_graph(path: str, *, edges_cols: str = "edge_id TEXT, chunk_id TEXT, "
                "source_document_id TEXT", with_manifest: bool = True,
                edge_rows: str = "", manifest_rows: str = "") -> None:
    con = duckdb.connect(path)
    con.execute("CREATE TABLE documents(document_id TEXT PRIMARY KEY)")
    con.execute("CREATE TABLE chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT)")
    con.execute("CREATE TABLE nodes(node_id TEXT PRIMARY KEY)")
    con.execute(f"CREATE TABLE edges({edges_cols})")
    if with_manifest:
        con.execute("CREATE TABLE synthesis_substrate_manifest("
                    "synthesis_id TEXT, entity_kind TEXT, entity_id TEXT)")
    con.execute("INSERT INTO documents VALUES ('doc-1')")
    con.execute("INSERT INTO chunks VALUES ('chunk-1','doc-1')")
    con.execute("INSERT INTO nodes VALUES ('node-1')")
    if edge_rows:
        con.execute(f"INSERT INTO edges VALUES {edge_rows}")
    if with_manifest and manifest_rows:
        con.execute(f"INSERT INTO synthesis_substrate_manifest VALUES {manifest_rows}")
    con.close()


def test_real_graph_all_resolving_passes(tmp_path):
    path = str(tmp_path / "g.duckdb")
    _make_graph(path, edge_rows="('edge-1','chunk-1','doc-1')",
                manifest_rows="('syn-1','chunk','chunk-1')")
    assert main(["--graph", path]) == 0


def test_real_graph_dangling_manifest_bites(tmp_path):
    path = str(tmp_path / "g.duckdb")
    _make_graph(path, manifest_rows="('syn-1','chunk','chunk-GONE')")
    assert main(["--graph", path]) == 1


def test_missing_table_is_schema_drift_not_silent_pass(tmp_path):
    # Rename/drop synthesis_substrate_manifest -> the gate must NOT pass (which
    # would hide a real dangling manifest row); it fails loud instead.
    path = str(tmp_path / "g.duckdb")
    _make_graph(path, with_manifest=False)
    with pytest.raises(SchemaDriftError):
        load_from_duckdb(path)
    assert main(["--graph", path]) == 2


def test_missing_column_is_schema_drift_not_a_crash(tmp_path):
    # edges without source_document_id (renamed/dropped column) -> loud, not crash.
    path = str(tmp_path / "g.duckdb")
    _make_graph(path, edges_cols="edge_id TEXT, chunk_id TEXT")
    with pytest.raises(SchemaDriftError):
        load_from_duckdb(path)
    assert main(["--graph", path]) == 2


def test_no_graph_is_a_clean_noop():
    assert main([]) == 0


def test_corrupt_graph_file_is_schema_drift_not_a_crash(tmp_path):
    path = tmp_path / "corrupt.duckdb"
    path.write_bytes(b"this is not a duckdb file at all")
    with pytest.raises(SchemaDriftError):
        load_from_duckdb(str(path))
    assert main(["--graph", str(path)]) == 2


def test_update_baseline_does_not_silence_a_live_regression(tmp_path):
    # --update-baseline shrinks, then STILL enforces: a live dangling manifest
    # reference present during maintenance must exit 1, never 0.
    path = str(tmp_path / "g.duckdb")
    _make_graph(path, manifest_rows="('syn-1','chunk','chunk-GONE')")
    baseline = tmp_path / "baseline.json"
    assert main(["--graph", path, "--baseline", str(baseline), "--update-baseline"]) == 1

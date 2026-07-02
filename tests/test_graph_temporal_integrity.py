"""Bite tests for the knowledge-graph temporal-integrity audit.

Exercise the PURE core (no database, no clock), so the gate is falsifiable
without a live DuckDB graph and deterministic across runs. Each invariant has a
seeded violation whose absence would let a real bug ship; if the audited core
were stubbed to ``return []`` these tests FAIL — that is what makes this a gate
rather than a rubber stamp. The DB-backed tests seed a real DuckDB so the
read-only extraction and schema-drift handling are exercised, not mocked.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from tools.lint.graph_temporal_integrity import (
    Edge,
    SchemaDriftError,
    audit_edges,
    audit_inverted_windows,
    audit_self_supersession,
    audit_supersession_cycles,
    load_edges_from_duckdb,
    main,
    new_findings,
    shrink_baseline,
)

T0 = datetime(2026, 1, 1)
T1 = datetime(2026, 6, 1)
T2 = datetime(2026, 12, 1)


def _edge(eid, *, src="n1", tgt="n2", rel="supports",
          valid_from=T0, valid_until=None, superseded_by=None) -> Edge:
    return Edge(eid, src, tgt, rel, valid_from, valid_until, superseded_by)


# ── inverted window ─────────────────────────────────────────────────────────
def test_inverted_window_bites():
    edges = [_edge("e1", valid_from=T2, valid_until=T1)]  # ends before it starts
    f = audit_inverted_windows(edges)
    assert len(f) == 1 and f[0].surface == "inverted_window" and f[0].edge_id == "e1"


def test_normal_window_and_null_until_pass():
    edges = [_edge("e1", valid_from=T0, valid_until=T2), _edge("e2", valid_until=None)]
    assert audit_inverted_windows(edges) == []


# ── self-supersession ───────────────────────────────────────────────────────
def test_self_supersession_bites():
    edges = [_edge("e1", superseded_by="e1")]
    f = audit_self_supersession(edges)
    assert len(f) == 1 and f[0].surface == "self_supersession"


# ── supersession cycle ──────────────────────────────────────────────────────
def test_two_cycle_bites_both_edges():
    edges = [_edge("a", superseded_by="b"), _edge("b", superseded_by="a")]
    f = audit_supersession_cycles(edges)
    assert {x.edge_id for x in f} == {"a", "b"}
    assert all(x.surface == "supersession_cycle" for x in f)


def test_linear_supersession_chain_is_clean():
    # a -> b -> c (terminates); not a cycle.
    edges = [_edge("a", superseded_by="b"), _edge("b", superseded_by="c"),
             _edge("c", superseded_by=None)]
    assert audit_supersession_cycles(edges) == []


def test_self_loop_not_double_counted_as_cycle():
    # length-1 self loop is reported by self_supersession only, not the cycle check.
    edges = [_edge("e1", superseded_by="e1")]
    assert audit_supersession_cycles(edges) == []


def test_rho_shape_flags_only_the_cycle_not_the_tail():
    # tail t -> a -> b -> a : only a,b are on the cycle; t is not.
    edges = [_edge("t", superseded_by="a"), _edge("a", superseded_by="b"),
             _edge("b", superseded_by="a")]
    assert {x.edge_id for x in audit_supersession_cycles(edges)} == {"a", "b"}


# ── corroboration is NOT a temporal violation ───────────────────────────────
def test_corroboration_over_one_triple_is_not_a_violation():
    # Two live edges over the same (src,tgt,rel) differ only in grounding
    # (distinct ids by ops.py content-addressing) — legitimate multi-source
    # corroboration. The audit must NOT flag it (the old duplicate_live check,
    # which two independent reviewers proved false-firing, has been removed).
    edges = [_edge("e1"), _edge("e2")]
    assert audit_edges(edges) == []


# ── baseline behaviour ──────────────────────────────────────────────────────
def test_baselined_finding_does_not_refail():
    findings = audit_edges([_edge("e1", superseded_by="e1")])
    assert findings, "precondition: a finding exists"
    assert new_findings(findings, {findings[0].key()}) == []


def test_shrink_baseline_drops_resolved_never_adds():
    old = {"self_supersession\te1\tedge supersedes itself",
           "inverted_window\te2\tvalid_until X < valid_from Y"}
    current = {"self_supersession\te1\tedge supersedes itself",
               "supersession_cycle\te3\tedge is on a superseded_by cycle (no latest edge)"}
    kept = shrink_baseline(old, current)
    # e2's key resolved (absent from current) -> dropped; e3's NEW key not added.
    assert kept == ["self_supersession\te1\tedge supersedes itself"]


def test_all_invariants_compose_in_audit_edges():
    edges = [
        _edge("inv", valid_from=T2, valid_until=T1),
        _edge("selfsup", src="x", tgt="y", superseded_by="selfsup"),
        _edge("c1", src="p", tgt="q", rel="r", superseded_by="c2"),
        _edge("c2", src="p", tgt="q", rel="r", superseded_by="c1"),
    ]
    surfaces = {f.surface for f in audit_edges(edges)}
    assert surfaces == {"inverted_window", "self_supersession", "supersession_cycle"}


# ── DB extraction + schema-strict handling (real DuckDB) ────────────────────
def _make_edges(path: str, *, cols: str, rows: str | None = None) -> None:
    con = duckdb.connect(path)
    con.execute(f"CREATE TABLE edges({cols})")
    if rows:
        con.execute(f"INSERT INTO edges VALUES {rows}")
    con.close()


_FULL_COLS = ("edge_id TEXT, source_node_id TEXT, target_node_id TEXT, "
              "relation TEXT, valid_from TIMESTAMP, valid_until TIMESTAMP, "
              "superseded_by TEXT")


def test_load_reads_edges_and_corroboration_stays_clean(tmp_path):
    path = str(tmp_path / "g.duckdb")
    _make_edges(
        path, cols=_FULL_COLS,
        rows=("('e1','n1','n2','supports',TIMESTAMP '2026-01-01',NULL,NULL),"
              "('e2','n1','n2','supports',TIMESTAMP '2026-01-01',NULL,NULL)"),
    )
    edges = load_edges_from_duckdb(path)
    assert len(edges) == 2
    assert audit_edges(edges) == []  # two live edges over one triple = corroboration
    assert main(["--graph", path]) == 0


def test_missing_column_is_schema_drift_not_a_crash(tmp_path):
    # edges without superseded_by (a renamed/dropped column) -> loud, not a crash.
    path = str(tmp_path / "drift.duckdb")
    _make_edges(path, cols=("edge_id TEXT, source_node_id TEXT, target_node_id TEXT, "
                            "relation TEXT, valid_from TIMESTAMP, valid_until TIMESTAMP"))
    with pytest.raises(SchemaDriftError):
        load_edges_from_duckdb(path)
    assert main(["--graph", path]) == 2


def test_missing_edges_table_is_schema_drift_not_silent_pass(tmp_path):
    # A graph with no edges table must NOT silently pass (exit 0) — it fails loud.
    path = str(tmp_path / "empty.duckdb")
    duckdb.connect(path).close()
    with pytest.raises(SchemaDriftError):
        load_edges_from_duckdb(path)
    assert main(["--graph", path]) == 2


def test_no_graph_is_a_clean_noop():
    assert main([]) == 0


def test_type_drift_valid_until_not_timestamp_is_schema_drift(tmp_path):
    # valid_until drifts TIMESTAMP -> VARCHAR: the name binds, but comparing the
    # str value would crash. The boundary type-check turns it into a loud
    # SchemaDriftError (exit 2), not a traceback.
    path = str(tmp_path / "typedrift.duckdb")
    _make_edges(
        path,
        cols=("edge_id TEXT, source_node_id TEXT, target_node_id TEXT, "
              "relation TEXT, valid_from TIMESTAMP, valid_until VARCHAR, "
              "superseded_by TEXT"),
        rows=("('e1','n1','n2','supports',TIMESTAMP '2026-01-01','2026-09-01',NULL)"),
    )
    with pytest.raises(SchemaDriftError):
        load_edges_from_duckdb(path)
    assert main(["--graph", path]) == 2


def test_corrupt_graph_file_is_schema_drift_not_a_crash(tmp_path):
    path = tmp_path / "corrupt.duckdb"
    path.write_bytes(b"this is not a duckdb file at all")
    with pytest.raises(SchemaDriftError):
        load_edges_from_duckdb(str(path))
    assert main(["--graph", str(path)]) == 2


def test_update_baseline_does_not_silence_a_live_regression(tmp_path):
    # --update-baseline shrinks, then STILL enforces: a live self-supersession
    # present during maintenance must exit 1, never 0.
    path = str(tmp_path / "g.duckdb")
    _make_edges(path, cols=_FULL_COLS,
                rows="('e1','n1','n2','supports',TIMESTAMP '2026-01-01',NULL,'e1')")
    baseline = tmp_path / "baseline.json"
    assert main(["--graph", path, "--baseline", str(baseline), "--update-baseline"]) == 1

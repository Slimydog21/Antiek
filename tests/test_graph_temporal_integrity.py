"""Bite tests for the knowledge-graph temporal-integrity audit.

Exercise the PURE core (no database, explicit ``now``), so the gate is
falsifiable without a live DuckDB graph and deterministic across runs. Each
invariant has a seeded violation whose absence would let a real bug ship; if the
audited core were stubbed to ``return []`` these tests FAIL — that is what makes
this a gate rather than a rubber stamp.
"""

from __future__ import annotations

from datetime import datetime

from tools.lint.graph_temporal_integrity import (
    Edge,
    audit_current_truth_uniqueness,
    audit_edges,
    audit_inverted_windows,
    audit_self_supersession,
    audit_supersession_cycles,
    new_findings,
)

T0 = datetime(2026, 1, 1)
T1 = datetime(2026, 6, 1)
T2 = datetime(2026, 12, 1)
NOW = datetime(2026, 7, 1)


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


# ── current-truth uniqueness ────────────────────────────────────────────────
def test_duplicate_live_edges_bite():
    edges = [_edge("e1"), _edge("e2")]  # both live, same (n1,n2,supports)
    f = audit_current_truth_uniqueness(edges, NOW)
    assert {x.edge_id for x in f} == {"e1", "e2"}
    assert all(x.surface == "duplicate_live" for x in f)


def test_superseded_or_expired_edge_is_not_live():
    edges = [
        _edge("e1"),                              # live
        _edge("e2", superseded_by="e1"),          # superseded -> not live
        _edge("e3", valid_until=T1),              # expired before NOW -> not live
    ]
    assert audit_current_truth_uniqueness(edges, NOW) == []


def test_distinct_relation_is_not_a_duplicate():
    edges = [_edge("e1", rel="supports"), _edge("e2", rel="contradicts")]
    assert audit_current_truth_uniqueness(edges, NOW) == []


# ── baseline behaviour ──────────────────────────────────────────────────────
def test_baselined_finding_does_not_refail():
    findings = audit_edges([_edge("e1", superseded_by="e1")], NOW)
    assert findings, "precondition: a finding exists"
    assert new_findings(findings, {findings[0].key()}) == []


def test_all_invariants_compose_in_audit_edges():
    edges = [
        _edge("inv", valid_from=T2, valid_until=T1),
        _edge("selfsup", src="x", tgt="y", superseded_by="selfsup"),
        _edge("c1", src="p", tgt="q", rel="r", superseded_by="c2"),
        _edge("c2", src="p", tgt="q", rel="r", superseded_by="c1"),
    ]
    surfaces = {f.surface for f in audit_edges(edges, NOW)}
    assert surfaces == {"inverted_window", "self_supersession", "supersession_cycle"}

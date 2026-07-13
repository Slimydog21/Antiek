"""Tests for the staleness-cascade axis (ask #1 — knowledge-graph rot propagation)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.staleness_cascade import (
    RootCascade,
    StalenessCascadeReport,
    measure_staleness_cascade,
)

# ---------------------------------------------------------------------------
# Unknown / base cases.
# ---------------------------------------------------------------------------


def test_unknown_empty_graph_and_no_stale_roots() -> None:
    report = measure_staleness_cascade([], [])
    assert report.total_node_count == 0
    assert report.stale_root_count == 0
    assert report.transitively_stale_count == 0
    assert report.cascade_ratio is None
    assert report.max_cascade_depth is None
    assert report.per_root_cascade == ()
    assert report.verdict == "unknown"
    assert report.authority == "advisory"
    assert report.notes == ()


def test_no_staleness_graph_exists_but_zero_stale_roots() -> None:
    report = measure_staleness_cascade([("A", "B"), ("B", "C")], [])
    assert report.total_node_count == 3
    assert report.stale_root_count == 0
    assert report.transitively_stale_count == 0
    assert report.cascade_ratio == pytest.approx(0.0)
    assert report.max_cascade_depth == 0
    assert report.verdict == "no_staleness"


# ---------------------------------------------------------------------------
# Isolated staleness — stale root reaches nothing.
# ---------------------------------------------------------------------------


def test_isolated_staleness_stale_leaf() -> None:
    # C is stale but has no outgoing edges (a terminal node).
    report = measure_staleness_cascade([("A", "B"), ("B", "C")], ["C"])
    assert report.stale_root_count == 1
    assert report.transitively_stale_count == 0
    assert report.cascade_ratio == pytest.approx(1 / 3)
    assert report.max_cascade_depth == 0
    assert report.verdict == "isolated_staleness"


def test_isolated_staleness_detached_root_not_in_graph() -> None:
    report = measure_staleness_cascade([("A", "B")], ["Z"])
    assert report.stale_root_count == 1
    assert report.transitively_stale_count == 0
    assert report.detached_root_count == 1
    assert report.verdict == "isolated_staleness"
    assert any("detached" in n for n in report.notes)


# ---------------------------------------------------------------------------
# Cascade — staleness propagates.
# ---------------------------------------------------------------------------


def test_cascade_simple_chain() -> None:
    # A -> B -> C; A stale -> B and C transitively stale. depth 2.
    report = measure_staleness_cascade([("A", "B"), ("B", "C")], ["A"])
    assert report.total_node_count == 3
    assert report.stale_root_count == 1
    assert report.transitively_stale_count == 2
    assert report.total_stale_footprint == 3
    assert report.cascade_ratio == pytest.approx(1.0)
    assert report.max_cascade_depth == 2
    assert report.affected_root_count == 1
    assert report.verdict == "pervasive_cascade"
    assert report.per_root_cascade == (RootCascade("A", 2, 2),)


def test_cascade_diamond_dedup() -> None:
    # A -> B, A -> C, B -> D, C -> D; A stale -> B, C, D all reachable.
    # D reachable via two paths but counted ONCE. transitive = 3.
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
    report = measure_staleness_cascade(edges, ["A"])
    assert report.transitively_stale_count == 3
    assert report.total_node_count == 4
    assert report.cascade_ratio == pytest.approx(4 / 4)
    assert report.max_cascade_depth == 2  # A->B->D or A->C->D
    assert report.per_root_cascade[0].reachable_count == 3


def test_cascade_cycle_handled() -> None:
    # A -> B -> A (cycle); A stale -> B reachable (A excluded as root). transitive = 1.
    report = measure_staleness_cascade([("A", "B"), ("B", "A")], ["A"])
    assert report.transitively_stale_count == 1
    assert report.max_cascade_depth == 1
    assert report.verdict != "isolated_staleness"


def test_cascade_self_loop_dropped() -> None:
    # A -> A (self-loop, dropped) + A -> B; A stale -> B reachable only.
    report = measure_staleness_cascade([("A", "A"), ("A", "B")], ["A"])
    assert report.transitively_stale_count == 1
    assert report.total_node_count == 2  # A and B (self-loop node A not duplicated)


def test_cascade_two_roots_union() -> None:
    # A -> B, C -> D; A and C both stale -> {B, D} reachable. transitive = 2.
    report = measure_staleness_cascade([("A", "B"), ("C", "D")], ["A", "C"])
    assert report.stale_root_count == 2
    assert report.transitively_stale_count == 2
    assert report.total_stale_footprint == 4
    assert report.affected_root_count == 2
    assert len(report.per_root_cascade) == 2


def test_cascade_stale_root_downstream_of_another_stale_root() -> None:
    # A -> B; both A and B stale. B is reachable FROM A (inherited) AND a root itself.
    # transitive = 1 (B), even though B is also a root.
    report = measure_staleness_cascade([("A", "B")], ["A", "B"])
    assert report.stale_root_count == 2
    assert report.transitively_stale_count == 1  # B reachable from A


def test_contained_cascade_small_ratio() -> None:
    # 7 nodes (A,B,X,Y,Z,P,Q); only A stale -> footprint 2 of 7 -> ratio ~0.286 < 0.30.
    edges = [("A", "B"), ("X", "Y"), ("Y", "Z"), ("P", "Q")]
    report = measure_staleness_cascade(edges, ["A"])
    assert report.total_node_count == 7
    assert report.cascade_ratio == pytest.approx(2 / 7)
    assert report.transitively_stale_count == 1
    assert report.verdict == "contained_cascade"


def test_custom_thresholds_reclassify() -> None:
    # A->B, X->Y; A stale -> footprint 2 of 4 -> ratio 0.50.
    edges = [("A", "B"), ("X", "Y")]
    default = measure_staleness_cascade(edges, ["A"])
    assert default.cascade_ratio == pytest.approx(0.5)
    assert default.verdict == "spreading_cascade"
    # Lower pervasive to 0.50 (boundary inclusive) -> pervasive.
    lowered = measure_staleness_cascade(edges, ["A"], pervasive_threshold=0.50)
    assert lowered.verdict == "pervasive_cascade"
    # Raise contained to 0.60 -> contained (0.50 < 0.60).
    raised = measure_staleness_cascade(edges, ["A"], contained_threshold=0.60)
    assert raised.verdict == "contained_cascade"


# ---------------------------------------------------------------------------
# Threshold validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"contained_threshold": -0.1}, "contained_threshold"),
        ({"contained_threshold": 1.1}, "contained_threshold"),
        ({"pervasive_threshold": -0.1}, "pervasive_threshold"),
        ({"pervasive_threshold": 1.1}, "pervasive_threshold"),
        ({"contained_threshold": 0.8, "pervasive_threshold": 0.2}, "must be <="),
    ],
)
def test_threshold_validation_raises(kwargs: dict[str, float], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        measure_staleness_cascade([("A", "B")], ["A"], **kwargs)


# ---------------------------------------------------------------------------
# Determinism + immutability + auditability.
# ---------------------------------------------------------------------------


def test_report_is_deterministic() -> None:
    edges = [("A", "B"), ("B", "C"), ("A", "C")]
    a = measure_staleness_cascade(edges, ["A"])
    b = measure_staleness_cascade(edges, ["A"])
    assert a == b


def test_report_is_frozen() -> None:
    report = measure_staleness_cascade([("A", "B")], ["A"])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "no_staleness"  # type: ignore[misc]


def test_per_root_sorted_by_reachability_desc() -> None:
    # R1 reaches 2, R2 reaches 1 -> R1 first.
    edges = [("R1", "A"), ("A", "B"), ("R2", "C")]
    report = measure_staleness_cascade(edges, ["R1", "R2"])
    assert report.per_root_cascade[0].root_id == "R1"
    assert report.per_root_cascade[0].reachable_count == 2
    assert report.per_root_cascade[1].root_id == "R2"
    assert report.per_root_cascade[1].reachable_count == 1


def test_whitespace_stale_ids_stripped() -> None:
    report = measure_staleness_cascade([("A", "B")], ["  A  "])
    assert report.stale_root_count == 1
    assert report.transitively_stale_count == 1


def test_report_type() -> None:
    report = measure_staleness_cascade([("A", "B")], ["A"])
    assert isinstance(report, StalenessCascadeReport)
    assert report.authority == "advisory"

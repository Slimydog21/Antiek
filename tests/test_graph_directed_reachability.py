"""Tests for the graph directed-reachability axis (ask #1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_directed_reachability import (
    measure_graph_directed_reachability,
)

# ---------------------------------------------------------------------------
# Base cases — honest defer states.
# ---------------------------------------------------------------------------

def test_zero_nodes_is_unknown() -> None:
    report = measure_graph_directed_reachability([], [])
    assert report.verdict == "unknown"
    assert report.reachability_ratio is None
    assert report.max_reach_set_size is None


def test_one_node_singleton_ratio_none() -> None:
    report = measure_graph_directed_reachability(["A"], [])
    assert report.verdict == "singleton"
    assert report.reachability_ratio is None
    assert report.max_reach_set_size == 0


def test_two_nodes_no_edges_is_no_directed_edges() -> None:
    report = measure_graph_directed_reachability(["A", "B"], [])
    assert report.verdict == "no_directed_edges"
    assert report.directed_edge_count == 0
    # honest measured 0.0, NOT None (distinct from unknown).
    assert report.reachability_ratio == 0.0
    assert report.mutual_pair_count == 0
    assert report.one_way_pair_count == 0
    assert report.unreachable_pair_count == 1


# ---------------------------------------------------------------------------
# Chain — one-way reachability, moderate ratio.
# ---------------------------------------------------------------------------

def test_chain_is_moderately_navigable_one_way() -> None:
    # A -> B -> C. reach(A)={B,C}, reach(B)={C}, reach(C)={}.
    # reachable_directed=3, total=6, ratio=0.5. All 3 unordered pairs one-way.
    report = measure_graph_directed_reachability(
        ["A", "B", "C"], [("A", "B"), ("B", "C")]
    )
    assert report.verdict == "moderately_navigable"
    assert report.reachable_directed_pair_count == 3
    assert report.total_possible_directed_pairs == 6
    assert report.reachability_ratio == pytest.approx(0.5)
    assert report.mutual_pair_count == 0
    assert report.one_way_pair_count == 3
    assert report.unreachable_pair_count == 0
    assert report.max_reach_set_size == 2  # node A reaches B and C


# ---------------------------------------------------------------------------
# Cycle — fully navigable, mutual reachability.
# ---------------------------------------------------------------------------

def test_three_cycle_is_fully_navigable() -> None:
    # A -> B -> C -> A. Every node reaches every other. ratio=1.0, all 3 pairs mutual.
    report = measure_graph_directed_reachability(
        ["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")]
    )
    assert report.verdict == "fully_navigable"
    assert report.reachable_directed_pair_count == 6
    assert report.total_possible_directed_pairs == 6
    assert report.reachability_ratio == 1.0
    assert report.mutual_pair_count == 3
    assert report.one_way_pair_count == 0
    assert report.unreachable_pair_count == 0


def test_strongly_connected_star_is_fully_navigable() -> None:
    # C <-> A, C <-> B. Strongly connected -> ratio 1.0.
    report = measure_graph_directed_reachability(
        ["A", "B", "C"], [("A", "C"), ("C", "A"), ("B", "C"), ("C", "B")]
    )
    assert report.verdict == "fully_navigable"
    assert report.reachability_ratio == 1.0


# ---------------------------------------------------------------------------
# Disconnected — sparsely navigable.
# ---------------------------------------------------------------------------

def test_two_disconnected_pairs_are_sparse() -> None:
    # A -> B, C -> D (separate). reachable_directed=2, total=12, ratio=0.1667.
    # Unordered (6): {A,B} one_way, {C,D} one_way, rest unreachable (4).
    report = measure_graph_directed_reachability(
        ["A", "B", "C", "D"], [("A", "B"), ("C", "D")]
    )
    assert report.verdict == "sparsely_navigable"
    assert report.reachable_directed_pair_count == 2
    assert report.total_possible_directed_pairs == 12
    assert report.reachability_ratio == pytest.approx(2.0 / 12.0)
    assert report.mutual_pair_count == 0
    assert report.one_way_pair_count == 2
    assert report.unreachable_pair_count == 4


def test_single_one_way_edge_is_moderate() -> None:
    # A -> B. reachable=1, total=2, ratio=0.5. one unordered pair, one_way.
    report = measure_graph_directed_reachability(["A", "B"], [("A", "B")])
    assert report.verdict == "moderately_navigable"
    assert report.reachability_ratio == pytest.approx(0.5)
    assert report.one_way_pair_count == 1


# ---------------------------------------------------------------------------
# Partition invariant — mutual + one_way + unreachable == n(n-1)/2.
# ---------------------------------------------------------------------------

def test_pair_breakdown_partition_complete_chain() -> None:
    report = measure_graph_directed_reachability(
        ["A", "B", "C", "D"], [("A", "B"), ("B", "C"), ("C", "D")]
    )
    total_unordered = 4 * 3 // 2  # 6
    assert (
        report.mutual_pair_count
        + report.one_way_pair_count
        + report.unreachable_pair_count
        == total_unordered
    )


def test_pair_breakdown_partition_complete_disconnected() -> None:
    report = measure_graph_directed_reachability(
        ["A", "B", "C", "D"], [("A", "B"), ("C", "D")]
    )
    total_unordered = 4 * 3 // 2
    assert (
        report.mutual_pair_count
        + report.one_way_pair_count
        + report.unreachable_pair_count
        == total_unordered
    )


def test_pair_breakdown_partition_complete_cycle() -> None:
    report = measure_graph_directed_reachability(
        ["A", "B", "C", "D", "E"],
        [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("E", "A")],
    )
    total_unordered = 5 * 4 // 2
    assert (
        report.mutual_pair_count
        + report.one_way_pair_count
        + report.unreachable_pair_count
        == total_unordered
    )


# ---------------------------------------------------------------------------
# Mutual reachability matches SCC structure.
# ---------------------------------------------------------------------------

def test_mutual_pairs_zero_for_dag() -> None:
    # A pure DAG has no mutual reachability.
    report = measure_graph_directed_reachability(
        ["A", "B", "C"], [("A", "B"), ("B", "C"), ("A", "C")]
    )
    assert report.mutual_pair_count == 0


# ---------------------------------------------------------------------------
# Self-loops, dedup, directionality.
# ---------------------------------------------------------------------------

def test_self_loops_excluded_and_counted() -> None:
    # A -> A (self-loop) + 3-cycle. Self-loop never inflates reachability.
    report = measure_graph_directed_reachability(
        ["A", "B", "C"], [("A", "A"), ("A", "B"), ("B", "C"), ("C", "A")]
    )
    assert report.self_loop_count == 1
    assert report.reachability_ratio == 1.0
    assert report.verdict == "fully_navigable"


def test_parallel_edges_deduped() -> None:
    # A -> B twice -> one edge. ratio=0.5.
    report = measure_graph_directed_reachability(["A", "B"], [("A", "B"), ("A", "B")])
    assert report.directed_edge_count == 1
    assert report.reachability_ratio == pytest.approx(0.5)


def test_directionality_matters() -> None:
    # A -> B -> C (reachable A->C) vs C -> B -> A (reachable C->A). Same ratio, but the
    # reach DIRECTION flips — confirming edges are directed (not symmetric).
    fwd = measure_graph_directed_reachability(
        ["A", "B", "C"], [("A", "B"), ("B", "C")]
    )
    bwd = measure_graph_directed_reachability(
        ["A", "B", "C"], [("C", "B"), ("B", "A")]
    )
    # Both chains have the same ratio (0.5) and one_way breakdown by symmetry.
    assert fwd.reachability_ratio == pytest.approx(0.5)
    assert bwd.reachability_ratio == pytest.approx(0.5)
    assert fwd.one_way_pair_count == 3
    assert bwd.one_way_pair_count == 3


# ---------------------------------------------------------------------------
# Threshold validation.
# ---------------------------------------------------------------------------

def test_thresholds_out_of_order_raise() -> None:
    with pytest.raises(ValueError):
        measure_graph_directed_reachability(
            ["A", "B"], [("A", "B")], navigable_threshold=0.2, sparse_threshold=0.8
        )


def test_threshold_above_one_raises() -> None:
    with pytest.raises(ValueError):
        measure_graph_directed_reachability(
            ["A", "B"], [("A", "B")], navigable_threshold=1.5
        )


def test_custom_thresholds_flip_verdict() -> None:
    # Chain ratio 0.5: below default navigable 0.70 (moderate), above 0.40 (highly).
    edges = [("A", "B"), ("B", "C")]
    assert (
        measure_graph_directed_reachability(["A", "B", "C"], edges).verdict
        == "moderately_navigable"
    )
    assert (
        measure_graph_directed_reachability(
            ["A", "B", "C"], edges, navigable_threshold=0.40, sparse_threshold=0.10
        ).verdict
        == "highly_navigable"
    )


# ---------------------------------------------------------------------------
# Determinism + immutability.
# ---------------------------------------------------------------------------

def test_deterministic_across_input_order() -> None:
    edges = [("B", "A"), ("A", "C"), ("C", "B"), ("A", "D")]
    nodes = ["A", "B", "C", "D"]
    first = measure_graph_directed_reachability(nodes, edges)
    second = measure_graph_directed_reachability(
        list(reversed(nodes)), list(reversed(edges))
    )
    assert first == second


def test_report_is_frozen() -> None:
    report = measure_graph_directed_reachability(["A", "B"], [("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.reachability_ratio = 0.0  # type: ignore[misc]


def test_authority_is_advisory() -> None:
    report = measure_graph_directed_reachability(["A", "B"], [("A", "B")])
    assert report.authority == "advisory"


def test_ratio_none_only_for_unknown_or_singleton() -> None:
    assert measure_graph_directed_reachability([], []).reachability_ratio is None
    assert measure_graph_directed_reachability(["A"], []).reachability_ratio is None
    # Two nodes with no edges: honest 0.0, NOT None.
    assert measure_graph_directed_reachability(["A", "B"], []).reachability_ratio == 0.0

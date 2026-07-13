"""Tests for the graph reciprocity axis (ask #1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_reciprocity import (
    measure_graph_reciprocity,
)

# ---------------------------------------------------------------------------
# Base cases — honest defer states.
# ---------------------------------------------------------------------------

def test_zero_nodes_is_unknown() -> None:
    report = measure_graph_reciprocity([], [])
    assert report.verdict == "unknown"
    assert report.node_count == 0
    assert report.directed_edge_count == 0
    assert report.reciprocity_ratio is None
    assert report.mutual_pairs == ()


def test_one_node_no_edges_is_singleton() -> None:
    report = measure_graph_reciprocity(["A"], [])
    assert report.verdict == "singleton"
    assert report.node_count == 1
    assert report.directed_edge_count == 0
    assert report.reciprocity_ratio is None


def test_one_node_with_self_loop_is_singleton() -> None:
    report = measure_graph_reciprocity(["A"], [("A", "A")])
    assert report.verdict == "singleton"
    assert report.self_loop_count == 1
    assert report.directed_edge_count == 0
    assert report.reciprocity_ratio is None


def test_two_nodes_no_edges_is_no_directed_edges() -> None:
    report = measure_graph_reciprocity(["A", "B"], [])
    assert report.verdict == "no_directed_edges"
    assert report.node_count == 2
    assert report.directed_edge_count == 0
    assert report.reciprocity_ratio is None
    # None is NEVER a fabricated 0.0 — distinct from acyclic's real 0.0.
    assert report.mutual_pair_count == 0


# ---------------------------------------------------------------------------
# Acyclic — fully one-way (real measured 0.0).
# ---------------------------------------------------------------------------

def test_acyclic_chain_is_zero_reciprocity() -> None:
    # A -> B -> C, all one-way. m=3, reciprocated=0, ratio=0.0.
    report = measure_graph_reciprocity(
        ["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "D")]
    )
    assert report.verdict == "acyclic"
    assert report.directed_edge_count == 3
    assert report.mutual_pair_count == 0
    assert report.reciprocated_edge_count == 0
    assert report.asymmetric_edge_count == 3
    assert report.reciprocity_ratio == 0.0
    assert report.mutual_pairs == ()


def test_single_directed_edge_is_acyclic() -> None:
    # One-way citation only. ratio = 0.0.
    report = measure_graph_reciprocity(["A", "B"], [("A", "B")])
    assert report.verdict == "acyclic"
    assert report.directed_edge_count == 1
    assert report.reciprocity_ratio == 0.0


# ---------------------------------------------------------------------------
# Highly reciprocal — dialogic substrate.
# ---------------------------------------------------------------------------

def test_mutual_plus_oneway_is_highly_reciprocal() -> None:
    # A<->B (mutual), B->C (one-way). m=3, reciprocated=2, ratio=2/3 ~= 0.667.
    report = measure_graph_reciprocity(
        ["A", "B", "C"], [("A", "B"), ("B", "A"), ("B", "C")]
    )
    assert report.verdict == "highly_reciprocal"
    assert report.directed_edge_count == 3
    assert report.mutual_pair_count == 1
    assert report.reciprocated_edge_count == 2
    assert report.asymmetric_edge_count == 1
    assert report.reciprocity_ratio == pytest.approx(2.0 / 3.0)
    assert report.mutual_pairs == (("A", "B"),)


def test_fully_reciprocal_two_pair_is_ratio_one() -> None:
    # A<->B, C<->D. m=4, reciprocated=4, ratio=1.0.
    report = measure_graph_reciprocity(
        ["A", "B", "C", "D"],
        [("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")],
    )
    assert report.verdict == "highly_reciprocal"
    assert report.directed_edge_count == 4
    assert report.mutual_pair_count == 2
    assert report.reciprocated_edge_count == 4
    assert report.asymmetric_edge_count == 0
    assert report.reciprocity_ratio == 1.0
    assert report.mutual_pairs == (("A", "B"), ("C", "D"))


# ---------------------------------------------------------------------------
# Partially reciprocal — mix of exchange and one-way.
# ---------------------------------------------------------------------------

def test_partially_reciprocal_below_default_threshold() -> None:
    # A<->B (mutual, 2 edges) + B->C, C->D, D->E (3 one-way). m=5, ratio=2/5=0.4.
    report = measure_graph_reciprocity(
        ["A", "B", "C", "D", "E"],
        [("A", "B"), ("B", "A"), ("B", "C"), ("C", "D"), ("D", "E")],
    )
    assert report.verdict == "partially_reciprocal"
    assert report.directed_edge_count == 5
    assert report.mutual_pair_count == 1
    assert report.reciprocated_edge_count == 2
    assert report.asymmetric_edge_count == 3
    assert report.reciprocity_ratio == pytest.approx(0.4)


def test_custom_threshold_flips_verdict() -> None:
    # ratio 0.4: below default 0.50 (partially) but above 0.30 (highly).
    edges = [("A", "B"), ("B", "A"), ("B", "C"), ("C", "D"), ("D", "E")]
    assert measure_graph_reciprocity(
        ["A", "B", "C", "D", "E"], edges
    ).verdict == "partially_reciprocal"
    assert (
        measure_graph_reciprocity(
            ["A", "B", "C", "D", "E"], edges, reciprocal_threshold=0.30
        ).verdict
        == "highly_reciprocal"
    )


# ---------------------------------------------------------------------------
# Dedup, self-loops, directionality.
# ---------------------------------------------------------------------------

def test_parallel_directed_edges_deduped() -> None:
    # A->B twice -> one distinct edge. With B->A: m=2, ratio=1.0.
    report = measure_graph_reciprocity(
        ["A", "B"], [("A", "B"), ("A", "B"), ("B", "A")]
    )
    assert report.directed_edge_count == 2
    assert report.mutual_pair_count == 1
    assert report.reciprocity_ratio == 1.0


def test_self_loops_excluded_and_counted() -> None:
    # A->A (self-loop), A->B, B->A -> self_loop_count=1, m=2, ratio=1.0.
    report = measure_graph_reciprocity(
        ["A", "B"], [("A", "A"), ("A", "B"), ("B", "A")]
    )
    assert report.self_loop_count == 1
    assert report.directed_edge_count == 2
    assert report.mutual_pair_count == 1
    assert report.reciprocity_ratio == 1.0


def test_directionality_matters_one_way_is_acyclic() -> None:
    # A->B only (no B->A). Confirms edges are directed: ratio=0, not mutual.
    report = measure_graph_reciprocity(["A", "B"], [("A", "B"), ("A", "B")])
    assert report.directed_edge_count == 1
    assert report.reciprocity_ratio == 0.0
    assert report.verdict == "acyclic"


def test_mutual_pairs_sorted_asc() -> None:
    # Out-of-order input; mutual pairs must surface sorted by (min, max).
    report = measure_graph_reciprocity(
        ["D", "C", "B", "A"],
        [("C", "D"), ("D", "C"), ("A", "B"), ("B", "A")],
    )
    assert report.mutual_pairs == (("A", "B"), ("C", "D"))


# ---------------------------------------------------------------------------
# Validation.
# ---------------------------------------------------------------------------

def test_threshold_zero_raises() -> None:
    with pytest.raises(ValueError):
        measure_graph_reciprocity(["A", "B"], [("A", "B")], reciprocal_threshold=0.0)


def test_threshold_above_one_raises() -> None:
    with pytest.raises(ValueError):
        measure_graph_reciprocity(["A", "B"], [("A", "B")], reciprocal_threshold=1.5)


def test_threshold_one_is_valid() -> None:
    report = measure_graph_reciprocity(
        ["A", "B"], [("A", "B"), ("B", "A")], reciprocal_threshold=1.0
    )
    assert report.verdict == "highly_reciprocal"


# ---------------------------------------------------------------------------
# Determinism + immutability.
# ---------------------------------------------------------------------------

def test_deterministic_across_calls() -> None:
    edges = [("B", "A"), ("A", "B"), ("C", "B"), ("D", "C"), ("A", "D"), ("D", "A")]
    nodes = ["A", "B", "C", "D"]
    first = measure_graph_reciprocity(nodes, edges)
    second = measure_graph_reciprocity(list(reversed(nodes)), list(reversed(edges)))
    assert first == second


def test_report_is_frozen() -> None:
    report = measure_graph_reciprocity(["A", "B"], [("A", "B"), ("B", "A")])
    with pytest.raises(FrozenInstanceError):
        report.reciprocity_ratio = 0.0  # type: ignore[misc]


def test_authority_is_advisory() -> None:
    report = measure_graph_reciprocity(["A", "B"], [("A", "B")])
    assert report.authority == "advisory"

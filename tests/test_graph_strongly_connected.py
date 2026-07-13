"""Tests for the graph strongly-connected-components axis (ask #1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_strongly_connected import (
    measure_graph_strongly_connected,
)

# ---------------------------------------------------------------------------
# Base cases — honest defer states.
# ---------------------------------------------------------------------------

def test_zero_nodes_is_unknown() -> None:
    report = measure_graph_strongly_connected([], [])
    assert report.verdict == "unknown"
    assert report.scc_count == 0
    assert report.largest_scc_fraction is None
    assert report.scc_sizes == ()


def test_one_node_is_singleton() -> None:
    report = measure_graph_strongly_connected(["A"], [])
    assert report.verdict == "singleton"
    assert report.scc_count == 1
    assert report.largest_scc_size == 1
    assert report.largest_scc_fraction == 1.0
    assert report.is_dag is True
    assert report.scc_sizes == (1,)


def test_two_nodes_no_edges_is_no_directed_edges() -> None:
    report = measure_graph_strongly_connected(["A", "B"], [])
    assert report.verdict == "no_directed_edges"
    assert report.scc_count == 2
    assert report.largest_scc_fraction == 0.5
    assert report.is_dag is True
    assert report.scc_sizes == (1, 1)


# ---------------------------------------------------------------------------
# Acyclic — clean DAG hierarchy.
# ---------------------------------------------------------------------------

def test_chain_is_acyclic() -> None:
    # A -> B -> C. No cycles: 3 trivial SCCs, is_dag True.
    report = measure_graph_strongly_connected(
        ["A", "B", "C"], [("A", "B"), ("B", "C")]
    )
    assert report.verdict == "acyclic"
    assert report.scc_count == 3
    assert report.trivial_scc_count == 3
    assert report.nontrivial_scc_count == 0
    assert report.is_dag is True
    assert report.largest_scc_size == 1
    assert report.largest_scc_fraction == pytest.approx(1.0 / 3.0)


def test_dag_tree_is_acyclic() -> None:
    # A -> B, A -> C, B -> D, C -> D. No cycles.
    report = measure_graph_strongly_connected(
        ["A", "B", "C", "D"],
        [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
    )
    assert report.verdict == "acyclic"
    assert report.scc_count == 4
    assert report.is_dag is True


# ---------------------------------------------------------------------------
# Strongly connected — total feedback closure.
# ---------------------------------------------------------------------------

def test_three_cycle_is_strongly_connected() -> None:
    # A -> B -> C -> A. One SCC of size 3.
    report = measure_graph_strongly_connected(
        ["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")]
    )
    assert report.verdict == "strongly_connected"
    assert report.scc_count == 1
    assert report.largest_scc_size == 3
    assert report.largest_scc_fraction == 1.0
    assert report.nontrivial_scc_count == 1
    assert report.is_dag is False
    assert report.scc_sizes == (3,)


def test_five_cycle_is_strongly_connected_zero_reciprocity() -> None:
    # A -> B -> C -> D -> E -> A. Every edge one-way (reciprocity 0) yet ONE SCC.
    # Proves distinctness from reciprocity: no direct back-edge, but total cyclic closure.
    report = measure_graph_strongly_connected(
        ["A", "B", "C", "D", "E"],
        [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("E", "A")],
    )
    assert report.verdict == "strongly_connected"
    assert report.scc_count == 1
    assert report.largest_scc_size == 5
    assert report.is_dag is False


# ---------------------------------------------------------------------------
# Partially cyclic — feedback clusters in a larger structure.
# ---------------------------------------------------------------------------

def test_cycle_plus_chain_is_partially_cyclic() -> None:
    # A <-> B (SCC {A,B}), C -> D (two trivial SCCs).
    report = measure_graph_strongly_connected(
        ["A", "B", "C", "D"], [("A", "B"), ("B", "A"), ("C", "D")]
    )
    assert report.verdict == "partially_cyclic"
    assert report.scc_count == 3
    assert report.largest_scc_size == 2
    assert report.largest_scc_fraction == 0.5
    assert report.nontrivial_scc_count == 1
    assert report.trivial_scc_count == 2
    assert report.is_dag is False
    assert report.scc_sizes == (2, 1, 1)


def test_two_separate_cycles_is_partially_cyclic() -> None:
    # A <-> B, C <-> D. Two nontrivial SCCs, scc_count 2 (>1) -> partially_cyclic.
    report = measure_graph_strongly_connected(
        ["A", "B", "C", "D"],
        [("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")],
    )
    assert report.verdict == "partially_cyclic"
    assert report.scc_count == 2
    assert report.nontrivial_scc_count == 2
    assert report.largest_scc_size == 2
    assert report.largest_scc_fraction == 0.5
    assert report.scc_sizes == (2, 2)


def test_cycle_with_tail_is_partially_cyclic() -> None:
    # A -> B -> C -> A (cycle), C -> D (tail out of the cycle).
    report = measure_graph_strongly_connected(
        ["A", "B", "C", "D"],
        [("A", "B"), ("B", "C"), ("C", "A"), ("C", "D")],
    )
    assert report.verdict == "partially_cyclic"
    assert report.scc_count == 2  # {A,B,C} and {D}
    assert report.largest_scc_size == 3
    assert report.largest_scc_fraction == 0.75
    assert report.nontrivial_scc_count == 1
    assert report.scc_sizes == (3, 1)


# ---------------------------------------------------------------------------
# Self-loops, dedup, directionality.
# ---------------------------------------------------------------------------

def test_self_loops_excluded_and_counted() -> None:
    # A -> A (self-loop), plus 3-cycle A -> B -> C -> A.
    report = measure_graph_strongly_connected(
        ["A", "B", "C"],
        [("A", "A"), ("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert report.self_loop_count == 1
    assert report.scc_count == 1
    assert report.largest_scc_size == 3
    assert report.verdict == "strongly_connected"


def test_parallel_edges_deduped() -> None:
    # A -> B twice, B -> A -> still SCC {A,B}, directed_edge_count 2.
    report = measure_graph_strongly_connected(
        ["A", "B"], [("A", "B"), ("A", "B"), ("B", "A")]
    )
    assert report.directed_edge_count == 2
    assert report.scc_count == 1
    assert report.largest_scc_size == 2


def test_directionality_matters() -> None:
    # A -> B -> C (chain, acyclic) vs adding C -> A (cyclic). Directionality decides.
    chain = measure_graph_strongly_connected(
        ["A", "B", "C"], [("A", "B"), ("B", "C")]
    )
    assert chain.is_dag is True
    assert chain.verdict == "acyclic"
    cycle = measure_graph_strongly_connected(
        ["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")]
    )
    assert cycle.is_dag is False
    assert cycle.verdict == "strongly_connected"


# ---------------------------------------------------------------------------
# Determinism + immutability.
# ---------------------------------------------------------------------------

def test_deterministic_across_input_order() -> None:
    edges = [("B", "A"), ("A", "B"), ("C", "D"), ("D", "C"), ("A", "D")]
    nodes = ["A", "B", "C", "D"]
    first = measure_graph_strongly_connected(nodes, edges)
    second = measure_graph_strongly_connected(
        list(reversed(nodes)), list(reversed(edges))
    )
    assert first == second


def test_report_is_frozen() -> None:
    report = measure_graph_strongly_connected(["A", "B"], [("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.is_dag = False  # type: ignore[misc]


def test_authority_is_advisory() -> None:
    report = measure_graph_strongly_connected(["A", "B"], [("A", "B")])
    assert report.authority == "advisory"


def test_largest_scc_fraction_none_only_for_unknown() -> None:
    assert measure_graph_strongly_connected([], []).largest_scc_fraction is None
    assert measure_graph_strongly_connected(["A"], []).largest_scc_fraction == 1.0
    assert (
        measure_graph_strongly_connected(["A", "B"], []).largest_scc_fraction == 0.5
    )

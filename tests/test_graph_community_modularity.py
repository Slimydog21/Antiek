"""Tests for the graph community-modularity axis (ask #1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_community_modularity import (
    measure_graph_community_modularity,
)

# ---------------------------------------------------------------------------
# Base cases — honest defer states.
# ---------------------------------------------------------------------------

def test_zero_nodes_is_unknown() -> None:
    report = measure_graph_community_modularity([], [])
    assert report.verdict == "unknown"
    assert report.community_count == 0
    assert report.modularity is None
    assert report.largest_community_fraction is None


def test_one_node_is_singleton() -> None:
    report = measure_graph_community_modularity(["A"], [])
    assert report.verdict == "singleton"
    assert report.community_count == 1
    assert report.largest_community_fraction == 1.0
    assert report.modularity is None


def test_two_nodes_no_edges_is_atomized() -> None:
    report = measure_graph_community_modularity(["A", "B"], [])
    assert report.verdict == "atomized"
    assert report.community_count == 2
    assert report.largest_community_fraction == 0.5
    # None is NEVER a fabricated 0.0 — distinct from single_community's measured 0.0.
    assert report.modularity is None


# ---------------------------------------------------------------------------
# Two triangles joined by a bridge — the canonical modular graph.
# ---------------------------------------------------------------------------

def test_two_triangles_bridged_is_modular() -> None:
    # A-B-C triangle + D-E-F triangle + bridge C-D. 7 edges, 6 nodes.
    # Greedy keeps two communities (bridge merge has NEGATIVE gain).
    # Q = 2 * [3/7 - (7/14)^2] = 2 * [0.4286 - 0.25] = 0.3571.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E", "F"],
        [
            ("A", "B"), ("A", "C"), ("B", "C"),  # triangle 1
            ("D", "E"), ("D", "F"), ("E", "F"),  # triangle 2
            ("C", "D"),  # bridge
        ],
    )
    assert report.verdict == "modular"
    assert report.community_count == 2
    assert report.modularity == pytest.approx(0.3571, abs=0.005)
    assert report.largest_community_fraction == pytest.approx(0.5)
    assert report.community_sizes == (3, 3)


# ---------------------------------------------------------------------------
# Two separate cliques (no bridge) — maximally modular.
# ---------------------------------------------------------------------------

def test_two_separate_cliques_are_modular() -> None:
    # K3 + K3, no connection. 6 edges, 6 nodes.
    # Q = 2 * [3/6 - (6/12)^2] = 2 * [0.5 - 0.25] = 0.5.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E", "F"],
        [
            ("A", "B"), ("A", "C"), ("B", "C"),
            ("D", "E"), ("D", "F"), ("E", "F"),
        ],
    )
    assert report.verdict == "modular"
    assert report.community_count == 2
    assert report.modularity == pytest.approx(0.5)
    assert report.community_sizes == (3, 3)


# ---------------------------------------------------------------------------
# Dense graph collapses to one community.
# ---------------------------------------------------------------------------

def test_clique_collapses_to_single_community() -> None:
    # K4 — every gain is positive, greedy merges all into one. Q=0.0.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D"],
        [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")],
    )
    assert report.verdict == "single_community"
    assert report.community_count == 1
    # single_community carries honest measured 0.0, NOT None.
    assert report.modularity == pytest.approx(0.0)
    assert report.largest_community_fraction == 1.0


def test_single_edge_is_single_community() -> None:
    # A-B. gain = 1 - 0.25 = 0.75 > 0. Merge into one.
    report = measure_graph_community_modularity(["A", "B"], [("A", "B")])
    assert report.verdict == "single_community"
    assert report.community_count == 1
    assert report.modularity == pytest.approx(0.0)


def test_chain_collapses_to_single_community() -> None:
    # A-B-C. All gains positive -> one community. A chain has no community structure.
    report = measure_graph_community_modularity(
        ["A", "B", "C"], [("A", "B"), ("B", "C")]
    )
    assert report.verdict == "single_community"
    assert report.community_count == 1


def test_star_collapses_to_single_community() -> None:
    # Center A connected to B,C,D,E. All gains positive -> one community.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E"],
        [("A", "B"), ("A", "C"), ("A", "D"), ("A", "E")],
    )
    assert report.verdict == "single_community"
    assert report.community_count == 1


# ---------------------------------------------------------------------------
# Weakly modular — communities exist but below threshold.
# ---------------------------------------------------------------------------

def test_weakly_modular_below_threshold() -> None:
    # Two triangles bridged has Q ~0.357 >= 0.30 (modular).
    # With threshold raised to 0.40 -> weakly_modular.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E", "F"],
        [
            ("A", "B"), ("A", "C"), ("B", "C"),
            ("D", "E"), ("D", "F"), ("E", "F"),
            ("C", "D"),
        ],
        modular_threshold=0.40,
    )
    assert report.community_count == 2
    assert report.verdict == "weakly_modular"


# ---------------------------------------------------------------------------
# Merges auditable: n - community_count.
# ---------------------------------------------------------------------------

def test_merges_performed_is_node_minus_community() -> None:
    # Two triangles bridged: 6 nodes -> 2 communities -> 4 merges.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E", "F"],
        [
            ("A", "B"), ("A", "C"), ("B", "C"),
            ("D", "E"), ("D", "F"), ("E", "F"),
            ("C", "D"),
        ],
    )
    assert report.merges_performed == 6 - 2


def test_merges_zero_when_single_community_from_collapse() -> None:
    # K4: 4 nodes collapse to 1 community -> 3 merges.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D"],
        [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")],
    )
    assert report.merges_performed == 4 - 1


# ---------------------------------------------------------------------------
# Self-loops, dedup, determinism.
# ---------------------------------------------------------------------------

def test_self_loops_excluded_and_counted() -> None:
    # A-A self-loop + two triangles bridged.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E", "F"],
        [
            ("A", "A"),
            ("A", "B"), ("A", "C"), ("B", "C"),
            ("D", "E"), ("D", "F"), ("E", "F"),
            ("C", "D"),
        ],
    )
    assert report.self_loop_count == 1
    assert report.verdict == "modular"
    assert report.community_count == 2


def test_parallel_edges_deduped() -> None:
    # A-B twice + A-C + B-C (triangle with duplicate edge).
    report = measure_graph_community_modularity(
        ["A", "B", "C"], [("A", "B"), ("A", "B"), ("A", "C"), ("B", "C")]
    )
    assert report.edge_count == 3  # deduped
    assert report.verdict == "single_community"


def test_deterministic_across_input_order() -> None:
    edges = [
        ("A", "B"), ("A", "C"), ("B", "C"),
        ("D", "E"), ("D", "F"), ("E", "F"),
        ("C", "D"),
    ]
    nodes = ["A", "B", "C", "D", "E", "F"]
    first = measure_graph_community_modularity(nodes, edges)
    second = measure_graph_community_modularity(
        list(reversed(nodes)), list(reversed(edges))
    )
    assert first == second


def test_three_clusters_is_modular() -> None:
    # Three separate edges (A-B, C-D, E-F) — three 2-node communities.
    # Each edge: L_ab=1, D_a=D_b=1. Q per community = 1/3 - (2/6)^2 = 0.3333 - 0.1111 = 0.2222.
    # But greedy: gain for A,B = 1/3 - (1*1)/(6^2) = 0.3333 - 0.0278 = 0.3056 > 0 -> merge.
    # gain for {A,B}+C: cross=0 (not adjacent) -> no merge. So 3 communities.
    # Q = 3 * [1/3 - (2/6)^2] = 3 * 0.2222 = 0.6667. Highly modular.
    report = measure_graph_community_modularity(
        ["A", "B", "C", "D", "E", "F"],
        [("A", "B"), ("C", "D"), ("E", "F")],
    )
    assert report.community_count == 3
    assert report.modularity == pytest.approx(2.0 / 3.0, abs=0.01)
    assert report.verdict == "modular"
    assert report.community_sizes == (2, 2, 2)


# ---------------------------------------------------------------------------
# Validation + immutability.
# ---------------------------------------------------------------------------

def test_threshold_above_one_raises() -> None:
    with pytest.raises(ValueError):
        measure_graph_community_modularity(["A", "B"], [("A", "B")], modular_threshold=1.5)


def test_threshold_negative_raises() -> None:
    with pytest.raises(ValueError):
        measure_graph_community_modularity(["A", "B"], [("A", "B")], modular_threshold=-0.1)


def test_report_is_frozen() -> None:
    report = measure_graph_community_modularity(["A", "B"], [("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.modularity = 0.5  # type: ignore[misc]


def test_authority_is_advisory() -> None:
    report = measure_graph_community_modularity(["A", "B"], [("A", "B")])
    assert report.authority == "advisory"


def test_modularity_none_only_for_defer_states() -> None:
    assert measure_graph_community_modularity([], []).modularity is None
    assert measure_graph_community_modularity(["A"], []).modularity is None
    assert measure_graph_community_modularity(["A", "B"], []).modularity is None
    # Edges exist -> measured, never None.
    assert measure_graph_community_modularity(["A", "B"], [("A", "B")]).modularity == 0.0

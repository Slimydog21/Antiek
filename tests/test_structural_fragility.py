"""Tests for the structural-fragility axis (ask #1 — knowledge-graph single-points-of-failure).

Every fixture is hand-verified: articulation points and bridges are determined by inspection
of the graph topology before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.structural_fragility import (
    StructuralFragilityReport,
    measure_structural_fragility,
)

# ---------------------------------------------------------------------------
# Unknown / base cases.
# ---------------------------------------------------------------------------


def test_unknown_empty_graph() -> None:
    report = measure_structural_fragility(nodes=[], edges=[])
    assert report.total_node_count == 0
    assert report.component_count == 0
    assert report.articulation_point_count == 0
    assert report.articulation_point_ids == ()
    assert report.bridge_count == 0
    assert report.fragility_ratio is None
    assert report.max_fragmentation is None
    assert report.verdict == "unknown"
    assert report.authority == "advisory"


def test_singleton_one_node() -> None:
    report = measure_structural_fragility(nodes=["A"], edges=[])
    assert report.total_node_count == 1
    assert report.component_count == 1
    assert report.articulation_point_count == 0
    assert report.bridge_count == 0
    assert report.fragility_ratio is None
    assert report.max_fragmentation is None
    assert report.verdict == "singleton"


def test_edgeless_multiple_nodes_no_edges() -> None:
    report = measure_structural_fragility(nodes=["A", "B", "C"], edges=[])
    assert report.total_node_count == 3
    assert report.component_count == 3
    assert report.articulation_point_count == 0
    assert report.bridge_count == 0
    assert report.fragility_ratio is None
    assert report.verdict == "edgeless"


# ---------------------------------------------------------------------------
# Robust — biconnected (zero APs, zero bridges).
# ---------------------------------------------------------------------------


def test_robust_triangle() -> None:
    # Triangle A-B-C: 2-connected. Removing any node leaves a 2-node edge (still 1 comp).
    report = measure_structural_fragility(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert report.articulation_point_count == 0
    assert report.bridge_count == 0
    assert report.fragility_ratio == pytest.approx(0.0)
    assert report.max_fragmentation is None
    assert report.verdict == "robust"


def test_robust_complete_graph_k4() -> None:
    edges = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"), ("C", "D"),
    ]
    report = measure_structural_fragility(nodes=["A", "B", "C", "D"], edges=edges)
    assert report.articulation_point_count == 0
    assert report.bridge_count == 0
    assert report.verdict == "robust"


def test_robust_square_cycle() -> None:
    # Cycle A-B-C-D-A: 2-connected (removing any node leaves a path, still connected).
    report = measure_structural_fragility(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")],
    )
    assert report.articulation_point_count == 0
    assert report.bridge_count == 0
    assert report.verdict == "robust"


# ---------------------------------------------------------------------------
# Fragile — articulation points exist.
# ---------------------------------------------------------------------------


def test_fragile_path_p4() -> None:
    # Path A-B-C-D. APs: B and C (each removal splits the path).
    # Bridges: all 3 edges (every edge in a path is a bridge).
    report = measure_structural_fragility(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "C"), ("C", "D")],
    )
    assert report.articulation_point_count == 2
    assert report.articulation_point_ids == ("B", "C")
    assert report.bridge_count == 3
    assert report.bridge_edges == (("A", "B"), ("B", "C"), ("C", "D"))
    assert report.fragility_ratio == pytest.approx(2 / 4)
    assert report.max_fragmentation == 2  # removing B or C -> 2 components
    assert report.verdict == "fragile"


def test_fragile_star_k14() -> None:
    # Star: center A connected to B,C,D,E. AP: A (4 DFS-tree children >= 2).
    report = measure_structural_fragility(
        nodes=["A", "B", "C", "D", "E"],
        edges=[("A", "B"), ("A", "C"), ("A", "D"), ("A", "E")],
    )
    assert report.articulation_point_count == 1
    assert report.articulation_point_ids == ("A",)
    assert report.bridge_count == 4
    assert report.max_fragmentation == 4  # removing A -> 4 isolated nodes
    assert report.fragility_ratio == pytest.approx(1 / 5)
    assert report.verdict == "fragile"


def test_fragile_friendship_graph_f3() -> None:
    # 3 triangles sharing center O. Removing O -> 3 components (each pair stays connected).
    edges = [
        ("O", "A1"), ("O", "B1"), ("A1", "B1"),
        ("O", "A2"), ("O", "B2"), ("A2", "B2"),
        ("O", "A3"), ("O", "B3"), ("A3", "B3"),
    ]
    nodes = ["O", "A1", "B1", "A2", "B2", "A3", "B3"]
    report = measure_structural_fragility(nodes=nodes, edges=edges)
    assert report.articulation_point_count == 1
    assert report.articulation_point_ids == ("O",)
    assert report.max_fragmentation == 3
    assert report.bridge_count == 0  # within each triangle, no bridge
    assert report.verdict == "fragile"


# ---------------------------------------------------------------------------
# Bridge-fragile — bridges but zero APs.
# ---------------------------------------------------------------------------


def test_bridge_fragile_single_edge() -> None:
    # Two nodes, one edge. Neither node is an AP (removal leaves 1 node = 1 comp).
    # But the edge is a bridge (removal -> 2 components).
    report = measure_structural_fragility(nodes=["A", "B"], edges=[("A", "B")])
    assert report.articulation_point_count == 0
    assert report.bridge_count == 1
    assert report.bridge_edges == (("A", "B"),)
    assert report.fragility_ratio == pytest.approx(0.0)
    assert report.max_fragmentation is None
    assert report.verdict == "bridge_fragile"


# ---------------------------------------------------------------------------
# Edge cases: self-loops, duplicates, disconnected.
# ---------------------------------------------------------------------------


def test_self_loop_dropped() -> None:
    report = measure_structural_fragility(
        nodes=["A", "B"],
        edges=[("A", "A"), ("A", "B")],
    )
    assert report.total_node_count == 2
    assert report.bridge_count == 1
    assert report.verdict == "bridge_fragile"


def test_duplicate_edges_merged() -> None:
    # Duplicate edges collapse — same as a simple path.
    report = measure_structural_fragility(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("A", "B"), ("B", "C"), ("B", "C")],
    )
    assert report.articulation_point_count == 1
    assert report.articulation_point_ids == ("B",)
    assert report.bridge_count == 2


def test_disconnected_graph_with_internal_aps() -> None:
    # Two disjoint paths: A-B-C and D-E-F. APs: B and E (one per component).
    report = measure_structural_fragility(
        nodes=["A", "B", "C", "D", "E", "F"],
        edges=[("A", "B"), ("B", "C"), ("D", "E"), ("E", "F")],
    )
    assert report.component_count == 2
    assert report.articulation_point_count == 2
    assert report.articulation_point_ids == ("B", "E")


def test_edge_endpoints_included_even_if_not_in_nodes() -> None:
    # Node Z appears only in an edge, not in the nodes list — must be included.
    report = measure_structural_fragility(
        nodes=["A"],
        edges=[("A", "Z")],
    )
    assert report.total_node_count == 2
    assert report.verdict == "bridge_fragile"


# ---------------------------------------------------------------------------
# Determinism + immutability + report type.
# ---------------------------------------------------------------------------


def test_report_is_deterministic() -> None:
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    a = measure_structural_fragility(nodes=nodes, edges=edges)
    b = measure_structural_fragility(nodes=nodes, edges=edges)
    assert a == b


def test_report_is_frozen() -> None:
    report = measure_structural_fragility(nodes=["A", "B"], edges=[("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "robust"  # type: ignore[misc]


def test_report_type() -> None:
    report = measure_structural_fragility(nodes=["A", "B"], edges=[("A", "B")])
    assert isinstance(report, StructuralFragilityReport)
    assert report.authority == "advisory"

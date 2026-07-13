"""Tests for the graph-diameter stretch axis (ask #1).

Every fixture is hand-counted: node/edge counts, diameters, radii, and endpoints are
verified by inspection before the assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_diameter import (
    GraphDiameterReport,
    GraphEdge,
    measure_graph_diameter,
)


def edge(a: str, b: str) -> GraphEdge:
    return GraphEdge(source=a, target=b)


# ---------------------------------------------------------------------------
# Base cases — distinct honest states, never collapsed.
# ---------------------------------------------------------------------------


def test_empty_graph_is_unknown() -> None:
    report = measure_graph_diameter(nodes=[], edges=[])
    assert report.verdict == "unknown"
    assert report.node_count == 0
    assert report.diameter is None
    assert report.radius is None
    assert report.mean_eccentricity is None
    assert report.connected is None
    assert report.component_diameters == ()
    assert report.diameter_path_endpoints == ()
    assert report.authority == "advisory"


def test_singleton_is_its_own_base_case() -> None:
    report = measure_graph_diameter(nodes=["n1"], edges=[])
    assert report.verdict == "singleton"
    assert report.node_count == 1
    assert report.edge_count == 0
    assert report.diameter is None
    assert report.radius is None
    assert report.mean_eccentricity is None
    assert report.connected is None
    assert report.orphan_node_count == 1


def test_two_nodes_no_edges_is_edgeless() -> None:
    report = measure_graph_diameter(nodes=["n1", "n2"], edges=[])
    assert report.verdict == "edgeless"
    assert report.node_count == 2
    assert report.diameter is None
    assert report.connected is False
    assert report.orphan_node_count == 2


def test_singleton_distinct_from_unknown() -> None:
    assert measure_graph_diameter(nodes=[], edges=[]).verdict == "unknown"
    assert measure_graph_diameter(nodes=["n1"], edges=[]).verdict == "singleton"
    assert measure_graph_diameter(nodes=["n1", "n2"], edges=[]).verdict == "edgeless"


# ---------------------------------------------------------------------------
# Connected graphs — diameter, radius, endpoints, verdict bands.
# ---------------------------------------------------------------------------


def test_single_edge_pair_diameter_one_compact() -> None:
    report = measure_graph_diameter(nodes=["n1", "n2"], edges=[edge("n1", "n2")])
    assert report.verdict == "compact"
    assert report.diameter == 1
    assert report.radius == 1
    assert report.connected is True
    assert report.component_count == 1
    assert sorted(report.diameter_path_endpoints) == ["n1", "n2"]
    assert report.component_diameters == (1,)


def test_triangle_clique_diameter_one() -> None:
    report = measure_graph_diameter(
        nodes=["a", "b", "c"],
        edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")],
    )
    assert report.diameter == 1
    assert report.radius == 1
    assert report.mean_eccentricity == pytest.approx(1.0)
    assert report.verdict == "compact"
    assert report.connected is True


def test_path_of_five_diameter_four_compact() -> None:
    # a - b - c - d - e  (5 nodes, diameter 4)
    nodes = ["a", "b", "c", "d", "e"]
    edges = [
        edge("a", "b"),
        edge("b", "c"),
        edge("c", "d"),
        edge("d", "e"),
    ]
    report = measure_graph_diameter(nodes=nodes, edges=edges)
    assert report.diameter == 4
    assert report.radius == 2  # center node c is at most 2 from any node
    assert report.mean_eccentricity == pytest.approx(3.2)
    assert report.verdict == "compact"  # 4 <= default compact_threshold 4
    assert report.diameter_path_endpoints == ("a", "e")
    assert report.component_diameters == (4,)
    assert report.connected is True


def test_star_diameter_two() -> None:
    # center c, leaves a b d
    report = measure_graph_diameter(
        nodes=["c", "a", "b", "d"],
        edges=[edge("c", "a"), edge("c", "b"), edge("c", "d")],
    )
    assert report.diameter == 2  # any leaf to any other leaf via center
    assert report.radius == 1  # the center reaches everyone in 1 hop
    assert report.mean_eccentricity == pytest.approx(1.75)
    assert report.verdict == "compact"


def test_long_path_is_stretched() -> None:
    # a 15-node path has diameter 14 (> default stretch_threshold 12)
    nodes = [f"n{i}" for i in range(15)]
    edges = [edge(f"n{i}", f"n{i + 1}") for i in range(14)]
    report = measure_graph_diameter(nodes=nodes, edges=edges)
    assert report.diameter == 14
    assert report.verdict == "stretched"
    assert report.diameter_path_endpoints == ("n0", "n14")
    assert report.connected is True


def test_extended_band_between_thresholds() -> None:
    # An 8-node path has diameter 7 (>4, <=12) -> extended
    nodes = [f"n{i}" for i in range(8)]
    edges = [edge(f"n{i}", f"n{i + 1}") for i in range(7)]
    report = measure_graph_diameter(nodes=nodes, edges=edges)
    assert report.diameter == 7
    assert report.verdict == "extended"


def test_radius_le_diameter_always() -> None:
    # Path of 5: radius 2, diameter 4 -> 2 <= 4.
    report = measure_graph_diameter(
        nodes=["a", "b", "c", "d", "e"],
        edges=[edge("a", "b"), edge("b", "c"), edge("c", "d"), edge("d", "e")],
    )
    assert report.radius is not None
    assert report.diameter is not None
    assert report.radius <= report.diameter
    assert report.diameter <= 2 * report.radius


# ---------------------------------------------------------------------------
# Disconnected graphs — honesty about unreachable pairs.
# ---------------------------------------------------------------------------


def test_disconnected_diameter_is_largest_intra_component_stretch() -> None:
    # Component 1: a - b - c (diameter 2). Component 2: d - e - f - g (diameter 3).
    report = measure_graph_diameter(
        nodes=["a", "b", "c", "d", "e", "f", "g"],
        edges=[
            edge("a", "b"),
            edge("b", "c"),
            edge("d", "e"),
            edge("e", "f"),
            edge("f", "g"),
        ],
    )
    assert report.connected is False
    assert report.component_count == 2
    assert report.diameter == 3  # NOT infinity — largest reachable stretch
    assert report.component_diameters == (3, 2)
    assert report.verdict == "compact"  # 3 <= 4
    assert any("disconnected" in note for note in report.notes)


def test_disconnected_cross_component_pair_unreachable() -> None:
    # a-b and c-d are two separate edges; a can never reach c.
    report = measure_graph_diameter(
        nodes=["a", "b", "c", "d"],
        edges=[edge("a", "b"), edge("c", "d")],
    )
    assert report.connected is False
    assert report.component_count == 2
    assert report.diameter == 1
    assert report.component_diameters == (1, 1)


# ---------------------------------------------------------------------------
# Edge integrity — self-loops, duplicates, dangling (mirror #1995/#1996).
# ---------------------------------------------------------------------------


def test_self_loops_ignored() -> None:
    report = measure_graph_diameter(
        nodes=["a", "b", "c"],
        edges=[edge("a", "a"), edge("a", "b"), edge("b", "b"), edge("b", "c")],
    )
    assert report.edge_count == 2  # only a-b and b-c
    assert report.diameter == 2  # path a - b - c


def test_duplicate_edges_merged() -> None:
    report = measure_graph_diameter(
        nodes=["a", "b"],
        edges=[
            edge("a", "b"),
            edge("a", "b"),
            edge("b", "a"),  # reversed duplicate
        ],
    )
    assert report.edge_count == 1
    assert report.diameter == 1


def test_dangling_edges_surfaced_not_coerced() -> None:
    # "ghost" is referenced by an edge but not declared as a node.
    report = measure_graph_diameter(
        nodes=["a", "b"],
        edges=[edge("a", "b"), edge("a", "ghost")],
    )
    assert report.edge_count == 1
    assert report.dangling_edge_count == 1
    assert report.diameter == 1


def test_orphan_nodes_counted() -> None:
    # c is connected; x and y are isolated orphans.
    report = measure_graph_diameter(
        nodes=["a", "b", "x", "y"],
        edges=[edge("a", "b")],
    )
    assert report.orphan_node_count == 2
    assert report.diameter == 1
    assert report.connected is False
    assert report.component_count == 3


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_compact_threshold_below_one_raises() -> None:
    with pytest.raises(ValueError, match="compact_threshold"):
        measure_graph_diameter(nodes=["a", "b"], edges=[edge("a", "b")], compact_threshold=0)


def test_stretch_below_compact_raises() -> None:
    with pytest.raises(ValueError, match="stretch_threshold"):
        measure_graph_diameter(
            nodes=["a", "b"],
            edges=[edge("a", "b")],
            compact_threshold=5,
            stretch_threshold=3,
        )


def test_custom_thresholds_reclassify_verdict() -> None:
    # 5-node path: diameter 4. Default -> compact. With compact_threshold=3 -> extended.
    nodes = ["a", "b", "c", "d", "e"]
    edges = [edge("a", "b"), edge("b", "c"), edge("c", "d"), edge("d", "e")]
    default = measure_graph_diameter(nodes=nodes, edges=edges)
    assert default.verdict == "compact"
    tightened = measure_graph_diameter(
        nodes=nodes, edges=edges, compact_threshold=3, stretch_threshold=12
    )
    assert tightened.verdict == "extended"
    assert tightened.compact_threshold == 3


def test_custom_stretch_threshold_makes_compact_stretched() -> None:
    # diameter 4, but stretch_threshold=2 -> stretched
    nodes = ["a", "b", "c", "d", "e"]
    edges = [edge("a", "b"), edge("b", "c"), edge("c", "d"), edge("d", "e")]
    report = measure_graph_diameter(
        nodes=nodes, edges=edges, compact_threshold=1, stretch_threshold=2
    )
    assert report.diameter == 4
    assert report.verdict == "stretched"


# ---------------------------------------------------------------------------
# Determinism + immutability + authority.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_graph_diameter(nodes=["a", "b"], edges=[edge("a", "b")])
    with pytest.raises(FrozenInstanceError):
        report.diameter = 99  # type: ignore[misc]


def test_deterministic_output() -> None:
    nodes = ["a", "b", "c", "d", "e"]
    edges = [edge("a", "b"), edge("b", "c"), edge("c", "d"), edge("d", "e")]
    first = measure_graph_diameter(nodes=nodes, edges=edges)
    second = measure_graph_diameter(nodes=nodes, edges=edges)
    assert first == second


def test_report_is_graph_diameter_report_instance() -> None:
    report = measure_graph_diameter(nodes=["a", "b"], edges=[edge("a", "b")])
    assert isinstance(report, GraphDiameterReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_graph_diameter(
        nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c")]
    )
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("diameter" in n.lower() for n in report.notes)


def test_component_diameters_sorted_descending() -> None:
    # Three components of stretch 1, 3, 2.
    report = measure_graph_diameter(
        nodes=["a", "b", "c", "d", "e", "f", "g", "p", "q"],
        edges=[
            edge("a", "b"),  # diameter 1
            edge("c", "d"),  # start of a 4-node path -> diameter 3
            edge("d", "e"),
            edge("e", "f"),
            edge("g", "p"),  # diameter 1
        ],
    )
    assert report.component_diameters == (3, 1, 1)

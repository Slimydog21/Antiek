"""Tests for the graph-betweenness axis (ask #1 — gateway-node identification).

Every fixture is hand-computed: betweenness values verified by enumerating shortest
paths before assertions are written. Brandes' algorithm produces exact results.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_betweenness import (
    GraphBetweennessReport,
    measure_graph_betweenness,
)

# ---------------------------------------------------------------------------
# Unknown / base cases.
# ---------------------------------------------------------------------------


def test_unknown_empty_graph() -> None:
    report = measure_graph_betweenness(nodes=[], edges=[])
    assert report.total_node_count == 0
    assert report.max_normalized_betweenness is None
    assert report.mean_betweenness is None
    assert report.gateway_node is None
    assert report.per_node == ()
    assert report.verdict == "unknown"
    assert report.authority == "advisory"


def test_singleton_one_node() -> None:
    report = measure_graph_betweenness(nodes=["A"], edges=[])
    assert report.total_node_count == 1
    assert report.max_normalized_betweenness is None
    assert report.verdict == "singleton"


def test_edgeless_multiple_nodes() -> None:
    report = measure_graph_betweenness(nodes=["A", "B", "C"], edges=[])
    assert report.total_node_count == 3
    assert report.max_normalized_betweenness is None
    assert report.verdict == "edgeless"


# ---------------------------------------------------------------------------
# Pairwise-only — zero betweenness (every pair directly connected).
# ---------------------------------------------------------------------------


def test_pairwise_only_single_edge() -> None:
    # Two nodes, one edge: no node is on a path between two OTHERS.
    report = measure_graph_betweenness(nodes=["A", "B"], edges=[("A", "B")])
    assert report.max_normalized_betweenness == pytest.approx(0.0)
    assert report.mean_betweenness == pytest.approx(0.0)
    assert report.verdict == "pairwise_only"


def test_pairwise_only_triangle() -> None:
    # Triangle K3: every pair is directly connected — no node on any shortest path.
    report = measure_graph_betweenness(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert report.max_normalized_betweenness == pytest.approx(0.0)
    assert report.verdict == "pairwise_only"


# ---------------------------------------------------------------------------
# Gateway-dominated — star (center is on every path).
# ---------------------------------------------------------------------------


def test_gateway_dominated_star_k14() -> None:
    # Star: center A connected to B,C,D,E.
    # Pairs: (B,C),(B,D),(B,E),(C,D),(C,E),(D,E) = 6 pairs, all via A.
    # raw betweenness(A) = 6. normalizer = (5-1)(5-2)/2 = 6. normalized = 1.0.
    report = measure_graph_betweenness(
        nodes=["A", "B", "C", "D", "E"],
        edges=[("A", "B"), ("A", "C"), ("A", "D"), ("A", "E")],
    )
    assert report.max_normalized_betweenness == pytest.approx(1.0)
    assert report.gateway_node == "A"
    assert report.mean_betweenness == pytest.approx(1.0 / 5)
    assert report.gateway_concentration == pytest.approx(1.0 / (1.0 / 5))
    assert report.verdict == "gateway_dominated"


# ---------------------------------------------------------------------------
# Multi-gateway — path (inner nodes moderate betweenness).
# ---------------------------------------------------------------------------


def test_multi_gateway_path_p5() -> None:
    # Path A-B-C-D-E. n=5, normalizer = 4*3/2 = 6.
    # Pairs through B: (A,C),(A,D),(A,E) = 3. raw(B) = 3.
    # Pairs through C: (A,D),(A,E),(B,D),(B,E) = 4. raw(C) = 4.
    # Pairs through D: (B,E),(A,E),(C,E) ... recount:
    #   (A,E) via A-B-C-D-E: yes through D. (B,E): B-C-D-E yes. (C,E): C-D-E yes. = 3.
    # So raw: A=0, B=3, C=4, D=3, E=0.
    # normalized: B=3/6=0.5, C=4/6=0.667, D=3/6=0.5.
    report = measure_graph_betweenness(
        nodes=["A", "B", "C", "D", "E"],
        edges=[("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")],
    )
    assert report.max_normalized_betweenness == pytest.approx(4.0 / 6.0)
    assert report.gateway_node == "C"
    assert report.verdict == "gateway_dominated"  # 0.667 >= 0.40

    by_id = {nb.node_id: nb.normalized_betweenness for nb in report.per_node}
    assert by_id["A"] == pytest.approx(0.0)
    assert by_id["B"] == pytest.approx(3.0 / 6.0)
    assert by_id["C"] == pytest.approx(4.0 / 6.0)
    assert by_id["D"] == pytest.approx(3.0 / 6.0)
    assert by_id["E"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Square cycle — diffuse flow (each node has same low betweenness).
# ---------------------------------------------------------------------------


def test_diffuse_flow_square_cycle() -> None:
    # Square A-B-C-D-A. n=4, normalizer = 3*2/2 = 3.
    # Opposite pairs: (A,C) and (B,D). Each has TWO shortest paths of length 2.
    # A is on (B,D) path A-B...no. Let's enumerate:
    # (A,C): paths A-B-C and A-D-C (both length 2). A is an endpoint, not between.
    # (B,D): paths B-A-D and B-C-D (both length 2). B is an endpoint, not between.
    # No node is BETWEEN any pair (all shortest paths are length 1 or 2 with no
    # intermediary that all paths share). Actually: for pair (A,C), the intermediaries
    # are B (on A-B-C) and D (on A-D-C). Each is on 1 of 2 shortest paths.
    # Betweenness contribution: B gets 1/2 from (A,C), D gets 1/2 from (A,C).
    # Similarly A gets 1/2 from (B,D), C gets 1/2 from (B,D).
    # raw: A=0.5, B=0.5, C=0.5, D=0.5. normalized: 0.5/3 = 0.1667.
    report = measure_graph_betweenness(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")],
    )
    assert report.max_normalized_betweenness == pytest.approx(0.5 / 3.0)
    assert report.verdict == "multi_gateway"  # 0.167 >= 0.10


# ---------------------------------------------------------------------------
# Two clusters with a bridge — bridge node has high betweenness.
# ---------------------------------------------------------------------------


def test_two_clusters_bridge_node() -> None:
    # Two triangles connected by bridge B1-B2:
    #   A1-B1-C1 (triangle), B1-B2 (bridge), B2-A2-C2 (triangle)
    # B1 and B2 are gateway nodes (all cross-cluster paths go through them).
    nodes = ["A1", "B1", "C1", "B2", "A2", "C2"]
    edges = [
        ("A1", "B1"), ("B1", "C1"), ("C1", "A1"),  # left triangle
        ("B1", "B2"),  # bridge
        ("B2", "A2"), ("A2", "C2"), ("C2", "B2"),  # right triangle
    ]
    report = measure_graph_betweenness(nodes=nodes, edges=edges)
    assert report.gateway_node in ("B1", "B2")
    assert report.max_normalized_betweenness is not None
    assert report.max_normalized_betweenness > 0.40
    assert report.verdict == "gateway_dominated"


# ---------------------------------------------------------------------------
# Disconnected — cross-component pairs contribute zero.
# ---------------------------------------------------------------------------


def test_disconnected_two_triangles() -> None:
    # Two disjoint triangles. Within each, betweenness is 0 (directly connected).
    # Across: no path, so zero contribution.
    report = measure_graph_betweenness(
        nodes=["A", "B", "C", "D", "E", "F"],
        edges=[("A", "B"), ("B", "C"), ("C", "A"), ("D", "E"), ("E", "F"), ("F", "D")],
    )
    assert report.component_count == 2
    assert report.max_normalized_betweenness == pytest.approx(0.0)
    assert report.verdict == "pairwise_only"


# ---------------------------------------------------------------------------
# Edge cases.
# ---------------------------------------------------------------------------


def test_self_loop_dropped() -> None:
    report = measure_graph_betweenness(
        nodes=["A", "B", "C"],
        edges=[("A", "A"), ("A", "B"), ("B", "C")],
    )
    # Path A-B-C: B is on path (A,C). raw(B) = 1, normalizer = 2*1/2 = 1. normalized = 1.0.
    assert report.gateway_node == "B"


def test_duplicate_edges_merged() -> None:
    report = measure_graph_betweenness(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("A", "B"), ("B", "C"), ("B", "C")],
    )
    by_id = {nb.node_id: nb.normalized_betweenness for nb in report.per_node}
    assert by_id["B"] == pytest.approx(1.0)


def test_edge_endpoints_included() -> None:
    report = measure_graph_betweenness(nodes=["A"], edges=[("A", "Z")])
    assert report.total_node_count == 2


# ---------------------------------------------------------------------------
# Threshold validation + custom.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"gateway_threshold": -0.1}, "gateway_threshold"),
        ({"gateway_threshold": 1.1}, "gateway_threshold"),
        ({"moderate_threshold": -0.1}, "moderate_threshold"),
        ({"moderate_threshold": 1.1}, "moderate_threshold"),
        ({"moderate_threshold": 0.5, "gateway_threshold": 0.3}, "must be <="),
    ],
)
def test_threshold_validation_raises(kwargs: dict[str, float], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        measure_graph_betweenness(["A", "B"], [("A", "B")], **kwargs)


def test_custom_thresholds_reclassify() -> None:
    # Square cycle: peak 0.167. multi_gateway at default (>= 0.10).
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    default = measure_graph_betweenness(["A", "B", "C", "D"], edges)
    assert default.verdict == "multi_gateway"
    # Raise moderate to 0.20 -> diffuse_flow (0.167 < 0.20).
    raised = measure_graph_betweenness(["A", "B", "C", "D"], edges, moderate_threshold=0.20)
    assert raised.verdict == "diffuse_flow"


# ---------------------------------------------------------------------------
# Determinism + immutability + report type.
# ---------------------------------------------------------------------------


def test_report_is_deterministic() -> None:
    nodes = ["A", "B", "C", "D", "E"]
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
    a = measure_graph_betweenness(nodes=nodes, edges=edges)
    b = measure_graph_betweenness(nodes=nodes, edges=edges)
    assert a == b


def test_report_is_frozen() -> None:
    report = measure_graph_betweenness(["A", "B"], [("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "robust"  # type: ignore[misc]


def test_report_type() -> None:
    report = measure_graph_betweenness(["A", "B"], [("A", "B")])
    assert isinstance(report, GraphBetweennessReport)
    assert report.authority == "advisory"


def test_per_node_sorted_desc() -> None:
    nodes = ["A", "B", "C", "D", "E"]
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
    report = measure_graph_betweenness(nodes=nodes, edges=edges)
    betweenness_values = [nb.normalized_betweenness for nb in report.per_node]
    assert betweenness_values == sorted(betweenness_values, reverse=True)

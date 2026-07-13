"""Tests for the graph-closeness-centrality axis (geodesic reach efficiency).

Exercises: Wasserman-Faust closeness values (hand-computed), focal/diffuse verdict,
tie-break ordering, disconnected-graph WF penalty, auditable reachable_count/
total_distance, base cases (unknown/singleton/edgeless), self-loop/duplicate handling,
custom threshold reclassification, validation, purity/immutability. Fixtures use small
labeled graphs so BFS distances are exact.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.graph_closeness_centrality import (
    GraphClosenessReport,
    NodeCloseness,
    measure_graph_closeness_centrality,
)


def _by_id(report: GraphClosenessReport) -> dict[str, NodeCloseness]:
    return {nc.node_id: nc for nc in report.per_node}


# --- core: focal graphs (a strong reach center exists) ---------------------


def test_path_p4_focal() -> None:
    # A-B-C-D, n=4, denom=3. closeness = k^2 / ((n-1)*S)
    # A: k=3,S=6 -> 9/18=0.5 ; B: k=3,S=4 -> 9/12=0.75 ; C same as B ; D same as A
    edges = [("A", "B"), ("B", "C"), ("C", "D")]
    report = measure_graph_closeness_centrality(["A", "B", "C", "D"], edges)
    bi = _by_id(report)
    assert bi["A"].closeness == pytest.approx(0.5)
    assert bi["B"].closeness == pytest.approx(0.75)
    assert bi["C"].closeness == pytest.approx(0.75)
    assert bi["D"].closeness == pytest.approx(0.5)
    assert report.max_closeness == pytest.approx(0.75)
    assert report.mean_closeness == pytest.approx(0.625)
    assert report.closest_node == "B"  # tie B,C -> B < C alphabetically
    assert report.verdict == "focal"  # 0.75 >= 0.50
    # auditable raw distance sums
    assert bi["A"].reachable_count == 3
    assert bi["A"].total_distance == 6
    assert bi["B"].total_distance == 4


def test_star_center_is_closest() -> None:
    # K1,3 center C, leaves L1 L2 L3, n=4
    # C: k=3,S=3 -> 1.0 ; each leaf: k=3,S=5 -> 9/15=0.6
    edges = [("C", "L1"), ("C", "L2"), ("C", "L3")]
    report = measure_graph_closeness_centrality(["C", "L1", "L2", "L3"], edges)
    bi = _by_id(report)
    assert bi["C"].closeness == pytest.approx(1.0)
    assert bi["L1"].closeness == pytest.approx(0.6)
    assert report.max_closeness == pytest.approx(1.0)
    assert report.closest_node == "C"
    assert report.verdict == "focal"


def test_complete_graph_uniform() -> None:
    # K4: every node k=3,S=3 -> 1.0
    edges = [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")]
    report = measure_graph_closeness_centrality(["A", "B", "C", "D"], edges)
    assert report.max_closeness == pytest.approx(1.0)
    assert report.mean_closeness == pytest.approx(1.0)
    assert all(nc.closeness == pytest.approx(1.0) for nc in report.per_node)
    assert report.closest_node == "A"  # all equal -> first alphabetically
    assert report.verdict == "focal"


def test_path_p5_center() -> None:
    # A-B-C-D-E, n=5, denom=4. C: k=4,S=6 -> 16/24=0.6667
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
    report = measure_graph_closeness_centrality(["A", "B", "C", "D", "E"], edges)
    bi = _by_id(report)
    assert bi["C"].closeness == pytest.approx(16 / 24)
    assert report.closest_node == "C"
    assert report.verdict == "focal"


# --- core: diffuse graphs (no strong reach center) -------------------------


def test_long_path_diffuse() -> None:
    # P8 A-B-C-D-E-F-G-H, n=8, denom=7. Center D: k=7,S=16 -> 49/112=0.4375 < 0.5
    edges = [
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
        ("E", "F"), ("F", "G"), ("G", "H"),
    ]
    report = measure_graph_closeness_centrality(
        ["A", "B", "C", "D", "E", "F", "G", "H"], edges
    )
    assert report.max_closeness == pytest.approx(49 / 112)
    assert report.closest_node == "D"  # D,E tie at 0.4375 -> D < E
    assert report.verdict == "diffuse"


# --- honesty: disconnected (Wasserman-Faust penalty) -----------------------


def test_disconnected_two_edges_penalized() -> None:
    # A-B and C-D, n=4. Each node: k=1,S=1 -> 1/(3*1)=1/3
    edges = [("A", "B"), ("C", "D")]
    report = measure_graph_closeness_centrality(["A", "B", "C", "D"], edges)
    assert report.component_count == 2
    assert all(nc.closeness == pytest.approx(1 / 3) for nc in report.per_node)
    assert all(nc.reachable_count == 1 for nc in report.per_node)
    assert all(nc.total_distance == 1 for nc in report.per_node)
    assert report.max_closeness is not None
    assert report.max_closeness < 0.5  # 1/3 < 0.5 -> diffuse
    assert report.verdict == "diffuse"


def test_isolated_node_within_larger_graph() -> None:
    # triangle A-B-C plus isolated X, n=4. X reaches nothing -> closeness 0.0
    edges = [("A", "B"), ("B", "C"), ("C", "A")]
    report = measure_graph_closeness_centrality(["A", "B", "C", "X"], edges)
    bi = _by_id(report)
    assert bi["X"].closeness == pytest.approx(0.0)
    assert bi["X"].reachable_count == 0
    assert bi["X"].total_distance == 0
    assert report.component_count == 2


# --- honesty: base cases ---------------------------------------------------


def test_unknown_empty_graph() -> None:
    report = measure_graph_closeness_centrality([], [])
    assert report.total_node_count == 0
    assert report.max_closeness is None
    assert report.mean_closeness is None
    assert report.closest_node is None
    assert report.per_node == ()
    assert report.verdict == "unknown"


def test_singleton_one_node() -> None:
    report = measure_graph_closeness_centrality(["A"], [])
    assert report.max_closeness is None  # undefined, not fabricated
    assert report.verdict == "singleton"
    assert report.per_node[0].node_id == "A"


def test_edgeless_multiple_nodes() -> None:
    report = measure_graph_closeness_centrality(["A", "B", "C"], [])
    assert report.max_closeness == pytest.approx(0.0)  # honest 0, not None
    assert report.mean_closeness == pytest.approx(0.0)
    assert all(nc.closeness == pytest.approx(0.0) for nc in report.per_node)
    assert report.component_count == 3
    assert report.verdict == "edgeless"


# --- edge handling ---------------------------------------------------------


def test_self_loop_dropped() -> None:
    # triangle A-B-C plus self-loop A-A (dropped) -> closeness as triangle, n=3
    edges = [("A", "B"), ("B", "C"), ("C", "A"), ("A", "A")]
    report = measure_graph_closeness_centrality(["A", "B", "C"], edges)
    assert report.max_closeness == pytest.approx(1.0)  # triangle = complete on 3


def test_duplicate_edges_merged() -> None:
    edges = [("A", "B"), ("A", "B"), ("B", "C"), ("C", "A")]
    report = measure_graph_closeness_centrality(["A", "B", "C"], edges)
    assert report.max_closeness == pytest.approx(1.0)  # still a triangle


def test_edge_endpoints_added_to_node_set() -> None:
    # node list omits D, but edge C-D introduces it
    report = measure_graph_closeness_centrality(["A", "B", "C"], [("A", "B"), ("C", "D")])
    assert report.total_node_count == 4
    assert {"A", "B", "C", "D"} == {nc.node_id for nc in report.per_node}


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_reclassifies() -> None:
    # P4 peak 0.75: >= 0.50 -> focal; with 0.80 -> diffuse
    edges = [("A", "B"), ("B", "C"), ("C", "D")]
    focal = measure_graph_closeness_centrality(["A", "B", "C", "D"], edges)
    assert focal.verdict == "focal"
    diffuse = measure_graph_closeness_centrality(
        ["A", "B", "C", "D"], edges, focal_threshold=0.80
    )
    assert diffuse.verdict == "diffuse"


def test_threshold_boundary_inclusive() -> None:
    # star center closeness exactly 1.0; threshold 1.0 -> still focal (>=)
    edges = [("C", "L1"), ("C", "L2"), ("C", "L3")]
    report = measure_graph_closeness_centrality(
        ["C", "L1", "L2", "L3"], edges, focal_threshold=1.0
    )
    assert report.verdict == "focal"


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_threshold_out_of_range_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        measure_graph_closeness_centrality(["A", "B"], [("A", "B")], focal_threshold=bad)


# --- purity / immutability / determinism -----------------------------------


def test_per_node_sorted_desc_then_id() -> None:
    edges = [("A", "B"), ("B", "C"), ("C", "D")]
    report = measure_graph_closeness_centrality(["A", "B", "C", "D"], edges)
    closenesses = [nc.closeness for nc in report.per_node]
    assert closenesses == sorted(closenesses, reverse=True)
    # tie B,C -> B before C
    ids = [nc.node_id for nc in report.per_node]
    assert ids.index("B") < ids.index("C")


def test_report_is_frozen() -> None:
    report = measure_graph_closeness_centrality(["A", "B"], [("A", "B")])
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.max_closeness = 99.0  # type: ignore[misc]


def test_deterministic_repeated_calls() -> None:
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
    first = measure_graph_closeness_centrality(["A", "B", "C", "D", "E"], edges)
    second = measure_graph_closeness_centrality(["A", "B", "C", "D", "E"], edges)
    assert first == second


def test_authority_is_advisory() -> None:
    report = measure_graph_closeness_centrality(["A", "B"], [("A", "B")])
    assert report.authority == "advisory"

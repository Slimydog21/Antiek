"""Tests for the graph global-efficiency axis (ask #1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_global_efficiency import (
    GraphGlobalEfficiencyReport,
    measure_graph_global_efficiency,
)


def test_no_edges_is_unknown() -> None:
    report = measure_graph_global_efficiency([])
    assert report.verdict == "unknown"
    assert report.edge_count == 0
    assert report.node_count == 0
    assert report.global_efficiency is None
    assert report.mean_shortest_path is None
    assert report.connected_fraction is None
    assert report.authority == "advisory"


def test_complete_triangle_is_maximal() -> None:
    # K3: every pair distance 1 -> E = 1.0
    report = measure_graph_global_efficiency([("a", "b"), ("b", "c"), ("a", "c")])
    assert report.verdict == "high_efficiency"
    assert report.global_efficiency == pytest.approx(1.0)
    assert report.reachable_pair_count == 3
    assert report.total_pair_count == 3
    assert report.connected_fraction == pytest.approx(1.0)
    assert report.mean_shortest_path == pytest.approx(1.0)


def test_single_edge_is_complete_k2() -> None:
    report = measure_graph_global_efficiency([("a", "b")])
    assert report.verdict == "high_efficiency"
    assert report.global_efficiency == pytest.approx(1.0)
    assert report.node_count == 2
    assert report.reachable_pair_count == 1


def test_three_disjoint_edges_low_efficiency() -> None:
    # 6 nodes, 3 components: only 3 of 15 pairs reachable -> E = 6/30 = 0.20
    report = measure_graph_global_efficiency(
        [("a", "b"), ("c", "d"), ("e", "f")]
    )
    assert report.verdict == "low_efficiency"
    assert report.global_efficiency == pytest.approx(0.20)
    assert report.reachable_pair_count == 3
    assert report.total_pair_count == 15
    assert report.connected_fraction == pytest.approx(0.20)
    assert report.mean_shortest_path == pytest.approx(1.0)


def test_two_disjoint_edges_moderate() -> None:
    # 4 nodes, 2 components: 2 of 6 pairs reachable -> E = 4/12 ~= 0.3333
    report = measure_graph_global_efficiency([("a", "b"), ("c", "d")])
    assert report.verdict == "moderate_efficiency"
    assert report.global_efficiency == pytest.approx(1 / 3)
    assert report.connected_fraction == pytest.approx(1 / 3)


def test_path_of_five_hand_computed() -> None:
    # P5 a-b-c-d-e: connected; distances over unordered pairs:
    # [1,2,3,4, 1,2,3, 1,2, 1] -> mean 2.0; E = 2*sum(1/d)/20
    distances = [1, 2, 3, 4, 1, 2, 3, 1, 2, 1]
    expected_e = 2 * sum(1 / d for d in distances) / 20
    report = measure_graph_global_efficiency(
        [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]
    )
    assert report.verdict == "high_efficiency"
    assert report.global_efficiency == pytest.approx(expected_e)
    assert report.connected_fraction == pytest.approx(1.0)
    assert report.mean_shortest_path == pytest.approx(2.0)


def test_star_k13_hand_computed() -> None:
    # center c + 3 leaves: 3 pairs d=1, 3 pairs d=2 -> E = 2*4.5/12 = 0.75
    report = measure_graph_global_efficiency([("c", "a"), ("c", "b"), ("c", "d")])
    assert report.global_efficiency == pytest.approx(0.75)
    assert report.verdict == "high_efficiency"
    assert report.mean_shortest_path == pytest.approx(1.5)
    assert report.reachable_pair_count == 6


def test_self_loops_excluded_and_counted() -> None:
    # (a,a) excluded; (a,b) -> K2 -> E = 1.0
    report = measure_graph_global_efficiency([("a", "a"), ("a", "b")])
    assert report.self_loop_count == 1
    assert report.edge_count == 1
    assert report.global_efficiency == pytest.approx(1.0)


def test_parallel_edges_deduped() -> None:
    report = measure_graph_global_efficiency([("a", "b"), ("b", "a")])
    assert report.edge_count == 1
    assert report.global_efficiency == pytest.approx(1.0)


def test_custom_thresholds_reclassify() -> None:
    # 2 disjoint edges E ~= 0.333: moderate at 0.30/0.60, low at 0.40, high at 0.30
    edges = [("a", "b"), ("c", "d")]
    assert measure_graph_global_efficiency(edges).verdict == "moderate_efficiency"
    assert (
        measure_graph_global_efficiency(edges, low_threshold=0.40, high_threshold=0.90).verdict
        == "low_efficiency"
    )


def test_threshold_validation_rejects_out_of_range() -> None:
    edges = [("a", "b"), ("c", "d")]
    with pytest.raises(ValueError, match="high_threshold"):
        measure_graph_global_efficiency(edges, high_threshold=0.0)
    with pytest.raises(ValueError, match="high_threshold"):
        measure_graph_global_efficiency(edges, high_threshold=1.5)
    with pytest.raises(ValueError, match="low_threshold"):
        measure_graph_global_efficiency(edges, low_threshold=1.0)
    with pytest.raises(ValueError, match="low_threshold"):
        measure_graph_global_efficiency(edges, low_threshold=-0.1)
    with pytest.raises(ValueError, match="low_threshold"):
        # low >= high is invalid
        measure_graph_global_efficiency(edges, low_threshold=0.50, high_threshold=0.40)


def test_report_is_frozen_and_deterministic() -> None:
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]
    first = measure_graph_global_efficiency(edges)
    second = measure_graph_global_efficiency(edges)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: GraphGlobalEfficiencyReport = measure_graph_global_efficiency(
        [("a", "b"), ("b", "c"), ("a", "c")]
    )
    assert isinstance(report, GraphGlobalEfficiencyReport)
    assert isinstance(report.notes, tuple)
    assert report.high_threshold == 0.60
    assert report.low_threshold == 0.30
    assert report.authority == "advisory"

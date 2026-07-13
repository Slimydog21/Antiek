"""Tests for the graph assortativity axis (ask #1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_assortativity import (
    GraphAssortativityReport,
    measure_graph_assortativity,
)


def test_no_edges_is_unknown() -> None:
    report = measure_graph_assortativity([])
    assert report.verdict == "unknown"
    assert report.edge_count == 0
    assert report.node_count == 0
    assert report.assortativity is None
    assert report.min_degree is None
    assert report.max_degree is None
    assert report.mean_degree is None
    assert report.degree_pairs_observed == 0
    assert report.authority == "advisory"


def test_star_is_maximally_disassortative() -> None:
    # center c (deg 3) + 3 leaves (deg 1) -> r = -1.0 (provably for any star k>=2)
    report = measure_graph_assortativity([("c", "a"), ("c", "b"), ("c", "d")])
    assert report.verdict == "disassortative"
    assert report.assortativity == pytest.approx(-1.0)
    assert report.node_count == 4
    assert report.edge_count == 3
    assert report.degree_pairs_observed == 6
    assert report.min_degree == 1
    assert report.max_degree == 3
    assert report.mean_degree == pytest.approx(1.5)


def test_disjoint_cliques_different_size_is_maximally_assortative() -> None:
    # triangle (deg 2) disjoint from an edge (deg 1): every edge joins equal-degree nodes
    # with TWO degree classes present -> r = +1.0
    report = measure_graph_assortativity(
        [("a", "b"), ("b", "c"), ("a", "c"), ("d", "e")]
    )
    assert report.verdict == "assortative"
    assert report.assortativity == pytest.approx(1.0)
    assert report.node_count == 5
    assert report.edge_count == 4
    assert report.min_degree == 1
    assert report.max_degree == 2
    assert report.mean_degree == pytest.approx(1.6)


def test_regular_triangle_is_unmeasurable() -> None:
    # all nodes degree 2 -> variance 0 -> no mixing pattern to measure
    report = measure_graph_assortativity([("a", "b"), ("b", "c"), ("a", "c")])
    assert report.verdict == "unmeasurable"
    assert report.assortativity is None
    assert report.edge_count == 3
    assert report.min_degree == 2
    assert report.max_degree == 2


def test_single_edge_is_unmeasurable() -> None:
    report = measure_graph_assortativity([("a", "b")])
    assert report.verdict == "unmeasurable"
    assert report.assortativity is None
    assert report.node_count == 2
    assert report.edge_count == 1


def test_self_loops_excluded_and_counted() -> None:
    # (a,a) is a self-loop (not inter-node mixing) -> excluded; (a,b) kept -> single edge
    report = measure_graph_assortativity([("a", "a"), ("a", "b")])
    assert report.self_loop_count == 1
    assert report.edge_count == 1
    assert report.verdict == "unmeasurable"


def test_parallel_edges_deduped_to_simple_graph() -> None:
    # (a,b) and (b,a) are one undirected edge
    report = measure_graph_assortativity([("a", "b"), ("b", "a")])
    assert report.edge_count == 1
    assert report.verdict == "unmeasurable"


def test_path_of_three_is_two_star_disassortative() -> None:
    # a-b-c is a 2-star -> r = -1.0
    report = measure_graph_assortativity([("a", "b"), ("b", "c")])
    assert report.verdict == "disassortative"
    assert report.assortativity == pytest.approx(-1.0)


def test_paw_graph_exact_interior_r_and_neutral_threshold_path() -> None:
    # triangle a,b,c + pendant c-d: degrees a=2,b=2,c=3,d=1 -> r = -5/7 ~= -0.7143
    paw = [("a", "b"), ("a", "c"), ("b", "c"), ("c", "d")]
    default_report = measure_graph_assortativity(paw)
    assert default_report.assortativity == pytest.approx(-5 / 7)
    assert default_report.verdict == "disassortative"  # -0.7143 <= -0.30
    # push the disassortative threshold below the measured r -> neutral path
    neutral_report = measure_graph_assortativity(paw, disassortative_threshold=-0.80)
    assert neutral_report.assortativity == pytest.approx(-5 / 7)
    assert neutral_report.verdict == "neutral_mixing"  # -0.7143 > -0.80


def test_threshold_validation_rejects_out_of_range() -> None:
    edge = [("a", "b"), ("b", "c")]
    with pytest.raises(ValueError, match="assortative_threshold"):
        measure_graph_assortativity(edge, assortative_threshold=0.0)
    with pytest.raises(ValueError, match="assortative_threshold"):
        measure_graph_assortativity(edge, assortative_threshold=1.5)
    with pytest.raises(ValueError, match="disassortative_threshold"):
        measure_graph_assortativity(edge, disassortative_threshold=0.0)
    with pytest.raises(ValueError, match="disassortative_threshold"):
        measure_graph_assortativity(edge, disassortative_threshold=-1.5)


def test_near_zero_real_r_carried_not_deferred() -> None:
    # neutral_mixing carries a REAL measured r, never None
    report = measure_graph_assortativity(
        [("a", "b"), ("a", "c"), ("b", "c"), ("c", "d")], disassortative_threshold=-0.80
    )
    assert report.assortativity is not None
    assert report.verdict == "neutral_mixing"


def test_report_is_frozen_and_deterministic() -> None:
    edges = [("c", "a"), ("c", "b"), ("c", "d")]
    first = measure_graph_assortativity(edges)
    second = measure_graph_assortativity(edges)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: GraphAssortativityReport = measure_graph_assortativity(
        [("a", "b"), ("b", "c"), ("a", "c"), ("d", "e")]
    )
    assert isinstance(report, GraphAssortativityReport)
    assert isinstance(report.notes, tuple)
    assert report.assortative_threshold == 0.30
    assert report.disassortative_threshold == -0.30
    assert report.authority == "advisory"

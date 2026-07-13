"""Tests for the graph-transitivity (local cliquishness) axis (ask #1).

Every fixture is hand-counted: triangles, triples, transitivity, and mean local
clustering are verified by inspection before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_transitivity import (
    GraphEdge,
    GraphTransitivityReport,
    measure_graph_transitivity,
)


def edge(a: str, b: str) -> GraphEdge:
    return GraphEdge(source=a, target=b)


# ---------------------------------------------------------------------------
# Base cases — distinct honest defer states, never collapsed.
# ---------------------------------------------------------------------------


def test_empty_graph_is_unknown() -> None:
    report = measure_graph_transitivity(nodes=[], edges=[])
    assert report.verdict == "unknown"
    assert report.transitivity is None
    assert report.triangle_count is None
    assert report.connected_triples is None
    assert report.mean_local_clustering is None
    assert report.authority == "advisory"


def test_singleton_is_its_own_base_case() -> None:
    report = measure_graph_transitivity(nodes=["n1"], edges=[])
    assert report.verdict == "singleton"
    assert report.transitivity is None
    assert report.orphan_node_count == 1


def test_edgeless_two_nodes() -> None:
    report = measure_graph_transitivity(nodes=["n1", "n2"], edges=[])
    assert report.verdict == "edgeless"
    assert report.transitivity is None
    assert report.orphan_node_count == 2


def test_pairwise_disjoint_edges_no_triples() -> None:
    # a-b and c-d are disjoint; x is isolated. No node has >= 2 neighbors.
    report = measure_graph_transitivity(
        nodes=["a", "b", "c", "d", "x"],
        edges=[edge("a", "b"), edge("c", "d")],
    )
    assert report.verdict == "pairwise"
    assert report.transitivity is None  # undefined — no 2-path to close
    assert report.connected_triples == 0
    assert report.triangle_count == 0
    assert report.orphan_node_count == 1  # x


def test_pairwise_distinct_from_open_weave_and_edgeless() -> None:
    assert measure_graph_transitivity(nodes=["a", "b"], edges=[]).verdict == "edgeless"
    assert (
        measure_graph_transitivity(
            nodes=["a", "b", "c", "d"], edges=[edge("a", "b"), edge("c", "d")]
        ).verdict
        == "pairwise"
    )
    # a-b-c path has one triple (centered at b) that does not close -> open_weave
    assert (
        measure_graph_transitivity(
            nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c")]
        ).verdict
        == "open_weave"
    )


# ---------------------------------------------------------------------------
# Measurable graphs — transitivity, triangles, verdict bands.
# ---------------------------------------------------------------------------


def test_triangle_clique_transitivity_one() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"],
        edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")],
    )
    assert report.triangle_count == 1
    assert report.connected_triples == 3
    assert report.transitivity == pytest.approx(1.0)
    assert report.mean_local_clustering == pytest.approx(1.0)
    assert report.verdict == "tightly_woven"


def test_star_is_open_weave_transitivity_zero() -> None:
    # center c, leaves a b d. 3 triples at c, none close.
    report = measure_graph_transitivity(
        nodes=["c", "a", "b", "d"],
        edges=[edge("c", "a"), edge("c", "b"), edge("c", "d")],
    )
    assert report.transitivity == pytest.approx(0.0)
    assert report.triangle_count == 0
    assert report.connected_triples == 3
    assert report.verdict == "open_weave"
    assert report.mean_local_clustering == pytest.approx(0.0)


def test_path_three_nodes_open_weave() -> None:
    # a - b - c: one triple at b (neighbors a, c), a-c is not an edge.
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c")]
    )
    assert report.transitivity == pytest.approx(0.0)
    assert report.connected_triples == 1
    assert report.triangle_count == 0
    assert report.verdict == "open_weave"


def test_square_four_cycle_open_weave() -> None:
    # a-b-c-d-a: 4 triples, zero triangles.
    report = measure_graph_transitivity(
        nodes=["a", "b", "c", "d"],
        edges=[
            edge("a", "b"),
            edge("b", "c"),
            edge("c", "d"),
            edge("d", "a"),
        ],
    )
    assert report.transitivity == pytest.approx(0.0)
    assert report.connected_triples == 4
    assert report.verdict == "open_weave"


def test_butterfly_transitivity_diverges_from_mean_local() -> None:
    # Two triangles sharing center c: triangles (a,b,c) and (c,d,e).
    report = measure_graph_transitivity(
        nodes=["a", "b", "c", "d", "e"],
        edges=[
            edge("c", "a"),
            edge("c", "b"),
            edge("a", "b"),
            edge("c", "d"),
            edge("c", "e"),
            edge("d", "e"),
        ],
    )
    assert report.triangle_count == 2
    assert report.connected_triples == 10
    assert report.transitivity == pytest.approx(0.6)  # 6 closed / 10 triples
    # mean local weights every node equally -> higher than triple-weighted
    assert report.mean_local_clustering == pytest.approx((1 + 1 + 2 / 6 + 1 + 1) / 5)
    assert report.mean_local_clustering is not None
    assert report.transitivity is not None
    assert report.mean_local_clustering > report.transitivity
    assert report.verdict == "tightly_woven"


def test_diamond_two_triangles_sharing_edge() -> None:
    # K4 minus edge c-d: triangles a-b-c and a-b-d.
    report = measure_graph_transitivity(
        nodes=["a", "b", "c", "d"],
        edges=[
            edge("a", "b"),
            edge("a", "c"),
            edge("a", "d"),
            edge("b", "c"),
            edge("b", "d"),
        ],
    )
    assert report.triangle_count == 2
    assert report.connected_triples == 8
    assert report.transitivity == pytest.approx(0.75)  # 6 closed / 8 triples
    assert report.verdict == "tightly_woven"


def test_loosely_woven_partial_closure() -> None:
    # Star center c with 6 leaves, plus ONE leaf-edge a-b. The leaf-edge closes
    # exactly one triangle {c,a,b} but leaves 15 open triples at c -> transitivity
    # 3 closed / 17 triples ~ 0.176 (in the loosely_woven band, not tightly_woven).
    report = measure_graph_transitivity(
        nodes=["c", "a", "b", "d", "e", "f", "g"],
        edges=[
            edge("c", "a"),
            edge("c", "b"),
            edge("c", "d"),
            edge("c", "e"),
            edge("c", "f"),
            edge("c", "g"),
            edge("a", "b"),
        ],
    )
    assert report.triangle_count == 1
    assert report.connected_triples == 17
    assert report.transitivity == pytest.approx(3 / 17)
    assert report.transitivity is not None
    assert report.transitivity is not None
    assert 0.0 < report.transitivity < 0.20  # loosely_woven band
    assert report.verdict == "loosely_woven"


def test_transitivity_bounded_zero_to_one() -> None:
    star = measure_graph_transitivity(
        nodes=["c", "a", "b", "d"], edges=[edge("c", "a"), edge("c", "b"), edge("c", "d")]
    )
    clique = measure_graph_transitivity(
        nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")]
    )
    assert star.transitivity is not None and clique.transitivity is not None
    assert 0.0 <= star.transitivity <= 1.0
    assert 0.0 <= clique.transitivity <= 1.0


# ---------------------------------------------------------------------------
# Edge integrity — self-loops, duplicates, dangling, orphans.
# ---------------------------------------------------------------------------


def test_self_loops_ignored() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"],
        edges=[edge("a", "a"), edge("a", "b"), edge("b", "b"), edge("b", "c"), edge("a", "c")],
    )
    assert report.edge_count == 3  # a-b, b-c, a-c
    assert report.triangle_count == 1


def test_duplicate_edges_merged() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"],
        edges=[
            edge("a", "b"),
            edge("a", "b"),
            edge("b", "a"),
            edge("b", "c"),
            edge("a", "c"),
        ],
    )
    assert report.edge_count == 3
    assert report.triangle_count == 1


def test_dangling_edges_surfaced_not_coerced() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"],
        edges=[edge("a", "b"), edge("b", "c"), edge("a", "c"), edge("a", "ghost")],
    )
    assert report.edge_count == 3
    assert report.dangling_edge_count == 1
    assert report.triangle_count == 1


def test_orphan_nodes_counted() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c", "x", "y"],
        edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")],
    )
    assert report.orphan_node_count == 2  # x and y isolated
    assert report.triangle_count == 1


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_closure_threshold_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="closure_threshold"):
        measure_graph_transitivity(
            nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")], closure_threshold=0.0
        )
    with pytest.raises(ValueError, match="closure_threshold"):
        measure_graph_transitivity(
            nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")], closure_threshold=1.5
        )


def test_custom_threshold_reclassifies_tightly_to_loosely() -> None:
    # butterfly: transitivity 0.6 -> tightly_woven by default, loosely_woven at 0.8.
    edges = [
        edge("c", "a"),
        edge("c", "b"),
        edge("a", "b"),
        edge("c", "d"),
        edge("c", "e"),
        edge("d", "e"),
    ]
    default = measure_graph_transitivity(nodes=["a", "b", "c", "d", "e"], edges=edges)
    assert default.verdict == "tightly_woven"
    raised = measure_graph_transitivity(
        nodes=["a", "b", "c", "d", "e"], edges=edges, closure_threshold=0.8
    )
    assert raised.verdict == "loosely_woven"


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")]
    )
    with pytest.raises(FrozenInstanceError):
        report.transitivity = 0.5  # type: ignore[misc]


def test_deterministic_output() -> None:
    nodes = ["a", "b", "c", "d", "e"]
    edges = [
        edge("a", "b"),
        edge("b", "c"),
        edge("c", "d"),
        edge("d", "e"),
        edge("e", "a"),
        edge("a", "c"),
    ]
    assert measure_graph_transitivity(nodes=nodes, edges=edges) == measure_graph_transitivity(
        nodes=nodes, edges=edges
    )


def test_report_is_graph_transitivity_report_instance() -> None:
    report = measure_graph_transitivity(
        nodes=["a", "b", "c"], edges=[edge("a", "b"), edge("b", "c"), edge("a", "c")]
    )
    assert isinstance(report, GraphTransitivityReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_graph_transitivity(
        nodes=["c", "a", "b", "d"], edges=[edge("c", "a"), edge("c", "b"), edge("c", "d")]
    )
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("transitivity" in n.lower() for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)

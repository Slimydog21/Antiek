"""Tests for the graph PageRank axis (ask #1 — recursive random-walk influence).

Fixtures use both exact convergence values (for small graphs) and invariant properties
(sum=1.0, ordering) for larger graphs.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_pagerank import (
    GraphPageRankReport,
    measure_graph_pagerank,
)

# ---------------------------------------------------------------------------
# Unknown / base cases.
# ---------------------------------------------------------------------------


def test_unknown_empty_graph() -> None:
    report = measure_graph_pagerank(nodes=[], edges=[])
    assert report.total_node_count == 0
    assert report.max_pagerank is None
    assert report.pagerank_gini is None
    assert report.per_node == ()
    assert report.verdict == "unknown"
    assert report.authority == "advisory"


def test_singleton_one_node() -> None:
    report = measure_graph_pagerank(nodes=["A"], edges=[])
    assert report.max_pagerank == pytest.approx(1.0)
    assert report.pagerank_gini is None
    assert report.verdict == "singleton"
    assert report.influential_node == "A"


def test_uniform_rank_edgeless() -> None:
    report = measure_graph_pagerank(nodes=["A", "B", "C", "D"], edges=[])
    uniform = 1.0 / 4
    assert report.max_pagerank == pytest.approx(uniform)
    assert report.pagerank_gini == pytest.approx(0.0)
    assert report.dangling_node_count == 4
    assert report.verdict == "uniform_rank"


# ---------------------------------------------------------------------------
# Two-node chain — exact convergence value.
# ---------------------------------------------------------------------------


def test_two_node_chain_b_downstream() -> None:
    # A -> B (A links to B, B is dangling). PR(A) = 1/(2+d), PR(B) = 1 - PR(A).
    report = measure_graph_pagerank(nodes=["A", "B"], edges=[("A", "B")])
    by_id = {np.node_id: np.pagerank for np in report.per_node}
    assert by_id["A"] == pytest.approx(1.0 / 2.85, abs=1e-4)
    assert by_id["B"] == pytest.approx(1.0 - 1.0 / 2.85, abs=1e-4)
    assert by_id["B"] > by_id["A"]  # downstream target favored
    assert sum(by_id.values()) == pytest.approx(1.0)
    assert report.influential_node == "B"
    assert report.converged is True


# ---------------------------------------------------------------------------
# Cycle — uniform by symmetry (Gini = 0).
# ---------------------------------------------------------------------------


def test_cycle_uniform() -> None:
    # A -> B -> C -> A: all equal by symmetry.
    report = measure_graph_pagerank(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    by_id = {np.node_id: np.pagerank for np in report.per_node}
    assert by_id["A"] == pytest.approx(1.0 / 3)
    assert by_id["B"] == pytest.approx(1.0 / 3)
    assert by_id["C"] == pytest.approx(1.0 / 3)
    assert report.pagerank_gini == pytest.approx(0.0, abs=1e-6)
    assert report.verdict == "diffuse_rank"  # Gini ~0 < 0.50


# ---------------------------------------------------------------------------
# Star (all link TO center) — center has highest PageRank.
# ---------------------------------------------------------------------------


def test_star_inlinks_center_dominates() -> None:
    # B -> A, C -> A, D -> A. A is the target of all links.
    report = measure_graph_pagerank(
        nodes=["A", "B", "C", "D"],
        edges=[("B", "A"), ("C", "A"), ("D", "A")],
    )
    assert report.influential_node == "A"
    by_id = {np.node_id: np.pagerank for np in report.per_node}
    assert by_id["A"] > by_id["B"]
    assert by_id["A"] > by_id["C"]
    assert by_id["A"] > by_id["D"]
    # B, C, D equal by symmetry.
    assert by_id["B"] == pytest.approx(by_id["C"])
    assert by_id["C"] == pytest.approx(by_id["D"])
    assert sum(by_id.values()) == pytest.approx(1.0)
    assert report.pagerank_gini is not None
    assert report.pagerank_gini > 0.20  # star center dominates


# ---------------------------------------------------------------------------
# Chain — downstream favored.
# ---------------------------------------------------------------------------


def test_chain_downstream_favored() -> None:
    # A -> B -> C -> D. C and D accumulate more recursive influence.
    report = measure_graph_pagerank(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "C"), ("C", "D")],
    )
    by_id = {np.node_id: np.pagerank for np in report.per_node}
    assert by_id["D"] > by_id["A"]  # downstream target
    assert by_id["C"] > by_id["A"]
    assert sum(by_id.values()) == pytest.approx(1.0)
    assert report.converged is True


# ---------------------------------------------------------------------------
# Recursive influence — linked-to-by-influential > linked-to-by-peripheral.
# ---------------------------------------------------------------------------


def test_recursive_influence_beats_degree() -> None:
    # X is cited by A (which is cited by B, C). Y is cited by P, Q (uncited leaves).
    # X should have higher PageRank than Y despite fewer in-links.
    edges = [
        ("B", "A"), ("C", "A"),  # A is influential (cited by B, C)
        ("A", "X"),               # X cited by ONE influential node
        ("P", "Y"), ("Q", "Y"),   # Y cited by TWO uncited leaves
    ]
    nodes = ["A", "B", "C", "X", "Y", "P", "Q"]
    report = measure_graph_pagerank(nodes=nodes, edges=edges)
    by_id = {np.node_id: np.pagerank for np in report.per_node}
    assert by_id["X"] > by_id["Y"]  # quality of citers > quantity
    assert report.converged is True


# ---------------------------------------------------------------------------
# Dangling nodes.
# ---------------------------------------------------------------------------


def test_dangling_nodes_counted() -> None:
    # A -> B, C is isolated (dangling), B is dangling.
    report = measure_graph_pagerank(
        nodes=["A", "B", "C"],
        edges=[("A", "B")],
    )
    assert report.dangling_node_count == 2  # B (zero out-degree) + C (isolated)
    assert any("dangling" in n for n in report.notes)


# ---------------------------------------------------------------------------
# Edge cases: self-loops, duplicates.
# ---------------------------------------------------------------------------


def test_self_loop_dropped() -> None:
    report = measure_graph_pagerank(
        nodes=["A", "B"],
        edges=[("A", "A"), ("A", "B")],
    )
    by_id = {np.node_id: np.pagerank for np in report.per_node}
    # Same as A->B (self-loop dropped): PR(A) = 1/2.85.
    assert by_id["A"] == pytest.approx(1.0 / 2.85, abs=1e-4)


def test_duplicate_edges_merged() -> None:
    report1 = measure_graph_pagerank(nodes=["A", "B"], edges=[("A", "B")])
    report2 = measure_graph_pagerank(nodes=["A", "B"], edges=[("A", "B"), ("A", "B"), ("A", "B")])
    by1 = {np.node_id: np.pagerank for np in report1.per_node}
    by2 = {np.node_id: np.pagerank for np in report2.per_node}
    assert by1["A"] == pytest.approx(by2["A"])


def test_edge_endpoints_included() -> None:
    report = measure_graph_pagerank(nodes=["A"], edges=[("A", "Z")])
    assert report.total_node_count == 2


# ---------------------------------------------------------------------------
# Convergence tracking.
# ---------------------------------------------------------------------------


def test_convergence_iterations_auditable() -> None:
    report = measure_graph_pagerank(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert report.convergence_iterations >= 1
    assert report.convergence_iterations <= 100
    assert report.converged is True


def test_max_iterations_capped() -> None:
    report = measure_graph_pagerank(
        nodes=["A", "B"],
        edges=[("A", "B")],
        max_iterations=1,
    )
    assert report.convergence_iterations == 1


# ---------------------------------------------------------------------------
# Threshold validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"damping": -0.1}, "damping"),
        ({"damping": 1.1}, "damping"),
        ({"tolerance": 0}, "tolerance"),
        ({"tolerance": -1}, "tolerance"),
        ({"max_iterations": 0}, "max_iterations"),
        ({"concentration_threshold": -0.1}, "concentration_threshold"),
        ({"concentration_threshold": 1.1}, "concentration_threshold"),
    ],
)
def test_validation_raises(kwargs: dict[str, float | int], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        measure_graph_pagerank(["A", "B"], [("A", "B")], **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Determinism + immutability + report type.
# ---------------------------------------------------------------------------


def test_report_is_deterministic() -> None:
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    a = measure_graph_pagerank(nodes=nodes, edges=edges)
    b = measure_graph_pagerank(nodes=nodes, edges=edges)
    assert a == b


def test_report_is_frozen() -> None:
    report = measure_graph_pagerank(["A", "B"], [("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "concentrated"  # type: ignore[misc]


def test_report_type() -> None:
    report = measure_graph_pagerank(["A", "B"], [("A", "B")])
    assert isinstance(report, GraphPageRankReport)
    assert report.authority == "advisory"


def test_per_node_sorted_desc() -> None:
    edges = [("B", "A"), ("C", "A"), ("D", "A")]
    report = measure_graph_pagerank(nodes=["A", "B", "C", "D"], edges=edges)
    pageranks = [np.pagerank for np in report.per_node]
    assert pageranks == sorted(pageranks, reverse=True)

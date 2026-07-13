"""Tests for substrate/graph_centrality.py — global influence concentration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.graph_centrality import (
    GraphEdge,
    measure_graph_centrality,
)


def _edges(*pairs: tuple[str, str]) -> list[GraphEdge]:
    return [GraphEdge(source=a, target=b) for a, b in pairs]


# --- unknown ---------------------------------------------------------------


def test_unknown_empty_graph() -> None:
    r = measure_graph_centrality([], [])
    assert r.verdict == "unknown"
    assert r.degree_centralization is None
    assert r.max_degree_centrality is None
    assert r.mean_degree_centrality is None
    assert r.authority == "advisory"


def test_unknown_never_fabricates_distributed() -> None:
    assert measure_graph_centrality([], []).verdict != "distributed"


# --- singleton (honest base case) -----------------------------------------


def test_singleton_one_node() -> None:
    r = measure_graph_centrality(["solo"], [])
    assert r.verdict == "singleton"
    assert r.degree_centralization is None


# --- edgeless (no influence to measure) -----------------------------------


def test_edgeless_never_fabricates_distributed() -> None:
    # >= 2 nodes, zero edges -> centralization undefined (degenerate), NOT "distributed".
    r = measure_graph_centrality(["a", "b", "c"], [])
    assert r.verdict == "edgeless"
    assert r.degree_centralization is None
    assert any("not measurable" in n for n in r.notes)


def test_edgeless_distinct_from_unknown_and_distributed() -> None:
    assert measure_graph_centrality([], []).verdict == "unknown"
    assert measure_graph_centrality(["a", "b"], []).verdict == "edgeless"


# --- hub_dominated (star — maximal concentration) -------------------------


def test_hub_dominated_star_graph() -> None:
    # Star: hub connects to 4 leaves. centralization = 1.0 (perfect star).
    nodes = ["hub", "x", "y", "z", "w"]
    edges = [("hub", n) for n in ["x", "y", "z", "w"]]
    r = measure_graph_centrality(nodes, _edges(*edges))
    assert r.verdict == "hub_dominated"
    assert r.degree_centralization == pytest.approx(1.0)
    assert r.max_degree == 4
    assert "hub" in r.hub_node_ids


def test_hub_node_ids_threshold() -> None:
    # hub connects to 3 of 4 others -> centrality 3/4 = 0.75 >= 0.50 -> hub.
    nodes = ["hub", "x", "y", "z", "w"]
    edges = [("hub", "x"), ("hub", "y"), ("hub", "z")]
    r = measure_graph_centrality(nodes, _edges(*edges))
    assert "hub" in r.hub_node_ids
    assert r.max_degree_centrality == pytest.approx(0.75)


# --- distributed (even spread — robust) -----------------------------------


def test_distributed_ring_graph() -> None:
    # Ring of 6: every node degree 2 -> centralization 0.0 -> distributed.
    nodes = list("abcdef")
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("f", "a")]
    r = measure_graph_centrality(nodes, _edges(*edges))
    assert r.verdict == "distributed"
    assert r.degree_centralization == pytest.approx(0.0)
    assert r.hub_node_ids == ()


def test_distributed_is_measured_not_default() -> None:
    assert measure_graph_centrality([], []).verdict == "unknown"
    assert measure_graph_centrality(["a", "b"], []).verdict == "edgeless"
    # A real distributed graph has edges + low centralization.
    nodes = list("abcd")
    r = measure_graph_centrality(
        nodes, _edges(("a", "b"), ("b", "c"), ("c", "d"), ("d", "a"), ("a", "c"), ("b", "d"))
    )
    assert r.verdict == "distributed"


# --- concentrated (in between) --------------------------------------------


def test_concentrated_moderate_hub() -> None:
    # A graph with some hub tendency but not a pure star -> centralization in (low, high).
    # Build: hub(3) + a separate pair, n=6.
    # degrees: hub=3, a=1,b=1,c=1, d=1,e=1 -> max=3, sum(max-d)= (3-3)+(3-1)*5 = 10
    # denom = (6-1)(6-2)=20 -> centralization 0.50 -> hub_dominated boundary.
    # Lower it: hub(2) among 6 nodes.
    nodes = ["hub", "a", "b", "c", "d", "e"]
    edges = [("hub", "a"), ("hub", "b"), ("c", "d")]
    r = measure_graph_centrality(nodes, _edges(*edges))
    # degrees: hub=2,a=1,b=1,c=1,d=1,e=0. max=2.
    # sum(max-d) = 0+1+1+1+1+2 = 6; denom 20 -> 0.30 -> concentrated (between 0.15,0.50)
    assert r.verdict == "concentrated"
    assert r.degree_centralization is not None and 0.15 < r.degree_centralization < 0.50


# --- n==2 (symmetric pair, centralization deferred) -----------------------


def test_two_node_pair_symmetric() -> None:
    r = measure_graph_centrality(["a", "b"], _edges(("a", "b")))
    assert r.verdict == "distributed"
    assert r.degree_centralization is None  # deferred for n<3
    assert r.max_degree_centrality == pytest.approx(1.0)
    assert any("centralization deferred" in n for n in r.notes)


# --- load-bearing: connected-but-hub-dominated vs connected-and-distributed


def test_connectivity_vs_concentration_orthogonal() -> None:
    # Both graphs are ONE component (fragmentation #1995 = connected) but differ
    # in concentration. Proves centrality != fragmentation.
    star = measure_graph_centrality(
        ["hub", "x", "y", "z"], _edges(("hub", "x"), ("hub", "y"), ("hub", "z"))
    )
    ring = measure_graph_centrality(
        ["a", "b", "c", "d"],
        _edges(("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")),
    )
    assert star.verdict == "hub_dominated"
    assert ring.verdict == "distributed"
    # Both are single-component graphs; centrality distinguishes them.


# --- Freeman centralization correctness -----------------------------------


def test_centralization_star_is_one() -> None:
    nodes = ["h", "a", "b", "c", "d"]
    r = measure_graph_centrality(nodes, _edges(("h", "a"), ("h", "b"), ("h", "c"), ("h", "d")))
    assert r.degree_centralization == pytest.approx(1.0)


def test_centralization_ring_is_zero() -> None:
    nodes = list("abcde")
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "a")]
    r = measure_graph_centrality(nodes, _edges(*edges))
    assert r.degree_centralization == pytest.approx(0.0)


# --- mean degree centrality -----------------------------------------------


def test_mean_degree_centrality() -> None:
    # 4 nodes, path a-b-c-d: degrees 1,2,2,1 -> centrality /3 = .33,.67,.67,.33
    r = measure_graph_centrality(
        list("abcd"), _edges(("a", "b"), ("b", "c"), ("c", "d"))
    )
    assert r.mean_degree_centrality == pytest.approx((1 + 2 + 2 + 1) / 4 / 3)


# --- dangling edges + dedup + self-loops ----------------------------------


def test_dangling_edges_surfaced() -> None:
    r = measure_graph_centrality(
        ["a", "b"], _edges(("a", "b"), ("a", "ghost"))
    )
    assert r.dangling_edge_count == 1
    assert r.edge_count == 1


def test_self_loop_ignored() -> None:
    r = measure_graph_centrality(["a", "b"], _edges(("a", "a"), ("a", "b")))
    assert r.edge_count == 1


def test_duplicate_edge_deduped() -> None:
    r = measure_graph_centrality(
        ["a", "b", "c"], _edges(("a", "b"), ("b", "a"), ("a", "b"))
    )
    assert r.edge_count == 1


# --- custom thresholds -----------------------------------------------------


def test_custom_high_concentration() -> None:
    # A graph at centralization 0.30 is concentrated under defaults but
    # hub_dominated under a lowered high_concentration of 0.25.
    nodes = ["hub", "a", "b", "c", "d", "e"]
    edges = [("hub", "a"), ("hub", "b"), ("c", "d")]  # centralization 0.30
    assert measure_graph_centrality(nodes, _edges(*edges)).verdict == "concentrated"
    assert (
        measure_graph_centrality(nodes, _edges(*edges), high_concentration=0.25).verdict
        == "hub_dominated"
    )


def test_custom_low_concentration() -> None:
    # Ring at 0.0 is distributed under defaults; with low_concentration negative
    # boundary it's still distributed (0.0 <= any positive floor).
    nodes = list("abcd")
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")]
    assert (
        measure_graph_centrality(nodes, _edges(*edges), low_concentration=0.01).verdict
        == "distributed"
    )


# --- validation ------------------------------------------------------------


def test_invalid_hub_threshold_zero() -> None:
    with pytest.raises(ValueError, match="hub_threshold"):
        measure_graph_centrality([], [], hub_threshold=0.0)


def test_invalid_high_concentration_over_one() -> None:
    with pytest.raises(ValueError, match="high_concentration"):
        measure_graph_centrality([], [], high_concentration=1.5)


def test_invalid_low_ge_high() -> None:
    with pytest.raises(ValueError, match="low_concentration"):
        measure_graph_centrality([], [], low_concentration=0.50, high_concentration=0.50)


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_graph_centrality(["a", "b"], _edges(("a", "b")))
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]

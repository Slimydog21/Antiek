"""Tests for substrate/knowledge_graph_fragmentation.py — global graph topology."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.knowledge_graph_fragmentation import (
    GraphEdge,
    measure_graph_fragmentation,
)


def _edges(*pairs: tuple[str, str]) -> list[GraphEdge]:
    return [GraphEdge(source=a, target=b) for a, b in pairs]


# --- unknown ---------------------------------------------------------------


def test_unknown_empty_graph() -> None:
    r = measure_graph_fragmentation([], [])
    assert r.verdict == "unknown"
    assert r.node_count == 0
    assert r.orphan_fraction is None
    assert r.largest_component_fraction is None
    assert r.mean_component_size is None
    assert r.component_sizes == ()
    assert r.authority == "advisory"


def test_unknown_never_fabricates_connected() -> None:
    assert measure_graph_fragmentation([], []).verdict != "connected"


# --- singleton (honest base case) -----------------------------------------


def test_singleton_one_node_no_edges() -> None:
    r = measure_graph_fragmentation(["solo"], [])
    assert r.verdict == "singleton"
    assert r.node_count == 1
    assert r.component_count == 1
    assert r.orphan_node_count == 1


def test_singleton_distinct_from_unknown() -> None:
    assert measure_graph_fragmentation([], []).verdict == "unknown"
    assert measure_graph_fragmentation(["solo"], []).verdict == "singleton"


# --- connected (one spanning component) -----------------------------------


def test_connected_chain() -> None:
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d"], _edges(("a", "b"), ("b", "c"), ("c", "d"))
    )
    assert r.verdict == "connected"
    assert r.component_count == 1
    assert r.largest_component_fraction == pytest.approx(1.0)
    assert r.component_sizes == (4,)


def test_connected_star() -> None:
    r = measure_graph_fragmentation(
        ["hub", "x", "y", "z"],
        _edges(("hub", "x"), ("hub", "y"), ("hub", "z")),
    )
    assert r.verdict == "connected"
    assert r.component_count == 1


def test_connected_is_measured_not_default() -> None:
    assert measure_graph_fragmentation([], []).verdict == "unknown"
    assert (
        measure_graph_fragmentation(
            ["a", "b"], _edges(("a", "b"))
        ).verdict
        == "connected"
    )


# --- fragmented (no dominant component) -----------------------------------


def test_fragmented_two_equal_clusters() -> None:
    # Two clusters of 3 each, no cross-link: largest = 3/6 = 0.5 == floor.
    # Verdict is cohesive at exactly 0.50 (< is strict). Add a third cluster.
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d", "e", "f"],
        _edges(("a", "b"), ("b", "c"), ("d", "e"), ("e", "f")),
    )
    # Two components of 3 each -> largest 0.50 == floor, not < floor -> cohesive.
    assert r.verdict == "cohesive"
    assert r.component_count == 2


def test_fragmented_spread_thin() -> None:
    # 6 nodes, 2 components of 2 and one pair -> largest 2/6 = 0.33 < 0.50.
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d", "e", "f"],
        _edges(("a", "b"), ("c", "d"), ("e", "f")),
    )
    assert r.verdict == "fragmented"
    assert r.component_count == 3
    assert r.largest_component_fraction == pytest.approx(1 / 3)


def test_fragmented_all_singletons() -> None:
    # No edges -> every node its own component -> fully fragmented.
    r = measure_graph_fragmentation(["a", "b", "c"], [])
    assert r.verdict == "fragmented"
    assert r.component_count == 3
    assert r.orphan_node_count == 3


# --- cohesive (one dominant + outliers) -----------------------------------


def test_cohesive_dominant_plus_outlier() -> None:
    # 10 nodes: a cluster of 8 + a pair of 2. largest 0.8 >= 0.50 -> cohesive.
    nodes = [f"n{i}" for i in range(10)]
    edges = [(f"n{i}", f"n{i+1}") for i in range(7)]  # chain n0..n7
    edges.append(("n8", "n9"))  # outlier pair
    r = measure_graph_fragmentation(nodes, _edges(*edges))
    assert r.verdict == "cohesive"
    assert r.component_count == 2
    assert r.largest_component_fraction == pytest.approx(0.8)
    assert r.component_sizes == (8, 2)


def test_cohesive_distinct_from_connected_and_fragmented() -> None:
    # Adding one outlier to a connected graph flips connected -> cohesive.
    nodes = ["a", "b", "c", "z"]
    assert measure_graph_fragmentation(
        nodes[:3], _edges(("a", "b"), ("b", "c"))
    ).verdict == "connected"
    r = measure_graph_fragmentation(nodes, _edges(("a", "b"), ("b", "c")))
    assert r.verdict == "cohesive"


# --- the load-bearing distinction: global != single-axis ----------------


def test_global_finds_cross_cluster_gap() -> None:
    # Two clusters each internally connected, never cross-link. A per-artifact
    # axis sees each cluster as connected; only the GLOBAL partition sees 2.
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d", "e", "f"],
        _edges(("a", "b"), ("b", "c"), ("d", "e"), ("e", "f")),
    )
    assert r.component_count == 2


# --- Union-Find correctness -----------------------------------------------


def test_transitive_connection() -> None:
    # a-b, b-c, c-d, d-e — all transitively one component.
    r = measure_graph_fragmentation(
        list("abcde"), _edges(("a", "b"), ("c", "d"), ("b", "c"), ("d", "e"))
    )
    assert r.verdict == "connected"
    assert r.component_count == 1


def test_cycle_handled() -> None:
    r = measure_graph_fragmentation(
        list("abcd"), _edges(("a", "b"), ("b", "c"), ("c", "d"), ("d", "a"))
    )
    assert r.verdict == "connected"


# --- orphans ---------------------------------------------------------------


def test_orphan_count_and_fraction() -> None:
    # a-b connected, c and d are orphans.
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d"], _edges(("a", "b"))
    )
    assert r.orphan_node_count == 2
    assert r.orphan_fraction == pytest.approx(0.5)
    assert any("orphan" in n for n in r.notes)


# --- dangling edges (undeclared nodes) ------------------------------------


def test_dangling_edges_surfaced_not_coerced() -> None:
    r = measure_graph_fragmentation(
        ["a", "b"],
        _edges(("a", "b"), ("a", "ghost"), ("b", "phantom")),
    )
    assert r.dangling_edge_count == 2
    assert r.edge_count == 1  # only a-b is valid
    assert any("dangling" in n for n in r.notes)


# --- self-loops + dedup ----------------------------------------------------


def test_self_loop_ignored() -> None:
    r = measure_graph_fragmentation(["a", "b"], _edges(("a", "a"), ("a", "b")))
    assert r.edge_count == 1
    assert r.verdict == "connected"


def test_duplicate_edge_deduped() -> None:
    r = measure_graph_fragmentation(
        ["a", "b"], _edges(("a", "b"), ("b", "a"), ("a", "b"))
    )
    assert r.edge_count == 1
    assert r.orphan_node_count == 0


# --- component_sizes audit -------------------------------------------------


def test_component_sizes_sorted_desc() -> None:
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d", "e", "f", "g"],
        _edges(("a", "b"), ("c", "d"), ("c", "e"), ("f", "g")),
    )
    assert r.component_sizes == (3, 2, 2)


def test_mean_component_size() -> None:
    r = measure_graph_fragmentation(
        ["a", "b", "c", "d", "e", "f"],
        _edges(("a", "b"), ("c", "d"), ("e", "f")),
    )
    assert r.mean_component_size == pytest.approx(2.0)


# --- custom dominance floor -----------------------------------------------


def test_custom_dominance_floor() -> None:
    # largest 0.8 is cohesive under 0.50 but fragmented under 0.90.
    nodes = [f"n{i}" for i in range(10)]
    edges = [(f"n{i}", f"n{i+1}") for i in range(7)] + [("n8", "n9")]
    assert measure_graph_fragmentation(nodes, _edges(*edges)).verdict == "cohesive"
    assert (
        measure_graph_fragmentation(
            nodes, _edges(*edges), dominance_floor=0.90
        ).verdict
        == "fragmented"
    )


# --- validation ------------------------------------------------------------


def test_invalid_dominance_floor_zero() -> None:
    with pytest.raises(ValueError, match="dominance_floor"):
        measure_graph_fragmentation([], [], dominance_floor=0.0)


def test_invalid_dominance_floor_over_one() -> None:
    with pytest.raises(ValueError, match="dominance_floor"):
        measure_graph_fragmentation([], [], dominance_floor=1.5)


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_graph_fragmentation(["a", "b"], _edges(("a", "b")))
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]

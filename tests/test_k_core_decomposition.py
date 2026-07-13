"""Tests for the k-core decomposition axis (ask #1 — deep-core identification).

Every fixture is hand-computed: core numbers verified by running the iterative peeling
process by hand before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.k_core_decomposition import (
    KCoreReport,
    measure_k_core_decomposition,
)

# ---------------------------------------------------------------------------
# Unknown / base cases.
# ---------------------------------------------------------------------------


def test_unknown_empty_graph() -> None:
    report = measure_k_core_decomposition(nodes=[], edges=[])
    assert report.total_node_count == 0
    assert report.max_core_number is None
    assert report.mean_core_number is None
    assert report.peripheral_fraction is None
    assert report.core_distribution == ()
    assert report.deep_core_ids == ()
    assert report.per_node == ()
    assert report.verdict == "unknown"
    assert report.authority == "advisory"


def test_singleton_one_node() -> None:
    report = measure_k_core_decomposition(nodes=["A"], edges=[])
    assert report.max_core_number == 0
    assert report.mean_core_number == pytest.approx(0.0)
    assert report.peripheral_fraction == pytest.approx(1.0)
    assert report.verdict == "singleton"


def test_edgeless_multiple_nodes() -> None:
    report = measure_k_core_decomposition(nodes=["A", "B", "C"], edges=[])
    assert report.max_core_number == 0
    assert report.mean_core_number == pytest.approx(0.0)
    assert report.deep_core_size == 0
    assert report.verdict == "edgeless"


# ---------------------------------------------------------------------------
# Shallow core — max core number <= 1 (trees, stars, paths).
# ---------------------------------------------------------------------------


def test_shallow_core_star_k14() -> None:
    # Star: center A, leaves B,C,D,E. All core 1 (center's leaves peel off first).
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C", "D", "E"],
        edges=[("A", "B"), ("A", "C"), ("A", "D"), ("A", "E")],
    )
    assert report.max_core_number == 1
    assert report.mean_core_number == pytest.approx(1.0)
    assert report.peripheral_fraction == pytest.approx(1.0)  # all core <= 1
    assert report.verdict == "shallow_core"
    # Center A has degree 4 but core 1 — degree != embedding depth.
    by_id = {nc.node_id: nc.core_number for nc in report.per_node}
    assert by_id["A"] == 1


def test_shallow_core_path_p4() -> None:
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "C"), ("C", "D")],
    )
    assert report.max_core_number == 1
    assert report.verdict == "shallow_core"


# ---------------------------------------------------------------------------
# Cyclic core — max core number == 2 (cycles, no dense clusters).
# ---------------------------------------------------------------------------


def test_cyclic_core_triangle() -> None:
    # Triangle K3: all core 2.
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert report.max_core_number == 2
    assert report.mean_core_number == pytest.approx(2.0)
    assert report.deep_core_ids == ("A", "B", "C")
    assert report.deep_core_size == 3
    assert report.verdict == "cyclic_core"


def test_cyclic_core_square_cycle() -> None:
    # Cycle C4: all core 2 (removing any node leaves a path — still connected, but no
    # node has 3 mutually-connected neighbors).
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")],
    )
    assert report.max_core_number == 2
    assert report.verdict == "cyclic_core"


def test_cyclic_core_two_triangles_shared_edge() -> None:
    # Triangles ABC and ABD sharing edge A-B. All core 2.
    edges = [("A", "B"), ("A", "C"), ("B", "C"), ("A", "D"), ("B", "D")]
    report = measure_k_core_decomposition(nodes=["A", "B", "C", "D"], edges=edges)
    assert report.max_core_number == 2
    assert report.deep_core_size == 4
    assert report.verdict == "cyclic_core"


# ---------------------------------------------------------------------------
# Deep core — max core number >= 3 (dense mutually-reinforcing subgraph).
# ---------------------------------------------------------------------------


def test_deep_core_k4_complete() -> None:
    # K4: all core 3.
    edges = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"), ("C", "D"),
    ]
    report = measure_k_core_decomposition(nodes=["A", "B", "C", "D"], edges=edges)
    assert report.max_core_number == 3
    assert report.deep_core_size == 4
    assert report.deep_core_ids == ("A", "B", "C", "D")
    assert report.verdict == "deep_core"


def test_deep_core_k4_with_pendant() -> None:
    # K4 (A,B,C,D) + pendant E attached to A. K4 nodes: core 3. E: core 1.
    edges = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"), ("C", "D"),
        ("A", "E"),  # pendant
    ]
    report = measure_k_core_decomposition(nodes=["A", "B", "C", "D", "E"], edges=edges)
    assert report.max_core_number == 3
    assert report.deep_core_size == 4
    assert "E" not in report.deep_core_ids
    by_id = {nc.node_id: nc.core_number for nc in report.per_node}
    assert by_id["E"] == 1
    assert by_id["A"] == 3
    assert report.peripheral_fraction == pytest.approx(1 / 5)


def test_deep_core_k33_bipartite() -> None:
    # K3,3: left {A,B,C}, right {D,E,F}, all connected. All core 3.
    edges = [
        ("A", "D"), ("A", "E"), ("A", "F"),
        ("B", "D"), ("B", "E"), ("B", "F"),
        ("C", "D"), ("C", "E"), ("C", "F"),
    ]
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C", "D", "E", "F"], edges=edges
    )
    assert report.max_core_number == 3
    assert report.deep_core_size == 6
    assert report.verdict == "deep_core"


# ---------------------------------------------------------------------------
# Edge cases: self-loops, duplicates, disconnected.
# ---------------------------------------------------------------------------


def test_self_loop_dropped() -> None:
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C"],
        edges=[("A", "A"), ("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert report.max_core_number == 2  # triangle (self-loop dropped)


def test_duplicate_edges_merged() -> None:
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("A", "B"), ("B", "C"), ("B", "C"), ("C", "A"), ("C", "A")],
    )
    assert report.max_core_number == 2  # triangle


def test_disconnected_two_triangles() -> None:
    # Two disjoint triangles: each core 2 independently.
    report = measure_k_core_decomposition(
        nodes=["A", "B", "C", "D", "E", "F"],
        edges=[("A", "B"), ("B", "C"), ("C", "A"), ("D", "E"), ("E", "F"), ("F", "D")],
    )
    assert report.max_core_number == 2
    assert report.deep_core_size == 6


def test_edge_endpoints_included() -> None:
    report = measure_k_core_decomposition(nodes=["A"], edges=[("A", "Z")])
    assert report.total_node_count == 2


# ---------------------------------------------------------------------------
# Core distribution auditability.
# ---------------------------------------------------------------------------


def test_core_distribution_auditable() -> None:
    # K4 + pendant: layers are core 3 (4 nodes) and core 1 (1 node).
    edges = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"), ("C", "D"),
        ("A", "E"),
    ]
    report = measure_k_core_decomposition(nodes=["A", "B", "C", "D", "E"], edges=edges)
    layers = {cl.core_number: cl.node_count for cl in report.core_distribution}
    assert layers == {3: 4, 1: 1}


def test_per_node_sorted_desc() -> None:
    edges = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"), ("C", "D"),
        ("A", "E"),
    ]
    report = measure_k_core_decomposition(nodes=["A", "B", "C", "D", "E"], edges=edges)
    core_values = [nc.core_number for nc in report.per_node]
    assert core_values == sorted(core_values, reverse=True)


# ---------------------------------------------------------------------------
# Determinism + immutability + report type.
# ---------------------------------------------------------------------------


def test_report_is_deterministic() -> None:
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    a = measure_k_core_decomposition(nodes=nodes, edges=edges)
    b = measure_k_core_decomposition(nodes=nodes, edges=edges)
    assert a == b


def test_report_is_frozen() -> None:
    report = measure_k_core_decomposition(nodes=["A", "B"], edges=[("A", "B")])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "deep_core"  # type: ignore[misc]


def test_report_type() -> None:
    report = measure_k_core_decomposition(nodes=["A", "B"], edges=[("A", "B")])
    assert isinstance(report, KCoreReport)
    assert report.authority == "advisory"

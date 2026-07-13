"""Tests for the Midnight Oil goal-interdependence axis (ask #13).

Assesses the structural coherence of a goal dependency graph: cycle detection,
independent/dependent counts, critical-path depth, density, and the
parallelizable/sequential/mixed/cyclic/unknown verdicts.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_goal_interdependence import (
    GoalDependency,
    GoalInterdependenceError,
    measure_goal_interdependence,
)

# --- unknown --------------------------------------------------------------


def test_unknown_when_no_goals() -> None:
    r = measure_goal_interdependence([], [])
    assert r.verdict == "unknown"
    assert r.goal_count == 0
    assert r.max_depth is None
    assert r.dependency_density is None
    assert r.has_cycle is None
    assert r.authority == "advisory"


def test_unknown_when_single_goal() -> None:
    r = measure_goal_interdependence(["g1"], [])
    assert r.verdict == "unknown"
    assert r.goal_count == 1
    assert r.max_depth is None
    assert r.dependency_density is None


# --- parallelizable -------------------------------------------------------


def test_parallelizable_all_independent() -> None:
    r = measure_goal_interdependence(["g1", "g2", "g3"], [])
    assert r.verdict == "parallelizable"
    assert r.independent_goal_count == 3
    assert r.dependent_goal_count == 0
    assert r.edge_count == 0
    assert r.dependency_density == 0.0
    assert r.has_cycle is False
    # No edges -> each goal is depth 1.
    assert r.max_depth == 1


# --- sequential -----------------------------------------------------------


def test_sequential_pure_chain() -> None:
    deps = [
        GoalDependency("g1", "g2"),
        GoalDependency("g2", "g3"),
    ]
    r = measure_goal_interdependence(["g1", "g2", "g3"], deps)
    assert r.verdict == "sequential"
    assert r.max_depth == 3  # critical path spans all 3 goals
    assert r.independent_goal_count == 1  # only g1 (root)
    assert r.dependent_goal_count == 2  # g2, g3
    assert r.edge_count == 2
    assert r.has_cycle is False


# --- mixed ----------------------------------------------------------------


def test_mixed_some_parallel_some_dependent() -> None:
    # g1, g2 independent; g3 depends on g1; g4 depends on g2.
    deps = [GoalDependency("g1", "g3"), GoalDependency("g2", "g4")]
    r = measure_goal_interdependence(["g1", "g2", "g3", "g4"], deps)
    assert r.verdict == "mixed"
    assert r.independent_goal_count == 2  # g1, g2
    assert r.dependent_goal_count == 2  # g3, g4
    assert r.max_depth == 2  # g1->g3 or g2->g4 (length-2 chains)
    assert r.edge_count == 2
    assert r.has_cycle is False


def test_mixed_diamond_dependency() -> None:
    # g1 -> g2, g1 -> g3, g2 -> g4, g3 -> g4 (diamond).
    deps = [
        GoalDependency("g1", "g2"),
        GoalDependency("g1", "g3"),
        GoalDependency("g2", "g4"),
        GoalDependency("g3", "g4"),
    ]
    r = measure_goal_interdependence(["g1", "g2", "g3", "g4"], deps)
    assert r.verdict == "mixed"
    assert r.independent_goal_count == 1  # g1
    assert r.max_depth == 3  # g1 -> g2 -> g4
    assert r.edge_count == 4
    assert r.has_cycle is False


# --- cyclic ---------------------------------------------------------------


def test_cyclic_two_node_cycle() -> None:
    deps = [GoalDependency("g1", "g2"), GoalDependency("g2", "g1")]
    r = measure_goal_interdependence(["g1", "g2"], deps)
    assert r.verdict == "cyclic"
    assert r.has_cycle is True
    assert r.max_depth is None  # unschedulable


def test_cyclic_three_node_cycle() -> None:
    deps = [
        GoalDependency("g1", "g2"),
        GoalDependency("g2", "g3"),
        GoalDependency("g3", "g1"),
    ]
    r = measure_goal_interdependence(["g1", "g2", "g3"], deps)
    assert r.verdict == "cyclic"
    assert r.has_cycle is True


def test_cyclic_self_loop() -> None:
    deps = [GoalDependency("g1", "g1")]
    r = measure_goal_interdependence(["g1", "g2"], deps)
    assert r.verdict == "cyclic"
    assert r.has_cycle is True


def test_cyclic_partial_graph() -> None:
    # g1->g2 fine, but g2->g3->g2 is a cycle.
    deps = [
        GoalDependency("g1", "g2"),
        GoalDependency("g2", "g3"),
        GoalDependency("g3", "g2"),
    ]
    r = measure_goal_interdependence(["g1", "g2", "g3"], deps)
    assert r.verdict == "cyclic"
    assert r.has_cycle is True


# --- density --------------------------------------------------------------


def test_density_calculation() -> None:
    # 4 goals -> possible_edges = 4*3/2 = 6. 2 edges -> density 2/6.
    deps = [GoalDependency("g1", "g2"), GoalDependency("g3", "g4")]
    r = measure_goal_interdependence(["g1", "g2", "g3", "g4"], deps)
    assert r.dependency_density == pytest.approx(2 / 6)


def test_density_two_goals_one_edge() -> None:
    deps = [GoalDependency("g1", "g2")]
    r = measure_goal_interdependence(["g1", "g2"], deps)
    # 2 goals -> possible = 1; 1 edge -> density 1.0.
    assert r.dependency_density == pytest.approx(1.0)


# --- de-duplication -------------------------------------------------------


def test_duplicate_edges_deduplicated() -> None:
    deps = [
        GoalDependency("g1", "g2"),
        GoalDependency("g1", "g2"),  # duplicate
    ]
    r = measure_goal_interdependence(["g1", "g2"], deps)
    assert r.edge_count == 1


# --- validation -----------------------------------------------------------


def test_dependency_undeclared_predecessor_raises() -> None:
    with pytest.raises(GoalInterdependenceError):
        measure_goal_interdependence(["g1"], [GoalDependency("gX", "g1")])


def test_dependency_undeclared_successor_raises() -> None:
    with pytest.raises(GoalInterdependenceError):
        measure_goal_interdependence(["g1"], [GoalDependency("g1", "gY")])


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    goals = ["g1", "g2", "g3"]
    deps = [GoalDependency("g1", "g2"), GoalDependency("g2", "g3")]
    assert measure_goal_interdependence(goals, deps) == measure_goal_interdependence(
        goals, deps
    )


def test_report_is_frozen_immutable() -> None:
    r = measure_goal_interdependence(["g1", "g2"], [])
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "cyclic"  # type: ignore[misc]


def test_dependency_dataclass_is_frozen() -> None:
    dep = GoalDependency("g1", "g2")
    with pytest.raises(dataclasses.FrozenInstanceError):
        dep.successor_id = "g3"  # type: ignore[misc]

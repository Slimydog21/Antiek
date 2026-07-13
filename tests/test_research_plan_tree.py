"""Tests for ``substrate.research_plan_tree`` — the visible/steerable research-plan
tree (deep-research competitive spec gap A / P0). Each test isolates ONE integrity
property (single_root / parents_resolve / acyclic) or ONE steering/outcome behavior
so the folds are exercised independently."""

from __future__ import annotations

import dataclasses

import pytest

from substrate.research_plan_tree import (
    STATUS_BRANCHED,
    STATUS_CHASING,
    STATUS_DEPRIORITIZED,
    STATUS_DONE,
    STATUS_PLANNED,
    STATUS_TRANSITIONS,
    STATUSES,
    PlanNode,
    PlanTreeError,
    validate_plan_tree,
    validate_status_transition,
)


def _node(
    node_id: str,
    sub_question: str = "q",
    status: str = STATUS_PLANNED,
    parent_node_id: str | None = None,
    investigation_id: str | None = None,
) -> PlanNode:
    return PlanNode(
        node_id=node_id,
        sub_question=sub_question,
        status=status,
        parent_node_id=parent_node_id,
        investigation_id=investigation_id,
    )


def _complete_tree() -> list[PlanNode]:
    # root -> two leaves, both done
    return [
        _node("root", status=STATUS_CHASING),
        _node("leaf_a", status=STATUS_DONE, parent_node_id="root", investigation_id="inv_a"),
        _node("leaf_b", status=STATUS_DONE, parent_node_id="root", investigation_id="inv_b"),
    ]


def test_valid_tree_is_steerable_and_complete() -> None:
    report = validate_plan_tree(_complete_tree())
    assert report.node_count == 3
    assert report.single_root is True
    assert report.steerable is True
    assert report.complete is True
    assert report.root_node_id == "root"
    assert set(report.leaf_node_ids) == {"leaf_a", "leaf_b"}
    assert report.leaf_count == 2
    assert report.orphaned_node_ids == ()
    assert report.cyclic_node_ids == ()
    assert report.pending_leaf_ids == ()
    assert report.authority == "advisory"


def test_empty_tree_is_not_steerable_complete_unknown() -> None:
    report = validate_plan_tree([])
    assert report.node_count == 0
    assert report.single_root is False
    assert report.steerable is False
    assert report.complete is None  # cannot assess outcome over empty/broken structure
    assert report.root_node_id is None


def test_multi_root_forest_breaks_single_root() -> None:
    nodes = [
        _node("root_a", status=STATUS_CHASING),
        _node("root_b", status=STATUS_CHASING),
    ]
    report = validate_plan_tree(nodes)
    assert report.single_root is False
    assert report.steerable is False
    assert report.complete is None
    assert "not a single-rooted tree" in " ".join(report.notes)


def test_orphan_node_breaks_steerable() -> None:
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("orphan", status=STATUS_PLANNED, parent_node_id="missing_parent"),
    ]
    report = validate_plan_tree(nodes)
    assert report.single_root is True
    assert report.orphaned_node_ids == ("orphan",)
    assert report.steerable is False
    assert report.complete is None


def test_cycle_breaks_steerable() -> None:
    # A -> B -> A (no root reaches None)
    nodes = [
        _node("a", status=STATUS_CHASING, parent_node_id="b"),
        _node("b", status=STATUS_CHASING, parent_node_id="a"),
    ]
    report = validate_plan_tree(nodes)
    assert report.cyclic_node_ids == ("a", "b")
    assert report.single_root is False  # no node has parent None
    assert report.steerable is False
    assert report.complete is None


def test_cycle_with_root_still_detected() -> None:
    # root is a proper root (parent None) but a/b form a 2-cycle separately.
    # single_root holds (only root has parent None) yet the cycle breaks steerable.
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("a", status=STATUS_CHASING, parent_node_id="b"),
        _node("b", status=STATUS_CHASING, parent_node_id="a"),
    ]
    report = validate_plan_tree(nodes)
    assert report.single_root is True
    assert report.cyclic_node_ids == ("a", "b")
    assert report.steerable is False


def test_incomplete_when_leaf_pending() -> None:
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("done_leaf", status=STATUS_DONE, parent_node_id="root", investigation_id="inv"),
        _node("planned_leaf", status=STATUS_PLANNED, parent_node_id="root"),
    ]
    report = validate_plan_tree(nodes)
    assert report.steerable is True
    assert report.complete is False
    assert report.pending_leaf_ids == ("planned_leaf",)


def test_chasing_leaf_is_pending() -> None:
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("chasing_leaf", status=STATUS_CHASING, parent_node_id="root", investigation_id="inv"),
    ]
    report = validate_plan_tree(nodes)
    assert report.steerable is True
    assert report.complete is False
    assert report.pending_leaf_ids == ("chasing_leaf",)


def test_deprioritized_leaf_excluded_from_completion() -> None:
    # done leaf + deprioritized leaf -> complete (deprioritized honestly excluded)
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("done_leaf", status=STATUS_DONE, parent_node_id="root", investigation_id="inv"),
        _node("deferred_leaf", status=STATUS_DEPRIORITIZED, parent_node_id="root"),
    ]
    report = validate_plan_tree(nodes)
    assert report.steerable is True
    assert report.complete is True  # deprioritized excluded, not pending
    assert report.pending_leaf_ids == ()
    assert "deprioritized" in " ".join(report.notes).lower()


def test_deprioritized_never_collapses_with_done_or_planned() -> None:
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("d", status=STATUS_DEPRIORITIZED, parent_node_id="root"),
    ]
    report = validate_plan_tree(nodes)
    assert report.status_counts[STATUS_DEPRIORITIZED] == 1
    assert report.status_counts[STATUS_DONE] == 0
    assert report.status_counts[STATUS_PLANNED] == 0
    assert report.complete is True  # the only leaf is deprioritized -> excluded -> complete


def test_non_leaf_status_does_not_count_toward_completion() -> None:
    # a non-leaf (has a child) that is planned does NOT block completion; only leaves count
    nodes = [
        _node("root", status=STATUS_PLANNED),  # non-leaf (has child)
        _node("done_leaf", status=STATUS_DONE, parent_node_id="root", investigation_id="inv"),
    ]
    report = validate_plan_tree(nodes)
    assert report.steerable is True
    assert report.complete is True
    assert report.leaf_node_ids == ("done_leaf",)


def test_status_transition_allowed_pairs() -> None:
    assert validate_status_transition(STATUS_PLANNED, STATUS_CHASING) is True
    assert validate_status_transition(STATUS_CHASING, STATUS_DONE) is True
    assert validate_status_transition(STATUS_CHASING, STATUS_DEPRIORITIZED) is True
    assert validate_status_transition(STATUS_DONE, STATUS_BRANCHED) is True
    assert validate_status_transition(STATUS_DEPRIORITIZED, STATUS_PLANNED) is True
    assert validate_status_transition(STATUS_BRANCHED, STATUS_CHASING) is True


def test_status_transition_rejected_pairs() -> None:
    # done -> planned erases completed work
    assert validate_status_transition(STATUS_DONE, STATUS_PLANNED) is False
    # deprioritized -> done fakes completion of never-run work
    assert validate_status_transition(STATUS_DEPRIORITIZED, STATUS_DONE) is False
    # chasing -> planned unwinds a started chase
    assert validate_status_transition(STATUS_CHASING, STATUS_PLANNED) is False


def test_status_transition_unknown_status_raises() -> None:
    with pytest.raises(PlanTreeError):
        validate_status_transition("bogus", STATUS_CHASING)
    with pytest.raises(PlanTreeError):
        validate_status_transition(STATUS_PLANNED, "bogus")


def test_self_reference_is_cycle() -> None:
    nodes = [
        _node("root", status=STATUS_CHASING, parent_node_id="root"),
    ]
    report = validate_plan_tree(nodes)
    assert report.cyclic_node_ids == ("root",)
    assert report.steerable is False


def test_validation_unknown_status_raises() -> None:
    with pytest.raises(PlanTreeError):
        validate_plan_tree([_node("x", status="bogus")])


def test_validation_empty_node_id_raises() -> None:
    with pytest.raises(PlanTreeError):
        validate_plan_tree([_node("", status=STATUS_PLANNED)])


def test_validation_empty_sub_question_raises() -> None:
    bad = PlanNode(node_id="x", sub_question="", status=STATUS_PLANNED, parent_node_id=None)
    with pytest.raises(PlanTreeError):
        validate_plan_tree([bad])


def test_validation_duplicate_node_id_raises() -> None:
    nodes = [
        _node("x", status=STATUS_CHASING),
        _node("x", status=STATUS_PLANNED, parent_node_id="x"),
    ]
    with pytest.raises(PlanTreeError):
        validate_plan_tree(nodes)


def test_status_counts_complete_for_all_statuses() -> None:
    nodes = _complete_tree()
    report = validate_plan_tree(nodes)
    for status in STATUSES:
        assert status in report.status_counts
    assert sum(report.status_counts.values()) == report.node_count


def test_transition_table_contract() -> None:
    # every transition pair references canonical statuses
    for from_status, to_status in STATUS_TRANSITIONS:
        assert from_status in STATUSES
        assert to_status in STATUSES
    # at least one transition per non-terminal status exists (the table is non-empty + covers)
    assert len(STATUS_TRANSITIONS) >= 10


def test_deterministic_same_nodes_same_report() -> None:
    nodes = _complete_tree()
    r1 = validate_plan_tree(nodes)
    r2 = validate_plan_tree(nodes)
    assert r1 == r2


def test_report_is_frozen() -> None:
    report = validate_plan_tree(_complete_tree())
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.steerable = False  # type: ignore[misc]


def test_planned_node_with_no_investigation_is_honest_unknown() -> None:
    # a planned node with investigation_id None is "not yet started" — never fabricated as chasing
    nodes = [
        _node("root", status=STATUS_CHASING),
        _node("planned_leaf", status=STATUS_PLANNED, parent_node_id="root", investigation_id=None),
    ]
    report = validate_plan_tree(nodes)
    node = next(n for n in nodes if n.node_id == "planned_leaf")
    assert node.investigation_id is None
    assert node.status == STATUS_PLANNED
    assert report.status_counts[STATUS_PLANNED] == 1
    assert report.complete is False

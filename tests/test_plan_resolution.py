"""Tests for substrate.deep_research_quality.plan_resolution — recursion-closer."""

from __future__ import annotations

import math
import typing
from dataclasses import dataclass, field

import pytest

from substrate.deep_research_quality.plan_resolution import (
    PlanQuestion,
    PlanResolutionError,
    PlanResolutionReport,
    QuestionResolution,
    score_plan_resolution,
)


@dataclass
class FakePlanNode:
    """Mutable plan node mirroring PlanNode's load-bearing fields."""

    question: str
    local_id: str
    graph_node_id: str | None = None
    children: list[FakePlanNode] = field(default_factory=list)


def _node(
    qid: str,
    gid: str | None = None,
    children: list[FakePlanNode] | None = None,
    *,
    question: str | None = None,
) -> PlanQuestion:
    return typing.cast(
        PlanQuestion,
        FakePlanNode(
            question=question if question is not None else qid,
            local_id=qid,
            graph_node_id=gid,
            children=children or [],
        ),
    )


# --- the three resolution states -------------------------------------------


def test_resolved_question_in_set() -> None:
    root = _node("root", gid="g-root")
    child = _node("c1", gid="g-c1")
    root.children.append(child)
    report = score_plan_resolution(root, {"g-root", "g-c1"})
    assert report.resolved_count == 2
    assert report.unresolved_count == 0
    assert all(q.state == "resolved" for q in report.resolved)


def test_unresolved_question_has_gid_but_not_in_set() -> None:
    root = _node("root", gid="g-root")
    report = score_plan_resolution(root, set())  # nothing resolved
    assert report.unresolved_count == 1
    assert report.unresolved[0].state == "unresolved"
    assert report.unresolved[0].graph_node_id == "g-root"


def test_unpersisted_question_has_no_gid() -> None:
    root = _node("root", gid="g-root")
    child = _node("c1", gid=None)  # never persisted
    root.children.append(child)
    report = score_plan_resolution(root, {"g-root"})
    assert report.resolved_count == 1
    assert report.unpersisted_count == 1
    assert report.unpersisted[0].state == "unpersisted"
    assert report.unpersisted[0].graph_node_id is None


# --- the coverage score (hard to vary) -------------------------------------


def test_coverage_is_resolved_over_measurable() -> None:
    """2 resolved + 1 unresolved = 2/3; unpersisted excluded from denominator."""
    root = _node("root", gid="g-root")
    c1 = _node("c1", gid="g-c1")
    c2 = _node("c2", gid="g-c2")  # unresolved
    c3 = _node("c3", gid=None)  # unpersisted (excluded)
    root.children.extend([c1, c2, c3])
    report = score_plan_resolution(root, {"g-root", "g-c1"})  # root + c1 resolved
    assert report.measurable_count == 3  # root, c1, c2 (c3 excluded)
    assert report.resolved_count == 2
    assert report.coverage == pytest.approx(2 / 3)


def test_unpersisted_excluded_not_penalized() -> None:
    """A half-persisted plan should not score artificially low."""
    root = _node("root", gid="g-root")
    for i in range(9):
        root.children.append(_node(f"c{i}", gid=None))  # 9 unpersisted
    report = score_plan_resolution(root, {"g-root"})
    assert report.measurable_count == 1
    assert report.coverage == 1.0  # the one measurable (root) is resolved


def test_all_resolved_is_full_coverage() -> None:
    root = _node("root", gid="g-root")
    root.children.append(_node("c1", gid="g-c1"))
    report = score_plan_resolution(root, {"g-root", "g-c1"})
    assert report.coverage == 1.0


def test_none_resolved_is_zero_coverage() -> None:
    root = _node("root", gid="g-root")
    root.children.append(_node("c1", gid="g-c1"))
    report = score_plan_resolution(root, set())
    assert report.coverage == 0.0
    assert report.measurable_count == 2


# --- orthogonality: nothing to measure -------------------------------------


def test_all_unpersisted_is_not_measured() -> None:
    """Resolution of an ungrounded plan is unknown, never fabricated."""
    root = _node("root", gid=None)
    report = score_plan_resolution(root, set())
    assert report.measured is False
    assert report.coverage == 0.0
    assert report.measurable_count == 0
    assert report.unpersisted_count == 1


# --- root resolution: the keystone -----------------------------------------


def test_root_resolved_true() -> None:
    root = _node("root", gid="g-root")
    report = score_plan_resolution(root, {"g-root"})
    assert report.root_resolved is True
    assert any("keystone met" in n for n in report.notes)


def test_root_unresolved_leaves_resolved_keystone_fails() -> None:
    """A plan that resolves leaves but not the root has NOT delivered its answer."""
    root = _node("root", gid="g-root")
    root.children.append(_node("c1", gid="g-c1"))
    report = score_plan_resolution(root, {"g-c1"})  # only the leaf resolved
    assert report.root_resolved is False
    assert report.coverage == pytest.approx(0.5)
    assert any("keystone failed" in n for n in report.notes)


def test_root_unpersisted_is_none() -> None:
    root = _node("root", gid=None)
    report = score_plan_resolution(root, set())
    assert report.root_resolved is None
    assert any("unmeasurable" in n for n in report.notes)


# --- the re-plan signal ----------------------------------------------------


def test_unresolved_list_is_the_replan_surface() -> None:
    root = _node("root", gid="g-root")
    root.children.extend([_node("c1", gid="g-c1"), _node("c2", gid="g-c2")])
    report = score_plan_resolution(root, set())  # nothing resolved
    assert len(report.unresolved) == 3
    assert {q.local_id for q in report.unresolved} == {"root", "c1", "c2"}
    assert any("RE-PLAN SIGNAL" in n for n in report.notes)


# --- honesty: pure, deterministic, advisory, auditable --------------------


def test_pure_and_idempotent() -> None:
    root = _node("root", gid="g-root")
    root.children.append(_node("c1", gid="g-c1"))
    resolved = {"g-root"}
    first = score_plan_resolution(root, resolved)
    second = score_plan_resolution(root, resolved)
    assert first == second


def test_authority_is_advisory() -> None:
    report = score_plan_resolution(_node("root", gid="g-root"), {"g-root"})
    assert report.authority == "advisory"


def test_report_is_frozen_value() -> None:
    report = score_plan_resolution(_node("root", gid="g-root"), set())
    assert isinstance(report, PlanResolutionReport)
    with pytest.raises((AttributeError, Exception)):
        report.coverage = 1.0  # type: ignore[misc]


def test_every_question_state_carried_through() -> None:
    root = _node("root", gid="g-root")
    c1 = _node("c1", gid="g-c1")
    c2 = _node("c2", gid=None)
    root.children.extend([c1, c2])
    report = score_plan_resolution(root, {"g-c1"})  # c1 resolved, root+c2 not
    all_states = {q.local_id: q.state for q in (report.resolved + report.unresolved + report.unpersisted)}
    assert all_states == {"root": "unresolved", "c1": "resolved", "c2": "unpersisted"}


def test_depth_first_stable_traversal_order() -> None:
    root = _node("root", gid="g-root")
    root.children.extend([_node("c1", gid="g-c1"), _node("c2", gid="g-c2")])
    root.children[0].children.append(_node("c1a", gid="g-c1a"))
    report = score_plan_resolution(root, set())
    ids = [q.local_id for q in report.unresolved]
    assert ids == ["root", "c1", "c1a", "c2"]  # depth-first


def test_coverage_in_unit_interval() -> None:
    """coverage is always a finite float in [0, 1]."""
    plans = [
        _node("root", gid=None),  # unmeasurable
        _node("root", gid="g"),  # none resolved
        _node("root", gid="g"),  # resolved
    ]
    for root in plans:
        report = score_plan_resolution(root, {"g"})
        assert isinstance(report.coverage, float)
        assert math.isfinite(report.coverage)
        assert 0.0 <= report.coverage <= 1.0


# --- input validation ------------------------------------------------------


def test_empty_root_question_rejected() -> None:
    with pytest.raises(PlanResolutionError, match="non-empty"):
        score_plan_resolution(_node("root", question="   "), set())


def test_empty_local_id_rejected() -> None:
    bad = typing.cast(
        PlanQuestion,
        FakePlanNode(question="q", local_id="  ", graph_node_id="g"),
    )
    with pytest.raises(PlanResolutionError, match="local_id"):
        score_plan_resolution(bad, set())


def test_question_resolution_frozen() -> None:
    qr = QuestionResolution(local_id="x", question="q", graph_node_id="g", state="resolved")
    with pytest.raises((AttributeError, Exception)):
        qr.state = "unresolved"  # type: ignore[misc]

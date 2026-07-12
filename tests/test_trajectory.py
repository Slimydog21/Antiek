"""Tests for the research-trajectory topology analyzer (ask #1 recursion).

Exercises: depth computation, cycle detection, orphan counting, leaf/branching,
resolution rate, verdict bands (productive/shallow/fruitless/unknown), validation,
purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.trajectory import (
    InvestigationNode,
    TrajectoryError,
    TrajectoryInputs,
    TrajectoryReport,
    analyze_trajectory,
)


def _node(
    nid: str,
    *,
    insights: int = 2,
    questions: int = 1,
    children: tuple[str, ...] = (),
) -> InvestigationNode:
    return InvestigationNode(
        investigation_id=nid,
        insight_count=insights,
        question_count=questions,
        child_investigation_ids=children,
    )


def _trajectory(
    roots: tuple[str, ...],
    nodes: list[InvestigationNode],
) -> TrajectoryInputs:
    return TrajectoryInputs(root_investigation_ids=roots, nodes=tuple(nodes))


# --- depth + breadth -------------------------------------------------------


def test_single_flat_investigation_is_shallow() -> None:
    report = analyze_trajectory(
        _trajectory(("A",), [_node("A", insights=3, questions=0)])
    )
    assert report.max_depth == 1
    assert report.leaf_count == 1
    assert report.verdict == "shallow"


def test_linear_chain_depth_3() -> None:
    report = analyze_trajectory(
        _trajectory(
            ("A",),
            [
                _node("A", children=("B",)),
                _node("B", children=("C",)),
                _node("C", insights=2, questions=0),
            ],
        )
    )
    assert report.max_depth == 3
    assert report.leaf_count == 1  # C is the only leaf
    assert report.avg_branching_factor == pytest.approx(1.0)


def test_branching_factor_two_children() -> None:
    report = analyze_trajectory(
        _trajectory(
            ("A",),
            [
                _node("A", children=("B", "C")),
                _node("B", insights=2, questions=0),
                _node("C", insights=2, questions=0),
            ],
        )
    )
    assert report.leaf_count == 2
    assert report.avg_branching_factor == pytest.approx(2.0)


# --- verdict: productive ---------------------------------------------------


def test_productive_deep_tree_high_resolution() -> None:
    # A -> B, C (both resolved leaves with insights)
    report = analyze_trajectory(
        _trajectory(
            ("A",),
            [
                _node("A", children=("B", "C")),
                _node("B", insights=3, questions=0),
                _node("C", insights=2, questions=1),
            ],
        )
    )
    assert report.max_depth == 2
    assert report.resolution_rate is not None and report.resolution_rate == pytest.approx(1.0)
    assert report.verdict == "productive"


# --- verdict: fruitless_expansion ------------------------------------------


def test_fruitless_expansion_leaves_only_questions() -> None:
    # A -> B, C but B and C have only questions (no insights) -> low resolution
    report = analyze_trajectory(
        _trajectory(
            ("A",),
            [
                _node("A", children=("B", "C")),
                _node("B", insights=0, questions=5),
                _node("C", insights=0, questions=3),
            ],
        )
    )
    assert report.max_depth is not None and report.max_depth > 1
    assert report.resolution_rate is not None and report.resolution_rate < 0.25
    assert report.verdict == "fruitless_expansion"


# --- verdict: unknown (empty) ----------------------------------------------


def test_empty_tree_is_unknown() -> None:
    report = analyze_trajectory(_trajectory((), []))
    assert report.verdict == "unknown"
    assert report.max_depth is None
    assert report.resolution_rate is None


def test_unreachable_tree_is_unknown() -> None:
    # Root doesn't exist in nodes -> nothing reachable
    report = analyze_trajectory(
        _trajectory(("X",), [_node("A", insights=2)])
    )
    assert report.reachable_count == 0
    assert report.verdict == "unknown"
    assert report.orphan_count == 1


# --- cycle detection -------------------------------------------------------


def test_cycle_detected_raises() -> None:
    with pytest.raises(TrajectoryError, match="cycle"):
        analyze_trajectory(
            _trajectory(
                ("A",),
                [
                    _node("A", children=("B",)),
                    _node("B", children=("A",)),  # back-edge -> cycle
                ],
            )
        )


def test_self_cycle_detected() -> None:
    with pytest.raises(TrajectoryError, match="cycle"):
        analyze_trajectory(
            _trajectory(("A",), [_node("A", children=("A",))])
        )


# --- orphans ---------------------------------------------------------------


def test_orphan_count_unreachable_nodes() -> None:
    report = analyze_trajectory(
        _trajectory(
            ("A",),
            [
                _node("A", children=("B",)),
                _node("B", insights=2),
                _node("ORPHAN", insights=1),  # not reachable from A
            ],
        )
    )
    assert report.reachable_count == 2
    assert report.orphan_count == 1


# --- resolution rate -------------------------------------------------------


def test_resolution_rate_mixed_leaves() -> None:
    # 2 resolved leaves, 1 unresolved -> 2/3
    report = analyze_trajectory(
        _trajectory(
            ("A",),
            [
                _node("A", children=("B", "C", "D")),
                _node("B", insights=3, questions=0),  # resolved
                _node("C", insights=2, questions=1),  # resolved (ratio 0.67)
                _node("D", insights=0, questions=5),  # unresolved (ratio 0.0)
            ],
        )
    )
    assert report.leaf_count == 3
    assert report.resolution_rate == pytest.approx(2 / 3)


def test_custom_resolution_threshold() -> None:
    # Leaf with ratio 0.3 (3 insights, 7 questions). Default 0.25 -> resolved.
    # Strict 0.5 -> unresolved.
    inp = _trajectory(
        ("A",),
        [
            _node("A", children=("B",)),
            _node("B", insights=3, questions=7),  # ratio 0.3
        ],
    )
    assert analyze_trajectory(inp).resolution_rate == pytest.approx(1.0)
    assert analyze_trajectory(inp, resolution_threshold=0.5).resolution_rate == pytest.approx(0.0)


# --- multiple roots --------------------------------------------------------


def test_multiple_roots_both_reachable() -> None:
    report = analyze_trajectory(
        _trajectory(
            ("A", "X"),
            [
                _node("A", children=("B",)),
                _node("B", insights=2),
                _node("X", children=("Y",)),
                _node("Y", insights=3),
            ],
        )
    )
    assert report.root_count == 2
    assert report.reachable_count == 4
    assert report.max_depth == 2


# --- provenance / purity ---------------------------------------------------


def test_authority_is_always_advisory() -> None:
    report = analyze_trajectory(_trajectory(("A",), [_node("A")]))
    assert report.authority == "advisory"


def test_report_is_immutable() -> None:
    report = analyze_trajectory(_trajectory(("A",), [_node("A")]))
    assert isinstance(report, TrajectoryReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.max_depth = 99  # type: ignore[misc]


def test_node_is_immutable() -> None:
    n = _node("A")
    assert isinstance(n, InvestigationNode)
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.insight_count = 5  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    inp = _trajectory(("A",), [_node("A", children=("B",)), _node("B", insights=2)])
    assert analyze_trajectory(inp) == analyze_trajectory(inp)


def test_notes_describe_verdict() -> None:
    report = analyze_trajectory(_trajectory(("A",), [_node("A")]))
    joined = " | ".join(report.notes).lower()
    assert "descriptive" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(TrajectoryError, match="resolution_threshold"):
        analyze_trajectory(
            _trajectory(("A",), [_node("A")]), resolution_threshold=bad
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import trajectory as mod

    assert set(mod.__all__) == {
        "InvestigationNode",
        "TrajectoryError",
        "TrajectoryInputs",
        "TrajectoryReport",
        "analyze_trajectory",
    }
    assert issubclass(mod.TrajectoryError, ValueError)
    assert dataclasses.is_dataclass(mod.InvestigationNode)
    assert dataclasses.is_dataclass(mod.TrajectoryInputs)
    assert dataclasses.is_dataclass(mod.TrajectoryReport)

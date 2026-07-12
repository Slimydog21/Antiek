"""Tests for the research-yield (insight/question balance) axis.

Exercises the load-bearing invariants: the yield ratio, the empty-artifact None
defer, the four descriptive verdicts, custom thresholds, validation, and
purity/immutability/determinism.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.research_yield import (
    ResearchYieldError,
    ResearchYieldReport,
    measure_research_yield,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    insights: int,
    questions: int,
    *,
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[ArtifactInsight(node_id=f"i{k}", text=f"insight {k}") for k in range(insights)],
        open_questions=[ArtifactQuestion(node_id=f"q{k}", text=f"question {k}") for k in range(questions)],
    )


# --- core ratio -----------------------------------------------------------


def test_delivery_heavy() -> None:
    # 3 insights, 1 question -> ratio 0.75 >= 0.75 -> delivery_heavy
    report = measure_research_yield(_artifact(3, 1))
    assert report.insight_count == 3
    assert report.open_question_count == 1
    assert report.informational_mass == 4
    assert report.yield_ratio == pytest.approx(0.75)
    assert report.verdict == "delivery_heavy"


def test_recursion_heavy() -> None:
    # 1 insight, 3 questions -> ratio 0.25 -> NOT < 0.25 (boundary). Use 1/5.
    report = measure_research_yield(_artifact(1, 4))
    assert report.yield_ratio == pytest.approx(0.2)
    assert report.verdict == "recursion_heavy"


def test_balanced() -> None:
    # 2 insights, 2 questions -> ratio 0.5 -> balanced
    report = measure_research_yield(_artifact(2, 2))
    assert report.yield_ratio == pytest.approx(0.5)
    assert report.verdict == "balanced"


def test_all_insights_yields_one() -> None:
    report = measure_research_yield(_artifact(5, 0))
    assert report.yield_ratio == pytest.approx(1.0)
    assert report.verdict == "delivery_heavy"


def test_all_questions_yields_zero() -> None:
    report = measure_research_yield(_artifact(0, 5))
    assert report.yield_ratio == pytest.approx(0.0)
    assert report.verdict == "recursion_heavy"


def test_ratio_in_unit_interval() -> None:
    for ii in range(6):
        for qq in range(6):
            if ii + qq == 0:
                continue
            r = measure_research_yield(_artifact(ii, qq)).yield_ratio
            assert r is not None and 0.0 <= r <= 1.0


# --- honesty rules: empty artifact ----------------------------------------


def test_empty_artifact_yields_none() -> None:
    report = measure_research_yield(_artifact(0, 0))
    assert report.informational_mass == 0
    assert report.yield_ratio is None
    assert report.verdict == "unknown"
    assert any("not measurable" in n for n in report.notes)


# --- verdict bands & boundaries -------------------------------------------


def test_boundary_at_delivery_threshold_is_delivery_heavy() -> None:
    # ratio exactly 0.75 (3/4) -> delivery_heavy (>= threshold inclusive)
    assert measure_research_yield(_artifact(3, 1)).verdict == "delivery_heavy"


def test_just_below_delivery_threshold_is_balanced() -> None:
    # 2/3 ~= 0.667 < 0.75 and >= 0.25 -> balanced
    assert measure_research_yield(_artifact(2, 1)).verdict == "balanced"


def test_just_above_recursion_threshold_is_balanced() -> None:
    # 1/4 = 0.25 -> NOT < 0.25, and < 0.75 -> balanced (boundary inclusive on low side)
    assert measure_research_yield(_artifact(1, 3)).verdict == "balanced"


def test_custom_thresholds_change_bands() -> None:
    # 2/2 = 0.5. Default balanced; with delivery=0.5 -> delivery_heavy.
    assert measure_research_yield(_artifact(2, 2)).verdict == "balanced"
    assert (
        measure_research_yield(_artifact(2, 2), delivery_threshold=0.5).verdict
        == "delivery_heavy"
    )
    # With recursion=0.6 (> 0.5 ratio), 0.5 < 0.6 -> recursion_heavy
    assert (
        measure_research_yield(
            _artifact(2, 2), delivery_threshold=0.9, recursion_threshold=0.6
        ).verdict
        == "recursion_heavy"
    )


# --- escalated questions count as open ------------------------------------


def test_escalated_questions_count_as_open() -> None:
    art = ResearchArtifactBody(
        investigation_id="inv-test",
        problem_question="the question",
        insights=[ArtifactInsight(node_id="i0", text="insight")],
        open_questions=[
            ArtifactQuestion(node_id="q0", text="q", escalated=True, reserved_child_investigation_id="child-1"),
            ArtifactQuestion(node_id="q1", text="q"),
        ],
    )
    report = measure_research_yield(art)
    assert report.open_question_count == 2  # escalated still counts as open
    assert report.yield_ratio == pytest.approx(1 / 3)


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    art = _artifact(1, 1, investigation_id="inv-777")
    assert measure_research_yield(art).artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    assert measure_research_yield(_artifact(1, 1)).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_research_yield(_artifact(1, 1))
    assert isinstance(report, ResearchYieldReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.yield_ratio = 0.0  # type: ignore[misc]


def test_determinism_same_artifact_same_report() -> None:
    art = _artifact(3, 2)
    assert measure_research_yield(art) == measure_research_yield(art)


def test_notes_describe_findings() -> None:
    report = measure_research_yield(_artifact(1, 4))
    joined = " | ".join(report.notes)
    assert "structural" in joined.lower()
    assert "yield ratio 20%" in joined.lower()
    assert "recursion_heavy" in joined.lower()


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_delivery_threshold(bad: float) -> None:
    with pytest.raises(ResearchYieldError, match="delivery_threshold"):
        measure_research_yield(_artifact(1, 1), delivery_threshold=bad)


@pytest.mark.parametrize("bad", [0.0, -0.1, 0.75, 1.0])
def test_validation_rejects_bad_recursion_threshold(bad: float) -> None:
    # 0.0 rejected (recursion band must stay reachable); >= delivery(0.75) rejected.
    with pytest.raises(ResearchYieldError, match="recursion_threshold"):
        measure_research_yield(_artifact(1, 1), recursion_threshold=bad)


def test_validation_recursion_must_be_below_delivery() -> None:
    with pytest.raises(ResearchYieldError, match="recursion_threshold"):
        measure_research_yield(_artifact(1, 1), delivery_threshold=0.5, recursion_threshold=0.5)


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import research_yield as mod

    assert set(mod.__all__) == {
        "ResearchYieldError",
        "ResearchYieldReport",
        "measure_research_yield",
    }
    assert issubclass(mod.ResearchYieldError, ValueError)
    assert dataclasses.is_dataclass(mod.ResearchYieldReport)

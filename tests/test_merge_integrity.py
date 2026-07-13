"""Tests for the merge-integrity axis (did the merge preserve its parents? asks #2/#3).

Exercises: preserved/insight_loss/question_loss/loss/unknown per-parent verdicts,
parent_loss/preserved/unknown overall, survival rates + means + weakest parent,
informational orphan ratio, subset survival (overlap-coefficient), custom threshold,
all-glue exclusion, purity/immutability, validation. Fixtures use BARE NONSENSE TOKENS.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.merge_integrity import (
    MergeIntegrityError,
    ParentCoverage,
    measure_merge_integrity,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    *,
    investigation_id: str,
    insights: list[str] | None = None,
    questions: list[str] | None = None,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the problem",
        insights=[
            ArtifactInsight(node_id=f"{investigation_id}-i{k}", text=t)
            for k, t in enumerate(insights or [])
        ],
        open_questions=[
            ArtifactQuestion(
                node_id=f"{investigation_id}-q{k}", text=t, escalated=False
            )
            for k, t in enumerate(questions or [])
        ],
    )


# --- perfect preservation -------------------------------------------------


def test_perfect_preservation_two_parents() -> None:
    parent_a = _artifact(
        investigation_id="a", insights=["alpha beta", "gamma delta"], questions=["epsilon zeta"]
    )
    parent_b = _artifact(investigation_id="b", insights=["eta theta"])
    merged = _artifact(
        investigation_id="m",
        insights=["alpha beta", "gamma delta", "eta theta"],
        questions=["epsilon zeta"],
    )

    report = measure_merge_integrity([parent_a, parent_b], merged)

    assert report.verdict == "preserved"
    assert report.authority == "advisory"
    assert report.merged_id == "m"
    assert len(report.parent_coverages) == 2
    by_id = {c.parent_id: c for c in report.parent_coverages}
    assert by_id["a"].insight_survival == 1.0
    assert by_id["a"].question_survival == 1.0
    assert by_id["a"].verdict == "preserved"
    assert by_id["b"].insight_survival == 1.0
    assert by_id["b"].question_survival is None  # parent b had no questions
    assert by_id["b"].verdict == "preserved"
    assert report.mean_insight_survival == 1.0
    assert report.mean_question_survival == 1.0
    assert report.orphan_insight_ratio == 0.0
    assert report.orphan_insight_count == 0


# --- insight loss ---------------------------------------------------------


def test_insight_loss_below_threshold() -> None:
    parent = _artifact(
        investigation_id="a",
        insights=["alpha beta", "gamma delta", "epsilon zeta"],
    )
    merged = _artifact(investigation_id="m", insights=["alpha beta"])

    report = measure_merge_integrity([parent], merged)

    cov = report.parent_coverages[0]
    assert cov.insight_survival == pytest.approx(1 / 3)  # 1 of 3 survived
    assert cov.verdict == "insight_loss"
    assert cov.survived_insights == 1
    assert cov.measurable_insights == 3
    assert report.verdict == "parent_loss"


# --- question loss --------------------------------------------------------


def test_question_loss_below_threshold() -> None:
    parent = _artifact(
        investigation_id="a",
        questions=["alpha beta", "gamma delta", "epsilon zeta"],
    )
    merged = _artifact(investigation_id="m", questions=["alpha beta"])

    report = measure_merge_integrity([parent], merged)

    cov = report.parent_coverages[0]
    assert cov.insight_survival is None  # parent had no insights
    assert cov.question_survival == pytest.approx(1 / 3)
    assert cov.verdict == "question_loss"
    assert report.verdict == "parent_loss"


# --- both lost -> "loss" --------------------------------------------------


def test_both_insight_and_question_loss() -> None:
    parent = _artifact(
        investigation_id="a",
        insights=["alpha beta", "gamma delta", "epsilon zeta"],
        questions=["eta theta", "iota kappa", "mu nu"],
    )
    merged = _artifact(
        investigation_id="m", insights=["alpha beta"], questions=["eta theta"]
    )

    report = measure_merge_integrity([parent], merged)

    cov = report.parent_coverages[0]
    assert cov.insight_survival == pytest.approx(1 / 3)
    assert cov.question_survival == pytest.approx(1 / 3)
    assert cov.verdict == "loss"
    assert report.verdict == "parent_loss"


# --- subset survival (overlap-coefficient design choice) ------------------


def test_short_parent_insight_survives_as_subset() -> None:
    # parent insight {alpha, beta} (2 tokens) is a SUBSET of a richer merged
    # insight {alpha, beta, gamma, delta, epsilon} (5 tokens): overlap-coeff =
    # |{alpha,beta}| / min(2,5) = 2/2 = 1.0 -> survived (not penalised for the
    # merge's added context, which a Jaccard score would wrongly punish).
    parent = _artifact(investigation_id="a", insights=["alpha beta"])
    merged = _artifact(
        investigation_id="m", insights=["alpha beta gamma delta epsilon"]
    )

    report = measure_merge_integrity([parent], merged)

    assert report.parent_coverages[0].insight_survival == 1.0
    assert report.verdict == "preserved"


# --- informational orphan ratio (NOT a verdict input) ---------------------


def test_orphan_ratio_is_informational_not_verdict() -> None:
    # merged carries the parent's insight PLUS a novel synthesis insight; the
    # novel content matches no parent -> orphan, but the parent was fully
    # preserved, so the verdict stays "preserved" (novel = synthesis, not
    # fabrication).
    parent = _artifact(investigation_id="a", insights=["alpha beta"])
    merged = _artifact(
        investigation_id="m", insights=["alpha beta", "gamma delta"]
    )

    report = measure_merge_integrity([parent], merged)

    assert report.parent_coverages[0].verdict == "preserved"
    assert report.verdict == "preserved"
    assert report.orphan_insight_count == 1
    assert report.orphan_insight_ratio == 0.5
    assert report.measurable_merge_insights == 2


# --- all-glue / unmeasurable ---------------------------------------------


def test_all_glue_parent_is_unknown() -> None:
    # every item is glue -> zero distinctive terms -> unmeasurable -> None
    parent = _artifact(
        investigation_id="a",
        insights=["the and of"],
        questions=["is was be"],
    )
    merged = _artifact(investigation_id="m", insights=["alpha beta"])

    report = measure_merge_integrity([parent], merged)

    cov = report.parent_coverages[0]
    assert cov.insight_survival is None
    assert cov.question_survival is None
    assert cov.unmeasurable_insights == 1
    assert cov.unmeasurable_questions == 1
    assert cov.verdict == "unknown"
    assert report.verdict == "unknown"


def test_glue_items_excluded_from_ratio() -> None:
    # one measurable + one all-glue insight; only the measurable one counts.
    parent = _artifact(
        investigation_id="a", insights=["alpha beta", "the and of"]
    )
    merged = _artifact(investigation_id="m", insights=["alpha beta"])

    report = measure_merge_integrity([parent], merged)

    cov = report.parent_coverages[0]
    assert cov.measurable_insights == 1
    assert cov.unmeasurable_insights == 1
    assert cov.insight_survival == 1.0  # 1 of 1 measurable survived
    assert cov.verdict == "preserved"


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    # "alpha beta gamma" vs "alpha beta zeta": overlap-coeff = |{alpha,beta}| /
    # min(3,3) = 2/3 ~= 0.667.
    parent = _artifact(investigation_id="a", insights=["alpha beta gamma"])
    merged = _artifact(investigation_id="m", insights=["alpha beta zeta"])

    loose = measure_merge_integrity([parent], merged, survival_threshold=0.50)
    assert loose.parent_coverages[0].insight_survival == 1.0
    assert loose.verdict == "preserved"

    strict = measure_merge_integrity([parent], merged, survival_threshold=0.70)
    assert strict.parent_coverages[0].insight_survival == 0.0
    assert strict.verdict == "parent_loss"


# --- weakest parent -------------------------------------------------------


def test_weakest_parent_identified() -> None:
    # parent a fully preserved; parent b gutted -> b is the weakest.
    parent_a = _artifact(investigation_id="a", insights=["alpha beta"])
    parent_b = _artifact(
        investigation_id="b", insights=["gamma delta", "epsilon zeta", "eta theta"]
    )
    merged = _artifact(investigation_id="m", insights=["alpha beta", "gamma delta"])

    report = measure_merge_integrity([parent_a, parent_b], merged)

    assert report.verdict == "parent_loss"
    assert report.weakest_parent_id == "b"
    # parent b: "gamma delta" survived (1), "epsilon zeta"/"eta theta" did not.
    by_id = {c.parent_id: c for c in report.parent_coverages}
    assert by_id["b"].survived_insights == 1
    assert by_id["b"].insight_survival == pytest.approx(1 / 3)


# --- validation -----------------------------------------------------------


def test_empty_parents_raises() -> None:
    merged = _artifact(investigation_id="m", insights=["alpha beta"])
    with pytest.raises(MergeIntegrityError, match="at least one parent"):
        measure_merge_integrity([], merged)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_threshold_raises(bad: float) -> None:
    parent = _artifact(investigation_id="a", insights=["alpha beta"])
    merged = _artifact(investigation_id="m", insights=["alpha beta"])
    with pytest.raises(MergeIntegrityError, match="survival_threshold"):
        measure_merge_integrity([parent], merged, survival_threshold=bad)


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_pure() -> None:
    parent = _artifact(investigation_id="a", insights=["alpha beta"])
    merged = _artifact(investigation_id="m", insights=["alpha beta"])

    report = measure_merge_integrity([parent], merged)

    assert dataclasses.is_dataclass(report)
    assert isinstance(report.parent_coverages, tuple)
    assert all(isinstance(c, ParentCoverage) for c in report.parent_coverages)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.parent_coverages[0].verdict = "tampered"  # type: ignore[misc]
    # deterministic: same inputs -> identical report
    again = measure_merge_integrity([parent], merged)
    assert again == report


def test_notes_are_non_empty_and_auditable() -> None:
    parent = _artifact(investigation_id="a", insights=["alpha beta"])
    merged = _artifact(investigation_id="m", insights=["alpha beta"])
    report = measure_merge_integrity([parent], merged)
    assert isinstance(report.notes, tuple)
    assert len(report.notes) >= 5
    assert all(isinstance(n, str) and n for n in report.notes)

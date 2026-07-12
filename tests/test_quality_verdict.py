"""Tests for substrate.deep_research_quality.quality_verdict — the composite gate."""

from __future__ import annotations

import math

import pytest

from substrate.deep_research_quality.quality_verdict import (
    AxisContribution,
    DRQualityVerdict,
    QualityVerdictError,
    compose_quality_verdict,
)


def _contrib(axis: str, score: float | None = None, fatal: bool = False, reason: str = "") -> AxisContribution:
    return AxisContribution(axis=axis, score=score, fatal=fatal, reason=reason)


# --- the fatal gate: the keystone the blind mean cannot express -----------


def test_fatal_axis_drops_to_floor_regardless_of_soft_scores() -> None:
    """A perfectly-scored artifact with a FABRICATED citation is indefensible."""
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[
            _contrib("rubric", 0.95),
            _contrib("source_diversity", 0.90),
            _contrib("problem_question_coverage", 1.0),
            _contrib("citation_grounding", fatal=True, reason="fabricated citation"),
        ],
    )
    assert verdict.gated is True
    assert verdict.overall_score == 0.0
    assert verdict.verdict == "indefensible"
    assert verdict.binding_axis == "citation_grounding"
    assert any("FATAL" in n for n in verdict.notes)


def test_fatal_dominates_even_when_only_axis() -> None:
    """A lone fatal axis is still decisive."""
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("grounding", fatal=True)],
    )
    assert verdict.verdict == "indefensible"
    assert verdict.overall_score == 0.0


def test_first_fatal_is_binding_when_multiple() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[
            _contrib("a", fatal=True),
            _contrib("b", fatal=True),
        ],
    )
    assert verdict.binding_axis == "a"  # first-seen
    assert any("b" in n for n in verdict.notes)  # additional fatal surfaced


# --- soft combination: weighted mean of measured only --------------------


def test_weighted_mean_of_measured_scores() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("rubric", 0.8), _contrib("diversity", 0.6)],
    )
    assert verdict.overall_score == pytest.approx(0.7)  # unweighted mean
    assert verdict.verdict == "defensible_with_gaps"  # 0.7 < 0.80


def test_equal_weights_by_default() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 1.0), _contrib("b", 0.5), _contrib("c", 0.5)],
    )
    assert verdict.overall_score == pytest.approx(2.0 / 3.0)


def test_custom_weights_emphasize_an_axis() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("rubric", 0.6), _contrib("coverage", 1.0)],
        weights={"rubric": 3.0, "coverage": 1.0},
    )
    # (0.6*3 + 1.0*1) / 4 = 2.8/4 = 0.7
    assert verdict.overall_score == pytest.approx(0.7)


# --- orthogonality: unknowns excluded, never fabricated ------------------


def test_unmeasured_axis_excluded_from_mean_not_penalized() -> None:
    """A None-scored axis is excluded, not coerced to 0."""
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("rubric", 0.9), _contrib("diversity", None)],
    )
    assert verdict.overall_score == pytest.approx(0.9)  # not (0.9+0)/2 = 0.45
    assert verdict.measured_axis_count == 1
    assert any("unmeasured" in n for n in verdict.notes)


def test_all_unmeasured_is_partial_not_affirmed() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", None), _contrib("b", None)],
    )
    assert verdict.overall_score == 0.0
    assert verdict.measured_axis_count == 0
    assert verdict.binding_axis is None
    assert verdict.verdict == "defensible_with_gaps"
    assert any("unproven" in n for n in verdict.notes)


# --- graduated verdicts ----------------------------------------------------


def test_defensible_when_all_measured_above_threshold() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 0.90), _contrib("b", 0.90)],
        defensible_threshold=0.80,
    )
    assert verdict.verdict == "defensible"
    assert verdict.measured_axis_count == 2


def test_below_threshold_is_defensible_with_gaps() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 0.60), _contrib("b", 0.60)],
        defensible_threshold=0.80,
    )
    assert verdict.verdict == "defensible_with_gaps"


def test_above_threshold_but_unmeasured_is_still_gaps() -> None:
    """Defensible requires BOTH above-threshold AND all-measured."""
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 1.0), _contrib("b", None)],
        defensible_threshold=0.80,
    )
    assert verdict.overall_score == 1.0
    assert verdict.verdict == "defensible_with_gaps"  # b unmeasured => partial


def test_configurable_threshold() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 0.75), _contrib("b", 0.75)],
        defensible_threshold=0.70,
    )
    assert verdict.verdict == "defensible"


# --- binding axis: the constraint to fix first ----------------------------


def test_binding_axis_is_lowest_measured_soft() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("rubric", 0.9), _contrib("coverage", 0.4)],
    )
    assert verdict.binding_axis == "coverage"  # lowest
    assert any("binding axis" in n for n in verdict.notes)


def test_binding_axis_first_seen_on_tie() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 0.5), _contrib("b", 0.5), _contrib("c", 0.9)],
    )
    assert verdict.binding_axis == "a"  # first-seen tie-break


def test_binding_axis_never_an_unmeasured_axis() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1",
        contributions=[_contrib("a", 0.9), _contrib("b", None), _contrib("c", 0.3)],
    )
    assert verdict.binding_axis == "c"  # measured lowest, not the None one


# --- honesty: pure, deterministic, advisory, auditable -------------------


def test_pure_and_idempotent() -> None:
    contribs = [_contrib("a", 0.8), _contrib("b", 0.6)]
    first = compose_quality_verdict(investigation_id="inv-1", contributions=contribs)
    second = compose_quality_verdict(investigation_id="inv-1", contributions=contribs)
    assert first == second


def test_authority_is_advisory() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1", contributions=[_contrib("a", 0.9)]
    )
    assert verdict.authority == "advisory"


def test_contributions_carried_through_auditable() -> None:
    contribs = [_contrib("a", 0.8, reason="high"), _contrib("b", fatal=True, reason="bad")]
    verdict = compose_quality_verdict(investigation_id="inv-1", contributions=contribs)
    assert verdict.contributions == tuple(contribs)


def test_report_is_frozen_value() -> None:
    verdict = compose_quality_verdict(
        investigation_id="inv-1", contributions=[_contrib("a", 0.9)]
    )
    assert isinstance(verdict, DRQualityVerdict)
    with pytest.raises((AttributeError, Exception)):
        verdict.overall_score = 0.5  # type: ignore[misc]


def test_overall_score_in_unit_interval() -> None:
    """overall_score is always a finite float in [0, 1]."""
    cases = [
        [_contrib("a", fatal=True)],  # gated
        [_contrib("a", None)],  # unmeasured
        [_contrib("a", 1.0), _contrib("b", 1.0)],  # max
        [_contrib("a", 0.0)],  # min measured
    ]
    for contribs in cases:
        verdict = compose_quality_verdict(investigation_id="inv-1", contributions=contribs)
        assert isinstance(verdict.overall_score, float)
        assert math.isfinite(verdict.overall_score)
        assert 0.0 <= verdict.overall_score <= 1.0


# --- input validation -----------------------------------------------------


def test_empty_investigation_id_rejected() -> None:
    with pytest.raises(QualityVerdictError, match="investigation_id"):
        compose_quality_verdict(investigation_id="  ", contributions=[_contrib("a", 0.5)])


def test_no_contributions_rejected() -> None:
    with pytest.raises(QualityVerdictError, match="at least one"):
        compose_quality_verdict(investigation_id="inv-1", contributions=[])


def test_duplicate_axis_rejected() -> None:
    with pytest.raises(QualityVerdictError, match="duplicate"):
        compose_quality_verdict(
            investigation_id="inv-1",
            contributions=[_contrib("rubric", 0.5), _contrib("rubric", 0.6)],
        )


def test_empty_axis_name_rejected() -> None:
    with pytest.raises(QualityVerdictError, match="non-empty axis"):
        compose_quality_verdict(investigation_id="inv-1", contributions=[_contrib("  ", 0.5)])


@pytest.mark.parametrize("bad", [1.5, -0.1, float("nan")])
def test_out_of_range_score_rejected(bad: float) -> None:
    with pytest.raises(QualityVerdictError, match="0, 1"):
        compose_quality_verdict(investigation_id="inv-1", contributions=[_contrib("a", bad)])


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1])
def test_bad_threshold_rejected(bad: float) -> None:
    with pytest.raises(QualityVerdictError, match="defensible_threshold"):
        compose_quality_verdict(
            investigation_id="inv-1", contributions=[_contrib("a", 0.5)], defensible_threshold=bad
        )


def test_negative_weight_rejected() -> None:
    with pytest.raises(QualityVerdictError, match="weight"):
        compose_quality_verdict(
            investigation_id="inv-1",
            contributions=[_contrib("a", 0.5)],
            weights={"a": -1.0},
        )

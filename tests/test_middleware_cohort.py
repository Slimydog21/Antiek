"""Tests for middleware/cohort/ (Sprint 5 day 2-3).

Coverage:

1. Empty cohort returns the right zero-shape.
2. Insufficient-power warning fires below
   ``COHORT_MIN_OBSERVED_INVESTIGATIONS``.
3. Thesis accuracy buckets stratify by ``thesis.thesis_components[].
   confidence`` and the calibration band check works.
4. Falsification specificity counts non-empty
   ``specific_observable`` across ALL cohort syntheses (not just those
   with outcomes).
5. Risk completeness rate accounts for manifested-only with risk-list
   intersection.
6. Decision-outcome alignment scoring respects the weighted
   thesis_outcome_when_proceeded grade.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.cohort import (  # noqa: E402
    CohortOutcomeRow,
    CohortSynthesisRow,
    analyze,
)
from substrate.constants import (  # noqa: E402
    COHORT_MIN_OBSERVED_INVESTIGATIONS,
    CONFIDENCE_CALIBRATION_TARGETS,
)


def _syn(sid: str, *, components=None, falsifiers=None, risks=None,
         rec="conditional") -> CohortSynthesisRow:
    return CohortSynthesisRow(
        synthesis_id=sid,
        synthesis_timestamp="2026-01-01T00:00:00Z",
        target_question="q",
        status="passed",
        thesis={
            "thesis_components": components or [],
            "falsification_conditions": falsifiers or [],
            "execution_risks": risks or [],
        },
        implicit_recommendation=rec,
    )


def _obs(sid: str, *, thesis=None, falsif=None, risks=None,
         decision=None) -> CohortOutcomeRow:
    return CohortOutcomeRow(
        synthesis_id=sid,
        thesis_outcomes=thesis or [],
        falsification_outcomes=falsif or [],
        execution_risk_outcomes=risks or [],
        decision_alignment=decision,
    )


# ---------------------------------------------------------------------------
# 1. Empty cohort
# ---------------------------------------------------------------------------


def test_analyze_empty_cohort_returns_zero_shape():
    out = analyze([], {})
    assert out["cohort_size"]["total_syntheses"] == 0
    assert out["cohort_size"]["with_observed_outcomes"] == 0
    assert out["insufficient_power"] is True
    assert out["falsification_specificity"]["rate"] is None
    assert out["risk_completeness"]["rate"] is None
    assert out["decision_alignment"]["alignment_rate"] is None
    # Every confidence bucket present, all zero
    for conf in ("high", "moderate", "low", "unknown"):
        bucket = out["thesis_accuracy_by_confidence"][conf]
        assert bucket["total"] == 0
        assert bucket["confirmation_rate"] is None


# ---------------------------------------------------------------------------
# 2. Insufficient-power warning
# ---------------------------------------------------------------------------


def test_insufficient_power_fires_below_min():
    cohort = [_syn(f"s-{i}") for i in range(2)]
    outcomes = {c.synthesis_id: [_obs(c.synthesis_id)] for c in cohort}
    out = analyze(cohort, outcomes)
    assert out["insufficient_power"] is True
    assert COHORT_MIN_OBSERVED_INVESTIGATIONS in (
        out["cohort_size"]["min_for_power"], 30,
    )
    assert "Numbers below are diagnostic" in out["power_warning"]


def test_sufficient_power_suppresses_warning():
    n = COHORT_MIN_OBSERVED_INVESTIGATIONS
    cohort = [_syn(f"s-{i}") for i in range(n)]
    outcomes = {c.synthesis_id: [_obs(c.synthesis_id)] for c in cohort}
    out = analyze(cohort, outcomes)
    assert out["insufficient_power"] is False
    assert out["power_warning"] is None


# ---------------------------------------------------------------------------
# 3. Thesis accuracy buckets + calibration band
# ---------------------------------------------------------------------------


def test_thesis_accuracy_stratifies_by_confidence():
    syn = _syn(
        "s-1",
        components=[
            {"claim": "C1", "confidence": "high"},
            {"claim": "C2", "confidence": "low"},
        ],
    )
    obs = _obs("s-1", thesis=[
        {"thesis_claim": "C1", "outcome": "confirmed"},
        {"thesis_claim": "C2", "outcome": "disconfirmed"},
    ])
    out = analyze([syn], {"s-1": [obs]})
    high = out["thesis_accuracy_by_confidence"]["high"]
    low = out["thesis_accuracy_by_confidence"]["low"]
    assert high["total"] == 1 and high["confirmed"] == 1
    assert high["confirmation_rate"] == 1.0
    assert low["total"] == 1 and low["disconfirmed"] == 1
    assert low["confirmation_rate"] == 0.0


def test_calibration_in_band_true_when_rate_inside_target():
    band = CONFIDENCE_CALIBRATION_TARGETS["high"]
    # Make 10 high-confidence claims, all confirmed → rate 1.0, inside (.85, 1.0)
    components = [{"claim": f"C{i}", "confidence": "high"} for i in range(10)]
    syn = _syn("s-1", components=components)
    obs = _obs("s-1", thesis=[
        {"thesis_claim": f"C{i}", "outcome": "confirmed"} for i in range(10)
    ])
    out = analyze([syn], {"s-1": [obs]})
    high = out["thesis_accuracy_by_confidence"]["high"]
    assert high["target_band"] == band
    assert high["in_target_band"] is True


def test_calibration_in_band_false_when_high_confidence_underperforms():
    components = [{"claim": f"C{i}", "confidence": "high"} for i in range(10)]
    syn = _syn("s-1", components=components)
    # Only 5/10 confirmed → 0.5, below the (.85, 1.0) high-confidence band.
    obs_outcomes = [
        {"thesis_claim": f"C{i}",
         "outcome": "confirmed" if i < 5 else "disconfirmed"}
        for i in range(10)
    ]
    out = analyze([syn], {"s-1": [_obs("s-1", thesis=obs_outcomes)]})
    high = out["thesis_accuracy_by_confidence"]["high"]
    assert high["in_target_band"] is False


def test_unknown_confidence_assigned_when_claim_missing_from_thesis():
    """An outcome whose thesis_claim doesn't match any thesis_component
    is bucketed under 'unknown' rather than silently dropped."""
    syn = _syn("s-1", components=[{"claim": "real", "confidence": "high"}])
    obs = _obs("s-1", thesis=[
        {"thesis_claim": "real", "outcome": "confirmed"},
        {"thesis_claim": "ghost", "outcome": "disconfirmed"},
    ])
    out = analyze([syn], {"s-1": [obs]})
    assert out["thesis_accuracy_by_confidence"]["unknown"]["total"] == 1


# ---------------------------------------------------------------------------
# 4. Falsification specificity
# ---------------------------------------------------------------------------


def test_falsification_specificity_counts_across_all_syntheses():
    """Counted across the WHOLE cohort, not just observed-outcome syntheses
    — a synthesis can be evaluated on its falsifier specificity without
    waiting for outcomes to be recorded."""
    cohort = [
        _syn("s-1", falsifiers=[
            {"condition": "ARR<50%", "specific_observable": "Q3 letter ARR"},
            {"condition": "vague", "specific_observable": ""},
        ]),
        _syn("s-2", falsifiers=[
            {"condition": "churn>10%", "specific_observable": "billing report"},
        ]),
    ]
    out = analyze(cohort, {})  # no outcomes — specificity still computes
    fs = out["falsification_specificity"]
    assert fs["total"] == 3
    assert fs["specific"] == 2
    assert fs["rate"] == round(2 / 3, 3)


# ---------------------------------------------------------------------------
# 5. Risk completeness
# ---------------------------------------------------------------------------


def test_risk_completeness_only_counts_manifested():
    syn = _syn("s-1", risks=[{"risk": "Talent flight"}, {"risk": "Regulation"}])
    obs = _obs("s-1", risks=[
        {"risk": "talent flight", "manifested": True},   # anticipated
        {"risk": "competitor", "manifested": True},      # not anticipated
        {"risk": "regulation", "manifested": False},     # didn't manifest, ignored
    ])
    out = analyze([syn], {"s-1": [obs]})
    rc = out["risk_completeness"]
    assert rc["manifested"] == 2
    assert rc["anticipated"] == 1
    assert rc["rate"] == 0.5


def test_risk_completeness_case_insensitive_match():
    """The agent's enumerated risks may use sentence case, observers
    may use lowercase. Match is case-insensitive + strip-trimmed."""
    syn = _syn("s-1", risks=[{"risk": "  Talent Flight  "}])
    obs = _obs("s-1", risks=[
        {"risk": "talent flight", "manifested": True},
    ])
    out = analyze([syn], {"s-1": [obs]})
    assert out["risk_completeness"]["rate"] == 1.0


# ---------------------------------------------------------------------------
# 6. Decision-outcome alignment scoring
# ---------------------------------------------------------------------------


def test_alignment_rate_counts_matching_pairs():
    syn1 = _syn("s-1")
    syn2 = _syn("s-2")
    out = analyze(
        [syn1, syn2],
        {
            "s-1": [_obs("s-1", decision={
                "agent_implicit_recommendation": "proceed",
                "actual_decision": "proceed",
                "thesis_outcome_when_proceeded": "confirmed",
            })],
            "s-2": [_obs("s-2", decision={
                "agent_implicit_recommendation": "proceed",
                "actual_decision": "pass",
            })],
        },
    )
    da = out["decision_alignment"]
    assert da["aligned_total"] == 2
    assert da["aligned_pairs"] == 1
    assert da["alignment_rate"] == 0.5


def test_proceed_confirmation_score_weighted():
    """confirmed=1.0, partially_confirmed=0.5, disconfirmed=0.0,
    not_observed=0.0. Mix of all four should produce the weighted
    mean across the aligned-proceed denominator."""
    cohort = [_syn(f"s-{i}") for i in range(4)]
    grades = ["confirmed", "partially_confirmed", "disconfirmed", "not_observed"]
    outcomes = {}
    for i, grade in enumerate(grades):
        sid = f"s-{i}"
        outcomes[sid] = [_obs(sid, decision={
            "agent_implicit_recommendation": "proceed",
            "actual_decision": "proceed",
            "thesis_outcome_when_proceeded": grade,
        })]
    out = analyze(cohort, outcomes)
    da = out["decision_alignment"]
    assert da["proceed_aligned_total"] == 4
    # (1.0 + 0.5 + 0.0 + 0.0) / 4 == 0.375
    assert da["proceed_confirmation_score"] == 0.375
    assert da["proceed_confirmed_when_aligned"] == 1


def test_unaligned_proceed_does_not_contribute_to_proceed_score():
    """When agent_rec='proceed' but actual_decision='pass', the row
    counts toward aligned_total but NOT toward proceed_total, because
    no 'proceed' actually happened."""
    syn = _syn("s-1")
    obs = _obs("s-1", decision={
        "agent_implicit_recommendation": "proceed",
        "actual_decision": "pass",
        "thesis_outcome_when_proceeded": "not_observed",
    })
    out = analyze([syn], {"s-1": [obs]})
    da = out["decision_alignment"]
    assert da["aligned_total"] == 1
    assert da["aligned_pairs"] == 0
    assert da["proceed_aligned_total"] == 0
    assert da["proceed_confirmation_score"] is None

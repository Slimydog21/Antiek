"""SPR-01 — truthful model evidence: ranking engine tests.

Covers: missing, partial, complete, over-budget, unknown-budget, stale,
malformed, and wrong-route evidence.  A measured pick requires at least
two operationally eligible measured candidates.
"""

from __future__ import annotations

import math

import pytest

from substrate.dispatch.advisory_decision import DecisionCandidate, rank_model_candidates


def _candidate(
    tier: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    ready: bool = True,
    exceed: bool | None = False,
    score: float | None = None,
) -> DecisionCandidate:
    return DecisionCandidate(
        tier=tier,
        provider=provider or f"provider-{tier}",
        model=model or f"model-{tier}",
        ready=ready,
        estimated_usd_low=0.01,
        estimated_usd_high=0.02,
        would_exceed_budget=exceed,
        benchmark_score=score,
        benchmark_samples=12 if score is not None else None,
    )


# ── No benchmark evidence: no recommendation ────────────────────────────


def test_no_benchmark_yields_no_recommendation() -> None:
    """Without any benchmark report, no measured pick is emitted."""
    result = rank_model_candidates(
        "writing",
        (_candidate("flash"), _candidate("synthesis"), _candidate("pro")),
    )
    assert result.recommended_tier is None
    assert all(row.quality_score is None for row in result.ranked)
    assert all(row.quality_basis == "absent" for row in result.ranked)


def test_all_absent_evidence_is_honestly_null() -> None:
    """Quality scores are null when no benchmark exists — never fabricated."""
    result = rank_model_candidates(
        "deep_research",
        (_candidate("pro"), _candidate("flash")),
    )
    for row in result.ranked:
        assert row.quality_score is None
        assert row.quality_basis == "absent"


# ── Single measured candidate: cannot win alone ─────────────────────────


def test_single_measured_candidate_cannot_win() -> None:
    """One measured route cannot be recommended — measurement availability
    is not comparative superiority."""
    result = rank_model_candidates(
        "writing",
        (_candidate("flash", score=0.96), _candidate("synthesis"), _candidate("pro")),
    )
    assert result.recommended_tier is None
    # The measured candidate sorts first (measured above absent)
    assert result.ranked[0].quality_basis == "measured"
    assert result.ranked[0].quality_score == 0.96


# ── Two eligible measured candidates: higher score wins ─────────────────


def test_two_eligible_measured_candidates_higher_wins() -> None:
    """With ≥2 eligible measured, the higher score wins."""
    result = rank_model_candidates(
        "writing",
        (
            _candidate("flash", score=0.90),
            _candidate("synthesis", score=0.99),
            _candidate("pro"),
        ),
    )
    assert result.recommended_tier == "synthesis"
    assert result.ranked[0].candidate.tier == "synthesis"
    assert result.ranked[0].quality_score == 0.99


def test_two_measured_one_exceeds_budget() -> None:
    """Only operationally eligible (ready + within budget) count."""
    result = rank_model_candidates(
        "writing",
        (
            _candidate("flash", score=0.90),
            _candidate("synthesis", score=0.99, exceed=True),
            _candidate("pro"),
        ),
    )
    # Only flash is eligible measured; synthesis exceeds budget → not counted
    # → only 1 eligible measured → no recommendation
    assert result.recommended_tier is None


def test_two_measured_one_unready() -> None:
    """Unready measured candidate does not count toward the ≥2 threshold."""
    result = rank_model_candidates(
        "writing",
        (
            _candidate("flash", score=0.90),
            _candidate("synthesis", score=0.99, ready=False),
            _candidate("pro"),
        ),
    )
    # Only flash is eligible measured → no recommendation
    assert result.recommended_tier is None


def test_two_eligible_measured_with_one_unmeasured() -> None:
    """Unmeasured routes do not block recommendation when ≥2 are measured."""
    result = rank_model_candidates(
        "writing",
        (
            _candidate("flash", score=0.85),
            _candidate("synthesis", score=0.95),
            _candidate("pro"),  # unmeasured
        ),
    )
    assert result.recommended_tier == "synthesis"


# ── Three eligible measured: highest wins ───────────────────────────────


def test_three_eligible_measured_highest_wins() -> None:
    result = rank_model_candidates(
        "general",
        (
            _candidate("pro", score=0.70),
            _candidate("synthesis", score=0.85),
            _candidate("flash", score=0.60),
        ),
    )
    assert result.recommended_tier == "synthesis"
    assert result.ranked[0].quality_score == 0.85


# ── Eligibility: ready + within budget ──────────────────────────────────


def test_unready_candidates_visible_but_not_eligible() -> None:
    result = rank_model_candidates(
        "deep_research",
        (_candidate("pro", ready=False, score=0.9), _candidate("flash", score=0.8)),
    )
    assert result.recommended_tier is None  # only 1 eligible measured
    assert result.ranked[-1].candidate.tier == "pro"
    assert result.ranked[-1].operationally_eligible is False


def test_unknown_budget_visible_but_not_eligible() -> None:
    result = rank_model_candidates(
        "deep_research",
        (_candidate("pro", exceed=None, score=0.9), _candidate("flash", exceed=True, score=0.8)),
    )
    assert result.recommended_tier is None
    assert all(row.operationally_eligible is False for row in result.ranked)


def test_over_budget_cannot_win() -> None:
    result = rank_model_candidates(
        "general",
        (
            _candidate("pro", score=0.99, exceed=True),
            _candidate("flash", score=0.80),
            _candidate("synthesis", score=0.85),
        ),
    )
    # pro exceeds budget → only flash + synthesis are eligible → ≥2 → synthesis wins
    assert result.recommended_tier == "synthesis"
    assert result.ranked[0].operationally_eligible is True
    # pro should be last (over budget sorts after within budget)
    assert result.ranked[-1].candidate.tier == "pro"
    assert result.ranked[-1].operationally_eligible is False


# ── Sorting: measured above unmeasured ──────────────────────────────────


def test_measured_sort_above_unmeasured() -> None:
    """Measured candidates sort above unmeasured (quality data exists)."""
    result = rank_model_candidates(
        "writing",
        (
            _candidate("pro"),  # unmeasured
            _candidate("flash", score=0.50),
            _candidate("synthesis", score=0.99),
        ),
    )
    # Measured first, then unmeasured
    assert result.ranked[0].quality_basis == "measured"
    assert result.ranked[1].quality_basis == "measured"
    assert result.ranked[2].quality_basis == "absent"


# ── Validation: invalid scores fail closed ──────────────────────────────


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.1])
def test_invalid_benchmark_scores_fail_closed(score: float) -> None:
    with pytest.raises(ValueError, match="benchmark_score"):
        rank_model_candidates("general", (_candidate("pro", score=score),))


def test_zero_benchmark_samples_rejected() -> None:
    candidate = DecisionCandidate(
        tier="pro",
        provider="p",
        model="m",
        ready=True,
        estimated_usd_low=0.01,
        estimated_usd_high=0.02,
        would_exceed_budget=False,
        benchmark_score=0.8,
        benchmark_samples=0,
    )
    with pytest.raises(ValueError, match="benchmark_samples"):
        rank_model_candidates("general", (candidate,))


def test_negative_usd_estimate_fails_closed() -> None:
    candidate = DecisionCandidate(
        tier="pro",
        provider="p",
        model="m",
        ready=True,
        estimated_usd_low=-0.01,
        estimated_usd_high=0.02,
        would_exceed_budget=False,
    )
    with pytest.raises(ValueError, match="estimated_usd_low"):
        rank_model_candidates("general", (candidate,))

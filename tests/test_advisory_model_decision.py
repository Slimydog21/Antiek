from __future__ import annotations

import math

import pytest

from substrate.dispatch.advisory_decision import DecisionCandidate, rank_model_candidates


def _candidate(
    tier: str,
    *,
    ready: bool = True,
    exceed: bool | None = False,
    score: float | None = None,
) -> DecisionCandidate:
    return DecisionCandidate(
        tier=tier,
        provider=f"provider-{tier}",
        model=f"model-{tier}",
        ready=ready,
        estimated_usd_low=0.01,
        estimated_usd_high=0.02,
        would_exceed_budget=exceed,
        benchmark_score=score,
        benchmark_samples=12 if score is not None else None,
    )


def test_static_affinity_recommends_ready_in_budget_task_tier() -> None:
    result = rank_model_candidates(
        "writing",
        (_candidate("flash"), _candidate("synthesis"), _candidate("pro")),
    )
    assert result.recommended_tier == "synthesis"
    assert [row.candidate.tier for row in result.ranked] == ["synthesis", "pro", "flash"]
    assert all(row.quality_basis == "static_prior" for row in result.ranked)


def test_measured_evidence_precedes_static_priors_without_overriding_budget() -> None:
    result = rank_model_candidates(
        "writing",
        (
            _candidate("flash", score=0.96),
            _candidate("synthesis", score=0.99, exceed=True),
            _candidate("pro"),
        ),
    )
    assert result.recommended_tier == "flash"
    assert [row.candidate.tier for row in result.ranked] == ["flash", "pro", "synthesis"]
    assert result.ranked[2].eligible is False


def test_measurement_basis_does_not_override_a_material_quality_gap() -> None:
    result = rank_model_candidates(
        "writing",
        (_candidate("flash", score=0.2), _candidate("synthesis")),
    )
    assert result.recommended_tier == "synthesis"
    assert [row.candidate.tier for row in result.ranked] == ["synthesis", "flash"]


def test_unready_candidates_remain_visible_but_cannot_be_recommended() -> None:
    result = rank_model_candidates(
        "deep_research",
        (_candidate("pro", ready=False), _candidate("flash", ready=True)),
    )
    assert result.recommended_tier == "flash"
    assert result.ranked[-1].candidate.tier == "pro"
    assert result.ranked[-1].eligible is False


def test_unknown_budget_is_visible_but_not_eligible_or_recommended() -> None:
    result = rank_model_candidates(
        "deep_research",
        (_candidate("pro", exceed=None), _candidate("flash", exceed=True)),
    )
    assert result.recommended_tier is None
    assert [row.candidate.tier for row in result.ranked] == ["pro", "flash"]
    assert all(row.eligible is False for row in result.ranked)


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.1])
def test_invalid_benchmark_scores_fail_closed(score: float) -> None:
    with pytest.raises(ValueError, match="benchmark_score"):
        rank_model_candidates("general", (_candidate("pro", score=score),))

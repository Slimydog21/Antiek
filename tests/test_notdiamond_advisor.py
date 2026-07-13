"""NotDiamond advisor spike contract tests."""

from __future__ import annotations

from typing import Literal, cast

from substrate.model_routing import (
    NotDiamondAdvisorCandidate,
    NotDiamondExternalRecommendation,
    resolve_notdiamond_advisor,
)


def _candidate(
    provider: str,
    model: str,
    *,
    tier: str = "pro",
    high: float | None = 0.01,
    cache: str = "cold",
) -> NotDiamondAdvisorCandidate:
    cache_status = cast(Literal["warm", "cold", "unknown"], cache)
    return NotDiamondAdvisorCandidate(
        provider=provider,
        model=model,
        tier=tier,
        estimated_usd_high=high,
        pricing_known=high is not None,
        cache_status=cache_status,
    )


def test_disabled_advisor_returns_local_policy_without_external_call() -> None:
    local = _candidate("zai", "glm-5.2")
    rec = resolve_notdiamond_advisor(
        candidates=[local],
        local_selected=local,
        mode="disabled",
    )

    assert rec.source == "disabled"
    assert rec.provider == "zai"
    assert rec.external_call_performed is False
    assert rec.notdiamond_would_call is False
    assert rec.promotion_gate.eligible is False


def test_shadow_mode_without_live_recommendation_falls_back_to_local_policy() -> None:
    local = _candidate("zai", "glm-5.2")
    rec = resolve_notdiamond_advisor(
        candidates=[local],
        local_selected=local,
        mode="shadow",
    )

    assert rec.source == "local_policy"
    assert rec.available is False
    assert rec.provider == "zai"
    assert rec.notdiamond_would_call is True
    assert rec.external_call_performed is False


def test_mock_recommendation_maps_only_to_configured_candidate() -> None:
    local = _candidate("zai", "glm-5.2")
    cheap = _candidate("deepseek", "deepseek-v4-pro", tier="pro__fallback")
    rec = resolve_notdiamond_advisor(
        candidates=[local, cheap],
        local_selected=local,
        mode="advisory",
        external_recommendation=NotDiamondExternalRecommendation(
            provider="deepseek",
            model="deepseek-v4-pro",
            confidence=0.73,
            session_id="nd-session-1",
        ),
    )

    assert rec.source == "notdiamond_candidate"
    assert rec.available is True
    assert rec.provider == "deepseek"
    assert rec.tier == "pro__fallback"
    assert rec.confidence == 0.73
    assert rec.session_id == "nd-session-1"


def test_unconfigured_recommendation_is_rejected_not_called_directly() -> None:
    local = _candidate("zai", "glm-5.2")
    rec = resolve_notdiamond_advisor(
        candidates=[local],
        local_selected=local,
        mode="advisory",
        external_recommendation=NotDiamondExternalRecommendation(
            provider="unknown",
            model="frontier",
        ),
    )

    assert rec.source == "advisor_candidate_unavailable"
    assert rec.provider == "zai"
    assert "not configured" in rec.reason
    assert rec.external_call_performed is False


def test_advisor_timeout_falls_back_to_local_policy() -> None:
    local = _candidate("zai", "glm-5.2")
    rec = resolve_notdiamond_advisor(
        candidates=[local],
        local_selected=local,
        mode="advisory",
        advisor_error="timeout",
    )

    assert rec.source == "advisor_unavailable"
    assert rec.provider == "zai"
    assert "timeout" in rec.reason
    assert rec.external_call_performed is False


def test_cache_warm_local_candidate_rejects_cold_advisor_penalty() -> None:
    local = _candidate("anthropic", "claude-sonnet", high=0.002, cache="warm")
    cold = _candidate("cheap", "fast", high=0.004, cache="cold")
    rec = resolve_notdiamond_advisor(
        candidates=[local, cold],
        local_selected=local,
        mode="advisory",
        task_kind="reading_highlight",
        external_recommendation=NotDiamondExternalRecommendation(
            provider="cheap",
            model="fast",
        ),
    )

    assert rec.source == "advisor_cache_penalty"
    assert rec.provider == "anthropic"
    assert rec.cache_caveat is not None
    assert "warm cache" in rec.cache_caveat

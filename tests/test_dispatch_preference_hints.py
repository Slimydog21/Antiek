"""DP preference hint tests (substrate/dispatch/preference_hints.py)."""

from __future__ import annotations

import pytest

from substrate.dispatch.preference_hints import (
    MIN_SAMPLE_COUNT,
    THRESHOLD_PROBABILITY,
    category_for_role,
    recommend_tier,
)
from substrate.dp_shuffler.epsilon_registry import (
    EpsilonRegistry,
    register_surface,
)
from substrate.dp_shuffler.preference_learning import (
    PreferenceLearningStream,
    PreferenceObservation,
)


def _registry_for_role(role: str, *, eps: float = 4.0) -> EpsilonRegistry:
    reg = EpsilonRegistry()
    register_surface(
        reg,
        surface_name=category_for_role(role),
        epsilon_per_day=eps,
        sensitivity="low",
        description=f"per-role upgrade preference for {role}",
    )
    return reg


# ── No upgrade tier configured ─────────────────────────────────────


def test_recommend_returns_fallback_when_no_upgrade():
    reg = _registry_for_role("synthesizer")
    stream = PreferenceLearningStream(registry=reg)
    rec = recommend_tier(
        role="synthesizer",
        fallback_tier="pro",
        upgrade_tier=None,
        stream=stream,
    )
    assert rec.recommended_tier == "pro"
    assert rec.reason == "no_upgrade_tier_configured"


# ── Insufficient sample count → fallback ──────────────────────────


def test_insufficient_samples_returns_fallback():
    """Below MIN_SAMPLE_COUNT, the hint stays on fallback — DP noise
    dominates the signal."""
    reg = _registry_for_role("synthesizer")
    stream = PreferenceLearningStream(registry=reg, per_obs_epsilon=0.01)
    for _ in range(5):  # < MIN_SAMPLE_COUNT
        stream.record(PreferenceObservation(
            category=category_for_role("synthesizer"),
            true_value=True,
        ))
    rec = recommend_tier(
        role="synthesizer",
        fallback_tier="pro",
        upgrade_tier="synthesis",
        stream=stream,
    )
    assert rec.recommended_tier == "pro"
    assert "insufficient_samples" in rec.reason


# ── Estimate above threshold → upgrade ────────────────────────────


def test_strong_preference_recommends_upgrade(monkeypatch):
    """With enough samples and a clear preference for upgrade, the
    hint flips to the upgrade tier.

    We stub ``randomized_response`` so the hint decision logic is what
    the test exercises — the DP randomizer's variance is tested
    separately in test_dp_preference_learning.py."""
    import substrate.dp_shuffler.preference_learning as pref_mod

    monkeypatch.setattr(
        pref_mod, "randomized_response",
        lambda truth, eps: truth,  # bypass noise for this test
    )

    reg = _registry_for_role("synthesizer")
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.05,
    )
    for _ in range(MIN_SAMPLE_COUNT * 2):
        stream.record(PreferenceObservation(
            category=category_for_role("synthesizer"),
            true_value=True,
        ))
    rec = recommend_tier(
        role="synthesizer",
        fallback_tier="pro",
        upgrade_tier="synthesis",
        stream=stream,
    )
    assert rec.recommended_tier == "synthesis", rec.reason
    assert rec.sample_count == MIN_SAMPLE_COUNT * 2
    assert rec.debiased_estimate >= 0.55


# ── Estimate below threshold → fallback ───────────────────────────


def test_weak_signal_stays_on_fallback(monkeypatch):
    """Mixed truth values produce a ~50/50 aggregate → stay on
    fallback. With randomized_response stubbed, the aggregate is
    deterministic so the hint decision is testable."""
    import substrate.dp_shuffler.preference_learning as pref_mod

    monkeypatch.setattr(
        pref_mod, "randomized_response",
        lambda truth, eps: truth,
    )

    reg = _registry_for_role("decomposer")
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.05,
    )
    cat = category_for_role("decomposer")
    for i in range(MIN_SAMPLE_COUNT * 2):
        stream.record(PreferenceObservation(
            category=cat,
            true_value=(i % 2 == 0),
        ))
    rec = recommend_tier(
        role="decomposer",
        fallback_tier="flash",
        upgrade_tier="pro",
        stream=stream,
        threshold=THRESHOLD_PROBABILITY,
    )
    # 50/50 truth → estimate ≈ 0.5 < threshold 0.55.
    assert rec.recommended_tier == "flash", rec.reason
    assert rec.debiased_estimate < THRESHOLD_PROBABILITY


# ── Category naming convention ─────────────────────────────────────


def test_category_for_role_is_stable():
    """Category names are stable per role — the EpsilonRegistry can
    register once and the aggregate accumulates across sessions."""
    assert category_for_role("synthesizer") == "dispatch_prefer_higher_tier__synthesizer"
    assert category_for_role("decomposer") == "dispatch_prefer_higher_tier__decomposer"
    # Idempotent.
    assert category_for_role("synthesizer") == category_for_role("synthesizer")

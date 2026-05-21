"""DP-aware preference learning module tests."""

from __future__ import annotations

import pytest

from substrate.dp_shuffler.epsilon_registry import (
    EpsilonRegistry,
    EpsilonRegistryError,
    register_surface,
)
from substrate.dp_shuffler.preference_learning import (
    PREFERENCE_PER_OBS_EPSILON,
    PreferenceBudgetExhausted,
    PreferenceLearningStream,
    PreferenceObservation,
)


def _registry_with(name: str, epsilon: float, sensitivity: str = "low") -> EpsilonRegistry:
    reg = EpsilonRegistry()
    register_surface(
        reg,
        surface_name=name,
        epsilon_per_day=epsilon,
        sensitivity=sensitivity,
        description="test surface",
    )
    return reg


# ── Registration discipline ──────────────────────────────────────────


def test_record_unregistered_category_raises():
    """Per §16.2: surfaces must be registered with explicit
    sensitivity before any observation is recorded."""
    reg = EpsilonRegistry()
    stream = PreferenceLearningStream(registry=reg)
    with pytest.raises(EpsilonRegistryError, match="not registered"):
        stream.record(
            PreferenceObservation(category="unknown", true_value=True),
        )


def test_aggregate_unregistered_category_returns_zero_budget():
    """Aggregate is read-only — must not raise on unregistered."""
    reg = EpsilonRegistry()
    stream = PreferenceLearningStream(registry=reg)
    pref = stream.aggregate("unknown")
    assert pref.epsilon_budget == 0.0
    assert pref.aggregate.sample_count == 0


# ── Budget enforcement ──────────────────────────────────────────────


def test_records_until_budget_exhausted():
    """Stream accepts observations up to the daily budget, then
    raises PreferenceBudgetExhausted. Per §16.2 binding cap."""
    reg = _registry_with("dispatch_followed", epsilon=0.05)
    stream = PreferenceLearningStream(
        registry=reg, per_obs_epsilon=0.01,
    )
    # 0.05 / 0.01 = 5 observations allowed.
    for _ in range(5):
        stream.record(
            PreferenceObservation(
                category="dispatch_followed", true_value=True,
            ),
        )
    with pytest.raises(PreferenceBudgetExhausted):
        stream.record(
            PreferenceObservation(
                category="dispatch_followed", true_value=True,
            ),
        )


def test_budget_per_category_is_independent():
    """Exhausting one category's budget doesn't block another."""
    reg = EpsilonRegistry()
    register_surface(
        reg, surface_name="cat_a", epsilon_per_day=0.02,
        sensitivity="low", description="a",
    )
    register_surface(
        reg, surface_name="cat_b", epsilon_per_day=0.10,
        sensitivity="low", description="b",
    )
    stream = PreferenceLearningStream(registry=reg, per_obs_epsilon=0.01)
    # Exhaust cat_a.
    for _ in range(2):
        stream.record(PreferenceObservation(category="cat_a", true_value=True))
    with pytest.raises(PreferenceBudgetExhausted):
        stream.record(PreferenceObservation(category="cat_a", true_value=True))
    # cat_b still has 10 observations of headroom.
    for _ in range(5):
        stream.record(PreferenceObservation(category="cat_b", true_value=True))
    assert stream.aggregate("cat_b").aggregate.sample_count == 5


def test_reset_daily_clears_spend():
    reg = _registry_with("cat", epsilon=0.02)
    stream = PreferenceLearningStream(registry=reg, per_obs_epsilon=0.01)
    for _ in range(2):
        stream.record(PreferenceObservation(category="cat", true_value=True))
    with pytest.raises(PreferenceBudgetExhausted):
        stream.record(PreferenceObservation(category="cat", true_value=True))
    stream.reset_daily()
    # After reset we can spend again.
    stream.record(PreferenceObservation(category="cat", true_value=False))


# ── Aggregation correctness ─────────────────────────────────────────


def test_aggregate_carries_budget_and_spend():
    reg = _registry_with("cat", epsilon=0.04)
    stream = PreferenceLearningStream(registry=reg, per_obs_epsilon=0.01)
    stream.record(PreferenceObservation(category="cat", true_value=True))
    stream.record(PreferenceObservation(category="cat", true_value=False))
    pref = stream.aggregate("cat")
    assert pref.epsilon_budget == pytest.approx(0.04)
    assert pref.epsilon_spent == pytest.approx(0.02)
    assert pref.aggregate.sample_count == 2
    assert pref.user_count == 1


def test_aggregate_with_no_observations_is_zero():
    reg = _registry_with("cat", epsilon=1.0)
    stream = PreferenceLearningStream(registry=reg)
    pref = stream.aggregate("cat")
    assert pref.aggregate.sample_count == 0
    assert pref.aggregate.estimate == 0.0


def test_per_obs_epsilon_default_matches_constant():
    """Sanity: the dataclass default is the named module constant."""
    reg = _registry_with("cat", epsilon=1.0)
    stream = PreferenceLearningStream(registry=reg)
    assert stream.per_obs_epsilon == PREFERENCE_PER_OBS_EPSILON

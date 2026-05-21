"""Differential-privacy shuffler tests (Sprint 19, master-spec §13.3)."""

from __future__ import annotations

import random

import pytest

from substrate.dp_shuffler import (
    EpsilonRegistry,
    EpsilonRegistryError,
    LocalRandomizer,
    SurfaceConfig,
    aggregate_with_dp,
    randomized_response,
    register_surface,
)
from substrate.dp_shuffler.epsilon_registry import MAX_EPSILON, SENSITIVITY_BUDGETS


# ── Epsilon registry policy enforcement ──────────────────────────────


def test_max_epsilon_is_ten():
    """Master-spec §16.2: 'No epsilon > 10 on any DP claim.'"""
    assert MAX_EPSILON == 10.0


def test_sensitivity_budgets_match_master_spec():
    """§13.3 names the per-sensitivity caps; drift here = policy hole."""
    assert SENSITIVITY_BUDGETS["low"] == 4.0
    assert SENSITIVITY_BUDGETS["medium"] == 2.0
    assert SENSITIVITY_BUDGETS["high"] == 1.0
    assert SENSITIVITY_BUDGETS["forbidden"] == 0.0


def test_register_surface_within_cap():
    reg = EpsilonRegistry()
    register_surface(
        reg,
        surface_name="skill_invocation_frequency",
        epsilon_per_day=2.0,
        sensitivity="medium",
        description="how often each skill fires per user",
    )
    assert "skill_invocation_frequency" in reg.surfaces


def test_register_surface_above_cap_raises():
    reg = EpsilonRegistry()
    with pytest.raises(EpsilonRegistryError):
        register_surface(
            reg,
            surface_name="bad_surface",
            epsilon_per_day=5.0,  # exceeds the medium cap of 2.0
            sensitivity="medium",
            description="x",
        )


def test_register_forbidden_with_nonzero_epsilon_raises():
    """Query-content telemetry is marked 'forbidden': DP cannot save
    it at any utility-preserving ε. Registering a 'forbidden' surface
    with nonzero ε must raise."""
    reg = EpsilonRegistry()
    with pytest.raises(EpsilonRegistryError):
        register_surface(
            reg,
            surface_name="query_content",
            epsilon_per_day=1.0,
            sensitivity="forbidden",
            description="x",
        )


def test_register_above_max_epsilon_raises():
    """The §16.2 hard cap. Even if a sensitivity bucket allowed it,
    ε > 10 is settled-negative."""
    reg = EpsilonRegistry()
    with pytest.raises(EpsilonRegistryError):
        # 'low' allows 4.0; 15.0 is above the global cap regardless.
        register_surface(
            reg,
            surface_name="cap_test",
            epsilon_per_day=15.0,
            sensitivity="low",
            description="x",
        )


def test_total_daily_epsilon_sums_correctly():
    reg = EpsilonRegistry()
    register_surface(
        reg, surface_name="a", epsilon_per_day=2.0,
        sensitivity="medium", description="x",
    )
    register_surface(
        reg, surface_name="b", epsilon_per_day=4.0,
        sensitivity="low", description="x",
    )
    assert reg.total_daily_epsilon() == 6.0


# ── Randomized response math ────────────────────────────────────────


def test_randomized_response_returns_bool():
    rng = random.Random(42)
    val = randomized_response(True, epsilon=2.0, rng=rng)
    assert isinstance(val, bool)


def test_local_randomizer_more_truthful_at_higher_epsilon():
    """At ε → ∞, p_truth → 1. At ε = 0, p_truth → 0.5. Higher epsilon
    means more truthful responses (less privacy)."""
    rng_high = random.Random(123)
    high_eps_truths = sum(
        LocalRandomizer(epsilon=5.0).randomize(True, rng=rng_high)
        for _ in range(1000)
    )
    rng_low = random.Random(123)
    low_eps_truths = sum(
        LocalRandomizer(epsilon=0.5).randomize(True, rng=rng_low)
        for _ in range(1000)
    )
    assert high_eps_truths > low_eps_truths


def test_aggregate_with_dp_debiases_correctly():
    """At ε = 5.0 and 5000 samples with true_rate=0.7, the aggregate
    should be within 0.05 of 0.7."""
    rng = random.Random(99)
    eps = 5.0
    true_rate = 0.7
    n = 5000
    noisy = [
        LocalRandomizer(epsilon=eps).randomize(rng.random() < true_rate, rng=rng)
        for _ in range(n)
    ]
    agg = aggregate_with_dp(noisy, epsilon=eps)
    assert agg.sample_count == n
    assert agg.epsilon == eps
    assert abs(agg.estimate - true_rate) < 0.05


def test_aggregate_empty_returns_zero():
    agg = aggregate_with_dp([], epsilon=1.0)
    assert agg.estimate == 0.0
    assert agg.sample_count == 0

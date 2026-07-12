"""Tests for substrate/midnight_oil/cost_estimate.py — ask #13 price ceiling."""

from __future__ import annotations

import math

import pytest

from substrate.midnight_oil.cost_estimate import (
    CadenceProfile,
    MidnightOilCostError,
    PhaseTokenBudget,
    TierPricing,
    estimate_midnight_oil_cost,
)


def _cadence():
    return CadenceProfile(
        phases_per_goal=2,
        phase_budgets=(
            PhaseTokenBudget(tier="pro", input_tokens=10_000, output_tokens=5_000),
            PhaseTokenBudget(tier="synthesis", input_tokens=20_000, output_tokens=8_000),
        ),
    )


def _pricing(priced=True):
    if priced:
        return [
            TierPricing(tier="pro", input_per_mtok=2.0, output_per_mtok=8.0),
            TierPricing(tier="synthesis", input_per_mtok=4.0, output_per_mtok=16.0),
        ]
    return [
        TierPricing(tier="pro", input_per_mtok=0.0, output_per_mtok=0.0),
        TierPricing(tier="synthesis", input_per_mtok=4.0, output_per_mtok=16.0),
    ]


# ---------------------------------------------------------------------------
# happy path — high-bound ceiling
# ---------------------------------------------------------------------------


def test_estimable_when_priced():
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing()
    )
    assert est.is_estimable is True
    assert est.recommended_ceiling_usd is not None
    assert est.recommended_ceiling_usd > 0
    assert est.pricing_known is True
    assert est.unpriced_tiers == ()


def test_ceiling_is_high_bound_breakdown():
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing()
    )
    # duration 60m / 3m per phase = 20 phases duration-limited
    # goals 3 * 2 phases_per_goal = 6 goal-limited → min = 6 phases
    assert est.total_phases == 6
    # pro: 10000 in * 6 = 60000 tokens; 2.0/mtok → 0.12 ; 5000 out * 6 = 30000; 8.0 → 0.24
    pro = [b for b in est.breakdown if b.tier == "pro"][0]
    assert pro.total_input_tokens == 60_000
    assert pro.total_output_tokens == 30_000
    assert pro.contribution_usd == pytest.approx(0.12 + 0.24)
    # synthesis: 20000 in * 6 = 120000; 4.0 → 0.48 ; 8000 out * 6 = 48000; 16.0 → 0.768
    syn = [b for b in est.breakdown if b.tier == "synthesis"][0]
    assert syn.contribution_usd == pytest.approx(0.48 + 0.768)
    assert est.recommended_ceiling_usd == pytest.approx(0.36 + 1.248)


# ---------------------------------------------------------------------------
# honesty: placeholder pricing → None, never fabricated $0
# ---------------------------------------------------------------------------


def test_unpriced_tier_yields_none_ceiling():
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing(priced=False)
    )
    assert est.recommended_ceiling_usd is None
    assert est.is_estimable is False
    assert est.pricing_known is False
    assert "pro" in est.unpriced_tiers
    assert any("UNPRICED" in n for n in est.notes)


def test_none_rate_treated_as_unpriced():
    pricing = [
        TierPricing(tier="pro", input_per_mtok=None, output_per_mtok=8.0),
        TierPricing(tier="synthesis", input_per_mtok=4.0, output_per_mtok=16.0),
    ]
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=pricing
    )
    assert est.recommended_ceiling_usd is None
    assert "pro" in est.unpriced_tiers


def test_partial_pricing_breakdown_shows_mixed():
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing(priced=False)
    )
    # pro is unpriced (contribution None); synthesis is priced
    pro = [b for b in est.breakdown if b.tier == "pro"][0]
    syn = [b for b in est.breakdown if b.tier == "synthesis"][0]
    assert pro.contribution_usd is None
    assert syn.contribution_usd is not None


# ---------------------------------------------------------------------------
# zero work → None (honest, not $0)
# ---------------------------------------------------------------------------


def test_zero_goals_yields_none():
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=0, cadence=_cadence(), pricing=_pricing()
    )
    assert est.recommended_ceiling_usd is None
    assert est.total_phases == 0
    assert any("zero work" in n for n in est.notes)


def test_zero_duration_yields_none():
    est = estimate_midnight_oil_cost(
        duration_minutes=0, goals=3, cadence=_cadence(), pricing=_pricing()
    )
    assert est.recommended_ceiling_usd is None


def test_duration_too_short_for_one_phase():
    est = estimate_midnight_oil_cost(
        duration_minutes=1, goals=3, cadence=_cadence(), pricing=_pricing(),
        minutes_per_phase=3.0,
    )
    assert est.recommended_ceiling_usd is None
    assert est.total_phases == 0
    assert any("too short" in n for n in est.notes)


# ---------------------------------------------------------------------------
# phase capping — duration-limited vs goal-limited
# ---------------------------------------------------------------------------


def test_duration_limits_phases():
    # 10m / 3m = 3 phases duration-limited; 5 goals * 2 = 10 goal-limited → min = 3
    est = estimate_midnight_oil_cost(
        duration_minutes=10, goals=5, cadence=_cadence(), pricing=_pricing()
    )
    assert est.total_phases == 3


def test_goals_limit_phases():
    # 100m / 3m = 33 duration; 2 goals * 2 = 4 goal-limited → min = 4
    est = estimate_midnight_oil_cost(
        duration_minutes=100, goals=2, cadence=_cadence(), pricing=_pricing()
    )
    assert est.total_phases == 4


# ---------------------------------------------------------------------------
# impossible inputs rejected
# ---------------------------------------------------------------------------


def test_negative_duration_rejected():
    with pytest.raises(MidnightOilCostError):
        estimate_midnight_oil_cost(
            duration_minutes=-1, goals=3, cadence=_cadence(), pricing=_pricing()
        )


def test_negative_goals_rejected():
    with pytest.raises(MidnightOilCostError):
        estimate_midnight_oil_cost(
            duration_minutes=60, goals=-1, cadence=_cadence(), pricing=_pricing()
        )


def test_zero_minutes_per_phase_rejected():
    with pytest.raises(MidnightOilCostError):
        estimate_midnight_oil_cost(
            duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing(),
            minutes_per_phase=0,
        )


def test_bad_cadence_rejected():
    with pytest.raises(MidnightOilCostError):
        CadenceProfile(phases_per_goal=0, phase_budgets=(PhaseTokenBudget("pro", 1, 1),))
    with pytest.raises(MidnightOilCostError):
        CadenceProfile(phases_per_goal=1, phase_budgets=())


# ---------------------------------------------------------------------------
# purity + frozen value
# ---------------------------------------------------------------------------


def test_estimate_is_pure_idempotent():
    args = dict(duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing())
    a = estimate_midnight_oil_cost(**args)
    b = estimate_midnight_oil_cost(**args)
    assert a == b


def test_breakdown_is_frozen_tuple():
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing()
    )
    assert isinstance(est.breakdown, tuple)
    assert isinstance(est.notes, tuple)


# ---------------------------------------------------------------------------
# composes with the budget substrate (#1842 gate / #1838 projection)
# ---------------------------------------------------------------------------


def test_ceiling_feeds_execution_gate_as_cost_ceiling():
    # The ceiling this produces is the high-bound the operator approves;
    # #1842 authorize_execution checks ceiling_usd <= approved_ceiling_usd.
    est = estimate_midnight_oil_cost(
        duration_minutes=60, goals=3, cadence=_cadence(), pricing=_pricing()
    )
    assert est.recommended_ceiling_usd is not None
    # the ceiling is positive and finite (a real bound)
    assert math.isfinite(est.recommended_ceiling_usd)


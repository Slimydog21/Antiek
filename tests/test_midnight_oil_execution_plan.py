"""Tests for the Midnight Oil execution planner (ask #13).

Each test pins one of the load-bearing invariants documented on the module.
"""

from __future__ import annotations

import pytest

from substrate.midnight_oil.execution_plan import (
    CadenceProfile,
    ExecutionPlan,
    GoalAllocation,
    MidnightOilPlanError,
    PhaseTierBudget,
    PlannedPhase,
    TierPricing,
    plan_midnight_oil,
)


def _cadence(phases_per_goal: int = 2) -> CadenceProfile:
    return CadenceProfile(
        phases_per_goal=phases_per_goal,
        phase_budgets=(
            PhaseTierBudget(tier="cheapest", input_tokens=2000, output_tokens=1000),
            PhaseTierBudget(tier="paid", input_tokens=4000, output_tokens=2000),
        ),
    )


def _pricing(*, priced: bool = True, missing_tier: bool = False) -> tuple[TierPricing, ...]:
    if missing_tier:
        return (TierPricing(tier="cheapest", input_per_mtok=1.0, output_per_mtok=2.0),)
    if priced:
        return (
            TierPricing(tier="cheapest", input_per_mtok=1.0, output_per_mtok=2.0),
            TierPricing(tier="paid", input_per_mtok=10.0, output_per_mtok=30.0),
        )
    return (
        TierPricing(tier="cheapest", input_per_mtok=1.0, output_per_mtok=2.0),
        TierPricing(tier="paid", input_per_mtok=0.0, output_per_mtok=0.0),  # unpriced
    )


# --------------------------------------------------------------------------- #
# Invariant #5 — fail-closed on degenerate input.
# --------------------------------------------------------------------------- #
def test_zero_goals_fails_closed():
    with pytest.raises(MidnightOilPlanError, match="cannot plan zero goals"):
        plan_midnight_oil(
            duration_minutes=60, goals=[], cadence=_cadence(), pricing=_pricing()
        )


def test_zero_duration_fails_closed():
    with pytest.raises(MidnightOilPlanError, match="duration_minutes must be > 0"):
        plan_midnight_oil(
            duration_minutes=0,
            goals=["understand X"],
            cadence=_cadence(),
            pricing=_pricing(),
        )


def test_negative_duration_fails_closed():
    with pytest.raises(MidnightOilPlanError, match="must be > 0"):
        plan_midnight_oil(
            duration_minutes=-5,
            goals=["understand X"],
            cadence=_cadence(),
            pricing=_pricing(),
        )


def test_blank_goal_fails_closed():
    with pytest.raises(MidnightOilPlanError, match="non-empty"):
        plan_midnight_oil(
            duration_minutes=60,
            goals=["real goal", "   "],
            cadence=_cadence(),
            pricing=_pricing(),
        )


def test_bad_cadence_fails():
    with pytest.raises(MidnightOilPlanError, match="phases_per_goal must be >= 1"):
        CadenceProfile(phases_per_goal=0, phase_budgets=(PhaseTierBudget("t", 1, 1),))
    with pytest.raises(MidnightOilPlanError, match="phase_budgets must be non-empty"):
        CadenceProfile(phases_per_goal=1, phase_budgets=())


# --------------------------------------------------------------------------- #
# Invariant #1 — every minute allocated exactly (no loss/invention).
# --------------------------------------------------------------------------- #
def test_total_time_accounted_exactly_no_loss():
    plan = plan_midnight_oil(
        duration_minutes=100,  # prime-ish; 3 goals × 2 phases = 6 slices
        goals=["g0", "g1", "g2"],
        cadence=_cadence(phases_per_goal=2),
        pricing=_pricing(),
    )
    assert sum(p.time_slice_minutes for p in plan.phases) == 100
    # goal allocations also sum to total
    assert sum(g.time_minutes for g in plan.goal_allocations) == 100


def test_remainder_distributed_deterministically():
    # 10 minutes / 3 goals = 3.33 each -> floored 3+3+3=9, 1 leftover to first
    plan = plan_midnight_oil(
        duration_minutes=10,
        goals=["a", "b", "c"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(),
    )
    allocations = [g.time_minutes for g in plan.goal_allocations]
    assert sum(allocations) == 10
    assert allocations[0] >= allocations[2]  # largest remainder wins first


def test_phase_time_within_goal_sums_to_goal_time():
    plan = plan_midnight_oil(
        duration_minutes=61,
        goals=["g0", "g1"],
        cadence=_cadence(phases_per_goal=3),
        pricing=_pricing(),
    )
    for goal_index in range(2):
        goal_phases = plan.phases_for_goal(goal_index)
        goal_alloc = plan.goal_allocations[goal_index].time_minutes
        assert sum(p.time_slice_minutes for p in goal_phases) == goal_alloc


# --------------------------------------------------------------------------- #
# Invariant #2 — even split by default; explicit weights work.
# --------------------------------------------------------------------------- #
def test_default_even_split():
    plan = plan_midnight_oil(
        duration_minutes=60,
        goals=["a", "b", "c"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(),
    )
    allocs = [g.time_minutes for g in plan.goal_allocations]
    assert allocs == [20, 20, 20]


def test_explicit_weights_bias_time():
    # weights [3, 1] -> goal 0 gets 3x the time of goal 1
    plan = plan_midnight_oil(
        duration_minutes=40,
        goals=["heavy", "light"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(),
        goal_weights=[3.0, 1.0],
    )
    allocs = [g.time_minutes for g in plan.goal_allocations]
    assert sum(allocs) == 40
    assert allocs[0] == 30
    assert allocs[1] == 10


def test_zero_weight_rejected():
    with pytest.raises(MidnightOilPlanError, match="must be > 0"):
        plan_midnight_oil(
            duration_minutes=60,
            goals=["a", "b"],
            cadence=_cadence(),
            pricing=_pricing(),
            goal_weights=[1.0, 0.0],
        )


def test_weights_length_mismatch_rejected():
    with pytest.raises(MidnightOilPlanError, match="weights length"):
        plan_midnight_oil(
            duration_minutes=60,
            goals=["a", "b"],
            cadence=_cadence(),
            pricing=_pricing(),
            goal_weights=[1.0, 1.0, 1.0],
        )


# --------------------------------------------------------------------------- #
# Invariant #3 — goal-major ordering; phases_per_goal per goal.
# --------------------------------------------------------------------------- #
def test_goal_major_ordering_and_phase_count():
    plan = plan_midnight_oil(
        duration_minutes=60,
        goals=["g0", "g1"],
        cadence=_cadence(phases_per_goal=3),
        pricing=_pricing(),
    )
    # 2 goals × 3 phases = 6 phases total
    assert plan.phase_count == 6
    assert plan.phases_per_goal == 3
    # goal-major: all g0 phases before g1 phases
    goal_seq = [p.goal_index for p in plan.phases]
    assert goal_seq == [0, 0, 0, 1, 1, 1]
    # phase_index_in_goal resets per goal
    phase_in_goal = [(p.goal_index, p.phase_index_in_goal) for p in plan.phases]
    assert phase_in_goal == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)
    ]
    # ordinals are global 0..N-1
    assert [p.ordinal for p in plan.phases] == [0, 1, 2, 3, 4, 5]


def test_goal_label_carried_verbatim():
    plan = plan_midnight_oil(
        duration_minutes=30,
        goals=["understand transformer scaling", "survey RLHF alternatives"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(),
    )
    assert plan.goals == ("understand transformer scaling", "survey RLHF alternatives")
    assert plan.phases[0].goal_label == "understand transformer scaling"


def test_phases_for_goal_returns_correct_subset():
    plan = plan_midnight_oil(
        duration_minutes=30,
        goals=["a", "b"],
        cadence=_cadence(phases_per_goal=2),
        pricing=_pricing(),
    )
    g1 = plan.phases_for_goal(1)
    assert len(g1) == 2
    assert all(p.goal_index == 1 for p in g1)


# --------------------------------------------------------------------------- #
# Invariant #4 — cumulative envelope monotonic; unpriced -> None.
# --------------------------------------------------------------------------- #
def test_cumulative_envelope_monotonic_when_priced():
    plan = plan_midnight_oil(
        duration_minutes=60,
        goals=["g0", "g1"],
        cadence=_cadence(phases_per_goal=2),
        pricing=_pricing(priced=True),
    )
    assert plan.pricing_known is True
    envelopes = [p.cumulative_high_cost_usd for p in plan.phases]
    # monotonic non-decreasing
    assert all(envelopes[i] <= envelopes[i + 1] for i in range(len(envelopes) - 1))
    # last == total
    assert envelopes[-1] == plan.total_high_cost_usd
    # per-phase cost is the same (same cadence budgets) so each step is equal
    phase_costs = {p.phase_high_cost_usd for p in plan.phases}
    assert len(phase_costs) == 1


def test_per_phase_cost_matches_token_budget_x_rate():
    # cheapest: 2000 in × $1/Mtok + 1000 out × $2/Mtok = 0.002 + 0.002 = 0.004
    # paid: 4000 in × $10/Mtok + 2000 out × $30/Mtok = 0.04 + 0.06 = 0.10
    # per phase = 0.104
    plan = plan_midnight_oil(
        duration_minutes=30,
        goals=["g"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(priced=True),
    )
    assert plan.phases[0].phase_high_cost_usd == pytest.approx(0.104)


def test_unpriced_tier_yields_none_envelope_and_unknown_flag():
    plan = plan_midnight_oil(
        duration_minutes=30,
        goals=["g"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(priced=False),  # paid tier unpriced
    )
    assert plan.pricing_known is False
    assert plan.total_high_cost_usd is None
    assert plan.phases[0].phase_high_cost_usd is None
    assert plan.phases[0].cumulative_high_cost_usd is None


def test_missing_tier_in_pricing_yields_unknown():
    # cadence uses 'paid' tier but pricing omits it
    plan = plan_midnight_oil(
        duration_minutes=30,
        goals=["g"],
        cadence=_cadence(phases_per_goal=1),
        pricing=_pricing(missing_tier=True),
    )
    assert plan.pricing_known is False
    assert plan.total_high_cost_usd is None


# --------------------------------------------------------------------------- #
# Invariant #6 — deterministic + idempotent (content-addressed plan_id).
# --------------------------------------------------------------------------- #
def test_plan_id_stable_across_calls():
    args = dict(
        duration_minutes=45,
        goals=["a", "b"],
        cadence=_cadence(phases_per_goal=2),
        pricing=_pricing(),
    )
    p1 = plan_midnight_oil(**args)
    p2 = plan_midnight_oil(**args)
    assert p1.plan_id == p2.plan_id


def test_plan_id_differs_for_different_goals():
    p1 = plan_midnight_oil(
        duration_minutes=45, goals=["a"], cadence=_cadence(), pricing=_pricing()
    )
    p2 = plan_midnight_oil(
        duration_minutes=45, goals=["b"], cadence=_cadence(), pricing=_pricing()
    )
    assert p1.plan_id != p2.plan_id


def test_plan_id_differs_for_weights():
    p_even = plan_midnight_oil(
        duration_minutes=45, goals=["a", "b"], cadence=_cadence(), pricing=_pricing()
    )
    p_weighted = plan_midnight_oil(
        duration_minutes=45,
        goals=["a", "b"],
        cadence=_cadence(),
        pricing=_pricing(),
        goal_weights=[3.0, 1.0],
    )
    assert p_even.plan_id != p_weighted.plan_id


def test_replan_same_args_byte_identical():
    args = dict(
        duration_minutes=33,
        goals=["x", "y"],
        cadence=_cadence(phases_per_goal=2),
        pricing=_pricing(),
    )
    p1 = plan_midnight_oil(**args)
    p2 = plan_midnight_oil(**args)
    assert p1 == p2  # frozen dataclass equality


# --------------------------------------------------------------------------- #
# Invariant #7 — purity (no I/O / clock / dispatch).
# --------------------------------------------------------------------------- #
def test_purity_no_io_imports():
    import inspect

    from substrate.midnight_oil import execution_plan as mod

    src = inspect.getsource(mod)
    for forbidden in (
        "import os",
        "import time",
        "import asyncio",
        "import requests",
        "open(",
        "datetime.now",
        "connect_write",
    ):
        assert forbidden not in src, f"purity breach: {forbidden!r} in planner source"


# --------------------------------------------------------------------------- #
# Boundary types frozen.
# --------------------------------------------------------------------------- #
def test_boundary_types_frozen():
    import dataclasses

    from substrate.midnight_oil.execution_plan import (
        PhaseTierBudget,
        TierPricing,
    )

    for cls in (
        PhaseTierBudget,
        TierPricing,
        PlannedPhase,
        GoalAllocation,
        ExecutionPlan,
    ):
        assert dataclasses.is_dataclass(cls)

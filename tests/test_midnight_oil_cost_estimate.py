"""Trust-boundary tests for the Midnight Oil price-ceiling estimator."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from substrate.midnight_oil.budget_ledger import BudgetLedger
from substrate.midnight_oil.cost_estimate import (
    CadenceProfile,
    MidnightOilCostError,
    MidnightOilCostEstimate,
    PhaseTokenBudget,
    TierCallCostBreakdown,
    TierCostBreakdown,
    TierPricing,
    estimate_midnight_oil_cost,
    validate_cost_estimate,
)


def _cadence() -> CadenceProfile:
    return CadenceProfile(
        phases_per_goal=2,
        phase_budgets=(
            PhaseTokenBudget("pro", 10_000, 5_000),
            PhaseTokenBudget("synthesis", 20_000, 8_000),
        ),
    )


def _pricing(*, priced: bool = True) -> list[TierPricing]:
    return [
        TierPricing("pro", 2.0 if priced else 0.0, 8.0 if priced else 0.0),
        TierPricing("synthesis", "4.0", Decimal("16.0")),
    ]


def _estimate(**overrides: object) -> MidnightOilCostEstimate:
    values: dict[str, object] = {
        "duration_minutes": 60,
        "goals": 3,
        "cadence": _cadence(),
        "pricing": _pricing(),
    }
    values.update(overrides)
    return estimate_midnight_oil_cost(**values)  # type: ignore[arg-type]


def test_known_estimate_is_exact_integer_cent_reservation() -> None:
    estimate = _estimate()

    assert estimate.total_phases == 6
    assert estimate.recommended_ceiling_cents == 162
    assert estimate.recommended_ceiling_usd == Decimal("1.62")
    assert estimate.is_estimable is True
    assert estimate.pricing_known is True
    assert estimate.unpriced_tiers == ()

    pro, synthesis = estimate.breakdown
    assert pro.total_input_tokens == 60_000
    assert pro.total_output_tokens == 30_000
    assert pro.contribution_cents == 36
    assert pro.contribution_usd == Decimal("0.36")
    # Each of six synthesis calls costs 20.8 cents and needs a 21-cent hold.
    assert synthesis.contribution_cents == 126
    assert synthesis.contribution_usd == Decimal("1.26")
    assert estimate.recommended_ceiling_cents == sum(
        row.contribution_cents or 0 for row in estimate.breakdown
    )


def test_any_startable_partial_phase_is_reserved() -> None:
    cadence = CadenceProfile(100, (PhaseTokenBudget("pro", 1_000_000, 0),))
    pricing = [TierPricing("pro", 1, 1)]

    assert (
        _estimate(
            duration_minutes=Decimal("0.000001"),
            goals=1,
            cadence=cadence,
            pricing=pricing,
        ).total_phases
        == 1
    )
    assert (
        _estimate(
            duration_minutes=Decimal("3.1"),
            goals=1,
            cadence=cadence,
            pricing=pricing,
        ).total_phases
        == 2
    )
    assert (
        _estimate(
            duration_minutes=Decimal("6.1"),
            goals=1,
            cadence=cadence,
            pricing=pricing,
        ).total_phases
        == 3
    )


def test_goal_cadence_caps_duration_capacity() -> None:
    assert _estimate(duration_minutes=100, goals=2).total_phases == 4


def test_duplicate_phase_rows_are_multiple_calls_and_aggregate() -> None:
    cadence = CadenceProfile(
        1,
        (
            PhaseTokenBudget("pro", 10, 20),
            PhaseTokenBudget("pro", 30, 40),
        ),
    )
    estimate = _estimate(
        duration_minutes=1,
        goals=1,
        cadence=cadence,
        pricing=[TierPricing("pro", 1, 1)],
    )
    assert len(estimate.breakdown) == 1
    assert estimate.breakdown[0].total_input_tokens == 40
    assert estimate.breakdown[0].total_output_tokens == 60
    assert len(estimate.breakdown[0].calls_per_phase) == 2


def test_duplicate_subcent_calls_each_receive_a_positive_ledger_hold() -> None:
    estimate = _estimate(
        duration_minutes=1,
        goals=1,
        cadence=CadenceProfile(
            1,
            (
                PhaseTokenBudget("pro", 1, 0),
                PhaseTokenBudget("pro", 1, 0),
            ),
        ),
        pricing=[TierPricing("pro", 1, 1)],
    )
    assert [call.projected_max_cents for call in estimate.breakdown[0].calls_per_phase] == [1, 1]
    assert estimate.breakdown[0].contribution_cents == 2
    assert estimate.recommended_ceiling_cents == 2


def test_subcent_exact_cost_rounds_up_never_down() -> None:
    estimate = _estimate(
        duration_minutes=1,
        goals=1,
        cadence=CadenceProfile(1, (PhaseTokenBudget("pro", 1, 0),)),
        pricing=[TierPricing("pro", Decimal("0.29"), 1)],
    )
    assert estimate.breakdown[0].contribution_cents == 1
    assert estimate.recommended_ceiling_cents == 1
    assert estimate.recommended_ceiling_usd == Decimal("0.01")


@pytest.mark.parametrize(
    "duration, goals",
    [(0, 3), (60, 0), (Decimal("0"), 0)],
)
def test_zero_work_is_known_no_reservation(
    duration: int | Decimal,
    goals: int,
) -> None:
    estimate = _estimate(duration_minutes=duration, goals=goals)
    assert estimate.recommended_ceiling_cents is None
    assert estimate.recommended_ceiling_usd is None
    assert estimate.total_phases == 0
    assert estimate.breakdown == ()
    assert estimate.pricing_known is True
    assert any("zero work" in note for note in estimate.notes)


def test_missing_or_placeholder_rate_is_unknown_never_free() -> None:
    for pricing in (
        _pricing(priced=False),
        [TierPricing("pro", None, 8), TierPricing("synthesis", 4, 16)],
        [TierPricing("synthesis", 4, 16)],
    ):
        estimate = _estimate(pricing=pricing)
        assert estimate.recommended_ceiling_cents is None
        assert estimate.pricing_known is False
        assert estimate.unpriced_tiers == ("pro",)
        assert estimate.breakdown[0].contribution_cents is None
        assert any("UNPRICED" in note for note in estimate.notes)


def test_duplicate_pricing_is_ambiguous_and_rejected() -> None:
    with pytest.raises(MidnightOilCostError, match="duplicate pricing"):
        _estimate(pricing=[TierPricing("pro", 0, 0), TierPricing("pro", 1, 1)])


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf")])
def test_invalid_duration_is_closed(value: float) -> None:
    with pytest.raises(MidnightOilCostError):
        _estimate(duration_minutes=value)


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_goals_require_exact_integer(value: object) -> None:
    with pytest.raises(MidnightOilCostError, match="exact int"):
        _estimate(goals=value)


@pytest.mark.parametrize(
    "value",
    [0, -1, True, float("nan"), float("inf"), "3"],
)
def test_phase_interval_is_finite_positive_number(value: object) -> None:
    with pytest.raises(MidnightOilCostError):
        _estimate(minutes_per_phase=value)


@pytest.mark.parametrize(
    "rate",
    [
        -1,
        float("nan"),
        float("inf"),
        "",
        " 1",
        "not-money",
        Decimal("0." + "1" * 29),
        Decimal("1e-19"),
        "1e-1000000000",
    ],
)
def test_rate_must_be_bounded_finite_decimal(rate: object) -> None:
    with pytest.raises(MidnightOilCostError):
        TierPricing("pro", rate, 1)


def test_rates_are_normalized_to_decimal() -> None:
    pricing = TierPricing("pro", 0.29, "8.00")
    assert pricing.input_per_mtok == Decimal("0.29")
    assert type(pricing.input_per_mtok) is Decimal
    assert pricing.output_per_mtok == Decimal("8.00")


def test_trailing_zeroes_do_not_bypass_decimal_precision_bounds() -> None:
    pricing = TierPricing("pro", Decimal("0.2900000000000000000"), 1)
    assert pricing.input_per_mtok == Decimal("0.29")


def test_extreme_nonzero_exponent_is_rejected_not_coerced_to_placeholder() -> None:
    with pytest.raises(MidnightOilCostError, match="decimal places"):
        TierPricing("pro", "1e-1000000000", 1)


def test_duration_decimal_precision_is_bounded() -> None:
    with pytest.raises(MidnightOilCostError, match="decimal places"):
        _estimate(duration_minutes=Decimal("0.0000001"))
    with pytest.raises(MidnightOilCostError, match="significant"):
        _estimate(duration_minutes=Decimal("1." + "1" * 28))


@pytest.mark.parametrize("tier", ["", "Pro", "two words", "x" * 65, True])
def test_tier_id_has_one_canonical_bounded_grammar(tier: object) -> None:
    with pytest.raises(MidnightOilCostError):
        TierPricing(tier, 1, 1)  # type: ignore[arg-type]
    with pytest.raises(MidnightOilCostError):
        PhaseTokenBudget(tier, 1, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "input_tokens, output_tokens",
    [(-1, 1), (1, -1), (True, 1), (1.5, 1), (0, 0)],
)
def test_phase_token_budget_is_exact_bounded_and_nonempty(
    input_tokens: object,
    output_tokens: object,
) -> None:
    with pytest.raises(MidnightOilCostError):
        PhaseTokenBudget("pro", input_tokens, output_tokens)  # type: ignore[arg-type]


def test_collections_are_exact_and_bounded() -> None:
    with pytest.raises(MidnightOilCostError, match="exact tuple"):
        CadenceProfile(1, [PhaseTokenBudget("pro", 1, 1)])  # type: ignore[arg-type]
    with pytest.raises(MidnightOilCostError, match="list or tuple"):
        _estimate(pricing={TierPricing("pro", 1, 1)})
    with pytest.raises(MidnightOilCostError, match="at most"):
        _estimate(pricing=[TierPricing(f"t{i}", 1, 1) for i in range(257)])


def test_values_are_frozen_and_slotted() -> None:
    pricing = TierPricing("pro", 1, 1)
    assert not hasattr(pricing, "__dict__")
    with pytest.raises(FrozenInstanceError):
        pricing.tier = "other"  # type: ignore[misc]


def test_forged_pricing_is_revalidated_at_estimation_boundary() -> None:
    forged = object.__new__(TierPricing)
    object.__setattr__(forged, "tier", "pro")
    object.__setattr__(forged, "input_per_mtok", Decimal("Infinity"))
    object.__setattr__(forged, "output_per_mtok", Decimal(1))
    with pytest.raises(MidnightOilCostError):
        _estimate(pricing=[forged])


def test_forged_tiny_rate_cannot_bypass_precision_envelope() -> None:
    forged = object.__new__(TierPricing)
    object.__setattr__(forged, "tier", "pro")
    object.__setattr__(forged, "input_per_mtok", Decimal("1e-110"))
    object.__setattr__(forged, "output_per_mtok", Decimal(1))
    with pytest.raises(MidnightOilCostError, match="decimal places"):
        _estimate(pricing=[forged])


def test_forged_cadence_is_revalidated_at_estimation_boundary() -> None:
    forged = object.__new__(CadenceProfile)
    object.__setattr__(forged, "phases_per_goal", -10)
    object.__setattr__(
        forged,
        "phase_budgets",
        (PhaseTokenBudget("pro", 1, 1),),
    )
    with pytest.raises(MidnightOilCostError):
        _estimate(cadence=forged)


def test_missing_forged_slot_fails_with_domain_error() -> None:
    forged = object.__new__(TierPricing)
    object.__setattr__(forged, "tier", "pro")
    with pytest.raises(MidnightOilCostError, match="missing"):
        _estimate(pricing=[forged])


def test_exported_estimate_rejects_forged_inconsistent_totals() -> None:
    estimate = _estimate()
    forged = object.__new__(MidnightOilCostEstimate)
    for name in (
        "total_phases",
        "breakdown",
        "unpriced_tiers",
        "pricing_known",
        "notes",
    ):
        object.__setattr__(forged, name, getattr(estimate, name))
    object.__setattr__(forged, "recommended_ceiling_cents", 1)
    with pytest.raises(MidnightOilCostError, match="contribution sum"):
        validate_cost_estimate(forged)
    with pytest.raises(MidnightOilCostError):
        _ = forged.recommended_ceiling_usd


def test_exported_breakdown_rejects_unpriced_contribution() -> None:
    call = TierCallCostBreakdown("pro", 1, 1, None, None, None)
    with pytest.raises(MidnightOilCostError):
        TierCostBreakdown("pro", 1, 1, None, None, 1, 1, (call,))


def test_exported_breakdown_recomputes_exact_contribution() -> None:
    call = TierCallCostBreakdown(
        "pro",
        1_000_000,
        0,
        Decimal("1E+2"),
        Decimal(1),
        10_000,
    )
    with pytest.raises(MidnightOilCostError, match="repeated per-call ledger holds"):
        TierCostBreakdown(
            "pro",
            1_000_000,
            0,
            Decimal("1E+2"),
            Decimal(1),
            1,
            1,
            (call,),
        )


def test_direct_estimate_construction_enforces_consistency() -> None:
    call = TierCallCostBreakdown("pro", 1, 1, Decimal(1), Decimal(1), 1)
    row = TierCostBreakdown("pro", 1, 1, Decimal(1), Decimal(1), 1, 1, (call,))
    with pytest.raises(MidnightOilCostError):
        MidnightOilCostEstimate(2, 1, (row,), (), True)
    with pytest.raises(MidnightOilCostError):
        MidnightOilCostEstimate(None, 1, (row,), (), False)


def test_estimate_rejects_breakdown_with_different_phase_count() -> None:
    call = TierCallCostBreakdown("pro", 1, 1, Decimal(1), Decimal(1), 1)
    row = TierCostBreakdown("pro", 2, 2, Decimal(1), Decimal(1), 2, 2, (call,))
    with pytest.raises(MidnightOilCostError, match="match the estimate total_phases"):
        MidnightOilCostEstimate(2, 1, (row,), (), True)


def test_estimator_is_pure_and_idempotent() -> None:
    first = _estimate()
    second = _estimate()
    assert first == second
    assert isinstance(first.breakdown, tuple)
    assert isinstance(first.notes, tuple)


def test_ceiling_composes_losslessly_with_budget_ledger_contract(tmp_path: Path) -> None:
    estimate = _estimate()
    approved_ceiling_cents = estimate.recommended_ceiling_cents
    assert type(approved_ceiling_cents) is int
    assert approved_ceiling_cents > 0

    ledger = BudgetLedger(str(tmp_path / "ledger.duckdb"))
    ledger.ensure_schema()
    balance = ledger.reserve(
        "run-cost-estimate",
        approved_ceiling_cents=approved_ceiling_cents,
        role_budgets={
            row.tier: row.contribution_cents
            for row in estimate.breakdown
            if row.contribution_cents is not None
        },
    )
    assert balance.ceiling_cents == approved_ceiling_cents
    assert balance.remaining_cents == approved_ceiling_cents

    holds = []
    for row in estimate.breakdown:
        for _ in range(row.total_phases):
            for call in row.calls_per_phase:
                assert type(call.projected_max_cents) is int
                holds.append(
                    ledger.reserve_call(
                        "run-cost-estimate",
                        row.tier,
                        projected_max_cents=call.projected_max_cents,
                    )
                )
    assert sum(hold.projected_max_cents for hold in holds) == approved_ceiling_cents
    assert ledger.balance("run-cost-estimate").held_cents == approved_ceiling_cents

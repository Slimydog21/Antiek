"""Tests for the Midnight Oil budget-safety-margin axis (ask #13).

Measures how close each run came to its approved ceiling — the operational
headroom / stall-risk signal. Exercises healthy_margin / at_stall_risk /
unknown verdicts, utilization ratios, signed margins, danger-rate, the
worst-case driver, incomplete-run exclusion, boundary inclusivity, overrun
handling, custom thresholds, purity/immutability, and validation.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_safety_margin import (
    BudgetSafetyMarginError,
    measure_budget_safety_margin,
)

# --- unknown (no complete runs) ------------------------------------------


def test_unknown_when_no_runs() -> None:
    r = measure_budget_safety_margin([])
    assert r.verdict == "unknown"
    assert r.run_count == 0
    assert r.incomplete_count == 0
    assert r.mean_utilization is None
    assert r.max_utilization is None
    assert r.min_margin_cents is None
    assert r.mean_margin_cents is None
    assert r.danger_rate is None
    assert r.authority == "advisory"


def test_unknown_when_all_runs_incomplete() -> None:
    # actual None marks incomplete runs — excluded, never fabricated as a verdict.
    r = measure_budget_safety_margin([(1000, None), (2000, None)])
    assert r.verdict == "unknown"
    assert r.run_count == 0
    assert r.incomplete_count == 2
    assert r.max_utilization is None
    assert r.danger_rate is None


# --- healthy_margin -------------------------------------------------------


def test_healthy_margin_single_run_well_under_ceiling() -> None:
    r = measure_budget_safety_margin([(1000, 500)])
    assert r.verdict == "healthy_margin"
    assert r.run_count == 1
    assert r.mean_utilization == 0.5
    assert r.max_utilization == 0.5
    assert r.min_margin_cents == 500
    assert r.mean_margin_cents == 500.0
    assert r.danger_rate == 0.0


def test_healthy_margin_just_below_threshold() -> None:
    # 899/1000 = 0.899 < 0.90 default danger threshold -> healthy.
    r = measure_budget_safety_margin([(1000, 899)])
    assert r.verdict == "healthy_margin"
    assert r.max_utilization == pytest.approx(0.899)
    assert r.danger_rate == 0.0


def test_healthy_margin_all_runs_below_threshold() -> None:
    runs = [(1000, 100), (1000, 200), (1000, 300)]
    r = measure_budget_safety_margin(runs)
    assert r.verdict == "healthy_margin"
    # utils 0.1, 0.2, 0.3 -> max 0.3, mean 0.2.
    assert r.max_utilization == pytest.approx(0.3)
    assert r.mean_utilization == pytest.approx(0.2)
    # margins 900, 800, 700 -> min 700, mean 800.0.
    assert r.min_margin_cents == 700
    assert r.mean_margin_cents == 800.0
    assert r.danger_rate == 0.0


def test_free_run_is_healthy_not_punished() -> None:
    # actual 0 -> utilization 0.0, full margin. A real healthy signal.
    r = measure_budget_safety_margin([(1000, 0)])
    assert r.verdict == "healthy_margin"
    assert r.max_utilization == 0.0
    assert r.min_margin_cents == 1000
    assert r.danger_rate == 0.0


# --- at_stall_risk --------------------------------------------------------


def test_at_stall_risk_boundary_inclusive_at_threshold() -> None:
    # 900/1000 = exactly 0.90 -> >= danger_threshold -> at_stall_risk.
    r = measure_budget_safety_margin([(1000, 900)])
    assert r.verdict == "at_stall_risk"
    assert r.max_utilization == pytest.approx(0.90)
    assert r.danger_rate == 1.0


def test_at_stall_risk_run_exactly_at_ceiling() -> None:
    # utilized the entire approved ceiling: margin 0.
    r = measure_budget_safety_margin([(1000, 1000)])
    assert r.verdict == "at_stall_risk"
    assert r.max_utilization == 1.0
    assert r.min_margin_cents == 0
    assert r.danger_rate == 1.0


def test_at_stall_risk_run_overran_ceiling() -> None:
    # actual > ceiling: utilization > 1.0, negative margin — carried verbatim.
    r = measure_budget_safety_margin([(1000, 1500)])
    assert r.verdict == "at_stall_risk"
    assert r.max_utilization == 1.5
    assert r.min_margin_cents == -500
    assert r.danger_rate == 1.0


def test_at_stall_risk_worst_case_drives_verdict() -> None:
    # one hot run in an otherwise comfortable portfolio flags the whole set.
    runs = [(1000, 200), (1000, 920), (1000, 950), (1000, 100), (1000, None)]
    r = measure_budget_safety_margin(runs)
    assert r.verdict == "at_stall_risk"
    assert r.run_count == 4
    assert r.incomplete_count == 1
    # utils 0.2, 0.92, 0.95, 0.1 -> max 0.95.
    assert r.max_utilization == pytest.approx(0.95)
    # mean = (0.2 + 0.92 + 0.95 + 0.1) / 4 = 2.17 / 4 = 0.5425.
    assert r.mean_utilization == pytest.approx(0.5425)
    # danger zone: 0.92 and 0.95 -> 2 of 4 = 0.5.
    assert r.danger_rate == 0.5
    # margins 800, 80, 50, 900 -> min 50, mean 1830/4 = 457.5.
    assert r.min_margin_cents == 50
    assert r.mean_margin_cents == 457.5


# --- custom danger threshold ---------------------------------------------


def test_custom_threshold_can_widen_danger_zone() -> None:
    # util 0.60 is healthy at the default 0.90 but at_stall_risk at 0.50.
    r_default = measure_budget_safety_margin([(1000, 600)])
    assert r_default.verdict == "healthy_margin"
    r_strict = measure_budget_safety_margin([(1000, 600)], danger_threshold=0.50)
    assert r_strict.verdict == "at_stall_risk"
    assert r_strict.danger_threshold == 0.50


def test_threshold_of_one_is_valid_boundary() -> None:
    # danger_threshold == 1.0 is allowed; a run exactly at cap (util 1.0) flags.
    r = measure_budget_safety_margin([(1000, 1000)], danger_threshold=1.0)
    assert r.verdict == "at_stall_risk"
    # a run at 0.95 does NOT flag when the whole budget must be spent to flag.
    r2 = measure_budget_safety_margin([(1000, 950)], danger_threshold=1.0)
    assert r2.verdict == "healthy_margin"


# --- distinctness: utilization vs absolute margin ------------------------


def test_utilization_and_margin_diverge_under_heterogeneous_ceilings() -> None:
    # Same utilization (0.90) but very different absolute headroom — both honest.
    runs = [(10000, 9000), (100, 90)]
    r = measure_budget_safety_margin(runs)
    assert r.verdict == "at_stall_risk"
    assert r.max_utilization == pytest.approx(0.90)
    # margins 1000 and 10 -> min 10, mean 505.0.
    assert r.min_margin_cents == 10
    assert r.mean_margin_cents == 505.0
    assert r.danger_rate == 1.0


# --- validation -----------------------------------------------------------


def test_non_positive_ceiling_raises() -> None:
    with pytest.raises(BudgetSafetyMarginError):
        measure_budget_safety_margin([(0, 5)])
    with pytest.raises(BudgetSafetyMarginError):
        measure_budget_safety_margin([(-100, 5)])


def test_negative_actual_raises() -> None:
    with pytest.raises(BudgetSafetyMarginError):
        measure_budget_safety_margin([(1000, -5)])


def test_invalid_danger_threshold_raises() -> None:
    with pytest.raises(BudgetSafetyMarginError):
        measure_budget_safety_margin([(1000, 5)], danger_threshold=0.0)
    with pytest.raises(BudgetSafetyMarginError):
        measure_budget_safety_margin([(1000, 5)], danger_threshold=-0.1)
    with pytest.raises(BudgetSafetyMarginError):
        measure_budget_safety_margin([(1000, 5)], danger_threshold=1.01)


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    runs = [(1000, 300), (2000, 1900), (1500, 100)]
    a = measure_budget_safety_margin(runs)
    b = measure_budget_safety_margin(runs)
    assert a == b


def test_report_is_frozen_immutable() -> None:
    r = measure_budget_safety_margin([(1000, 500)])
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "at_stall_risk"  # type: ignore[misc]


def test_notes_carry_worst_case_context_for_stall_risk() -> None:
    r = measure_budget_safety_margin([(1000, 950)])
    assert r.verdict == "at_stall_risk"
    assert any("danger zone" in note for note in r.notes)


def test_notes_carry_healthy_context() -> None:
    r = measure_budget_safety_margin([(1000, 300)])
    assert r.verdict == "healthy_margin"
    assert any("below the danger threshold" in note for note in r.notes)

"""Tests for the Midnight Oil cost-efficiency axis (ask #13).

Pure arithmetic — every cost-per-unit computed by hand from integer cents.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_cost_efficiency import (
    CostEfficiencyError,
    RunCost,
    measure_cost_efficiency,
)

TARGET = 100.0  # cents per delivered unit


def runs(*pairs: tuple[int, int]) -> list[RunCost]:
    return [RunCost(cost_cents=c, delivered_units=u) for c, u in pairs]


# --- verdicts ---------------------------------------------------------------


def test_efficient_under_target() -> None:
    report = measure_cost_efficiency(runs((1000, 20)), TARGET)
    assert report.verdict == "efficient"
    assert report.cost_per_unit == 50.0  # 1000 / 20
    assert report.run_count == 1
    assert report.total_cost_cents == 1000
    assert report.total_delivered_units == 20
    assert report.authority == "advisory"


def test_efficient_at_target_boundary_is_a_hit() -> None:
    # cost_per_unit == target -> efficient (<= boundary).
    report = measure_cost_efficiency(runs((1000, 10)), TARGET)
    assert report.verdict == "efficient"
    assert report.cost_per_unit == 100.0


def test_at_target_within_band() -> None:
    # cost_per_unit = 1100/10 = 110; band [100, 120] -> at_target.
    report = measure_cost_efficiency(runs((1100, 10)), TARGET)
    assert report.verdict == "at_target"
    assert report.cost_per_unit == 110.0


def test_at_target_upper_boundary_is_a_hit() -> None:
    # cost_per_unit = 1200/10 = 120 == target*(1+0.2) -> at_target (<= boundary).
    report = measure_cost_efficiency(runs((1200, 10)), TARGET)
    assert report.verdict == "at_target"


def test_expensive_beyond_band() -> None:
    # cost_per_unit = 1500/10 = 150 > 120 -> expensive.
    report = measure_cost_efficiency(runs((1500, 10)), TARGET)
    assert report.verdict == "expensive"
    assert report.cost_per_unit == 150.0


# --- portfolio aggregation (load-bearing) -----------------------------------


def test_portfolio_sums_then_divides() -> None:
    # 3000c / 40u = 75 c/u -> efficient.
    report = measure_cost_efficiency(runs((1000, 10), (2000, 30)), TARGET)
    assert report.verdict == "efficient"
    assert report.total_cost_cents == 3000
    assert report.total_delivered_units == 40
    assert report.cost_per_unit == 75.0


def test_cost_sink_run_drags_up_portfolio_efficiency() -> None:
    # A run that cost 500c but delivered 0 is INCLUDED in cost but not units.
    # Without it: 1000/20 = 50. With it: 1500/20 = 75. The drag is honest.
    report = measure_cost_efficiency(runs((1000, 20), (500, 0)), TARGET)
    assert report.run_count == 2
    assert report.total_cost_cents == 1500
    assert report.total_delivered_units == 20
    assert report.cost_per_unit == 75.0
    assert report.verdict == "efficient"  # 75 <= 100


def test_cost_sink_can_flip_verdict_to_expensive() -> None:
    # Two good runs + one heavy cost sink pushes cost_per_unit past the band.
    # 1000/40 = 25 alone; +1500c sink -> 2500/40 = 62.5... still efficient.
    # Use a tighter target so the sink flips it: target=40.
    # 2500/40 = 62.5; band [40, 48] -> 62.5 > 48 -> expensive.
    report = measure_cost_efficiency(runs((1000, 40), (1500, 0)), 40.0)
    assert report.cost_per_unit == 62.5
    assert report.verdict == "expensive"


# --- free delivery (edge) ---------------------------------------------------


def test_free_delivery_zero_cost_with_output() -> None:
    report = measure_cost_efficiency(runs((0, 5)), TARGET)
    assert report.verdict == "free_delivery"
    assert report.cost_per_unit == 0.0
    assert report.total_delivered_units == 5


def test_free_delivery_across_portfolio() -> None:
    # All runs free but delivered -> free_delivery.
    report = measure_cost_efficiency(runs((0, 5), (0, 10)), TARGET)
    assert report.verdict == "free_delivery"
    assert report.total_delivered_units == 15


# --- unknown (honesty keystone — never "infinitely expensive") ---------------


def test_unknown_when_zero_runs() -> None:
    report = measure_cost_efficiency([], TARGET)
    assert report.verdict == "unknown"
    assert report.run_count == 0
    assert report.cost_per_unit is None


def test_unknown_when_nothing_delivered_single_run() -> None:
    # A run that spent money but delivered nothing -> unknown (a goals/scope
    # failure, NOT an efficiency verdict; defer, never "infinitely expensive").
    report = measure_cost_efficiency(runs((500, 0)), TARGET)
    assert report.verdict == "unknown"
    assert report.cost_per_unit is None
    assert report.total_cost_cents == 500
    assert report.total_delivered_units == 0


def test_unknown_when_portfolio_delivered_nothing() -> None:
    report = measure_cost_efficiency(runs((500, 0), (300, 0)), TARGET)
    assert report.verdict == "unknown"
    assert report.cost_per_unit is None


# --- custom tolerance -------------------------------------------------------


def test_custom_tolerance_widens_at_target_band() -> None:
    # cost_per_unit = 1400/10 = 140; default band [100,120] -> expensive,
    # but tolerance=0.5 widens band to [100,150] -> at_target.
    report_default = measure_cost_efficiency(runs((1400, 10)), TARGET)
    assert report_default.verdict == "expensive"
    report_wide = measure_cost_efficiency(runs((1400, 10)), TARGET, tolerance=0.5)
    assert report_wide.verdict == "at_target"
    assert report_wide.tolerance == 0.5


def test_tolerance_zero_only_target_is_efficient() -> None:
    # tolerance 0.0: band collapses to [100,100]; 110 -> at_target is gone, -> expensive.
    report = measure_cost_efficiency(runs((1100, 10)), TARGET, tolerance=0.0)
    assert report.verdict == "expensive"


# --- validation (load-bearing invariants) -----------------------------------


def test_nonpositive_efficiency_target_raises() -> None:
    with pytest.raises(CostEfficiencyError, match="efficiency_target"):
        measure_cost_efficiency(runs((100, 5)), 0.0)
    with pytest.raises(CostEfficiencyError, match="efficiency_target"):
        measure_cost_efficiency(runs((100, 5)), -10.0)


def test_tolerance_out_of_range_raises() -> None:
    with pytest.raises(CostEfficiencyError, match="tolerance"):
        measure_cost_efficiency(runs((100, 5)), TARGET, tolerance=1.5)
    with pytest.raises(CostEfficiencyError, match="tolerance"):
        measure_cost_efficiency(runs((100, 5)), TARGET, tolerance=-0.1)


def test_negative_cost_raises() -> None:
    with pytest.raises(CostEfficiencyError, match="cost_cents"):
        measure_cost_efficiency(runs((-100, 5)), TARGET)


def test_negative_delivered_units_raises() -> None:
    with pytest.raises(CostEfficiencyError, match="delivered_units"):
        measure_cost_efficiency(runs((100, -5)), TARGET)


# --- purity / determinism ---------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_cost_efficiency(runs((1000, 20)), TARGET)
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    portfolio = runs((1000, 10), (2000, 30), (500, 0))
    first = measure_cost_efficiency(portfolio, TARGET)
    second = measure_cost_efficiency(portfolio, TARGET)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_cost_efficiency(runs((1500, 10)), TARGET)
    joined = " ".join(report.notes)
    assert "cost-efficiency" in joined
    assert "verdict expensive" in joined
    assert "cost_per_unit 150.00" in joined

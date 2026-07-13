"""Tests for the Midnight Oil ceiling-accuracy axis (ask #13 + ask #11 learning).

Measures whether the recommended price ceiling matched actual run costs. Exercises:
well_calibrated/under_estimating/over_estimating/unknown verdicts, signed bias,
mean_abs_error, within_tolerance_rate, ceiling_hit_rate, incomplete-run exclusion,
the asymmetric under/over failure logic, purity/immutability, validation.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.mo_ceiling_accuracy import (
    CeilingAccuracyError,
    CeilingAccuracyReport,
    measure_ceiling_accuracy,
)

# --- well_calibrated ------------------------------------------------------


def test_well_calibrated_recommendations_match_actual() -> None:
    # ceiling_hit boundary is actual >= recommended (exact match = used full budget = hit).
    runs = [(1000, 1050), (1000, 950), (1000, 1000)]
    r = measure_ceiling_accuracy(runs)
    assert r.verdict == "well_calibrated"
    assert r.run_count == 3
    assert r.authority == "advisory"
    # errors: +50, -50, 0 -> mean_bias = 0 (well-calibrated despite spread).
    assert r.mean_bias == 0.0
    # ceiling hits: 1050>=1000 T, 950>=1000 F, 1000>=1000 T -> 2/3.
    assert r.ceiling_hit_rate == pytest.approx(2 / 3)


def test_well_calibrated_zero_bias_exact_match() -> None:
    runs = [(1000, 1000)]
    r = measure_ceiling_accuracy(runs)
    assert r.mean_bias == 0.0
    assert r.verdict == "well_calibrated"


# --- under_estimating (the dangerous direction) ---------------------------


def test_under_estimating_positive_bias_and_stalls() -> None:
    # recommended 1000, actual 1500 every run -> bias +500, all hit ceiling.
    runs = [(1000, 1500), (1000, 1400), (1000, 1600)]
    r = measure_ceiling_accuracy(runs)
    assert r.mean_bias is not None and r.mean_bias > 0
    assert r.ceiling_hit_rate == 1.0  # all actual >= recommended
    assert r.verdict == "under_estimating"


def test_under_estimating_requires_stall_rate_not_just_bias() -> None:
    # positive bias from ONE outlier but most runs well under budget -> not stalling.
    # 2 runs came in at half-budget (1000/500), 1 ran way over (1000/5000).
    # errors: -500, -500, +4000 -> mean_bias = 1000 > 0.
    # ceiling_hits: 500>=1000 F, 500>=1000 F, 5000>=1000 T -> 1/3 < 0.50.
    runs = [(1000, 500), (1000, 500), (1000, 5000)]
    r = measure_ceiling_accuracy(runs)
    assert r.mean_bias is not None and r.mean_bias > 0
    assert r.ceiling_hit_rate == pytest.approx(1 / 3)
    assert r.verdict == "well_calibrated"  # positive bias but NOT stalling systematically


# --- over_estimating ------------------------------------------------------


def test_over_estimating_negative_bias() -> None:
    # recommended 2000, actual 1000 -> bias -1000 (over-estimated).
    runs = [(2000, 1000), (2000, 1200)]
    r = measure_ceiling_accuracy(runs)
    assert r.mean_bias is not None and r.mean_bias < 0
    assert r.verdict == "over_estimating"


# --- unknown (defer, never fabricated) ------------------------------------


def test_unknown_when_zero_runs() -> None:
    r = measure_ceiling_accuracy([])
    assert r.verdict == "unknown"
    assert r.mean_bias is None
    assert r.mean_abs_error is None
    assert r.within_tolerance_rate is None
    assert r.ceiling_hit_rate is None


def test_unknown_when_all_incomplete() -> None:
    runs = [(1000, None), (2000, None)]
    r = measure_ceiling_accuracy(runs)
    assert r.verdict == "unknown"
    assert r.incomplete_count == 2
    assert r.run_count == 0
    assert r.mean_bias is None


# --- incomplete-run exclusion ---------------------------------------------


def test_incomplete_runs_excluded() -> None:
    # 2 complete + 1 incomplete. The incomplete must not pollute the rate.
    runs = [(1000, 1000), (2000, 2000), (3000, None)]
    r = measure_ceiling_accuracy(runs)
    assert r.run_count == 2
    assert r.incomplete_count == 1
    assert r.mean_bias == 0.0  # only the 2 complete runs counted
    assert r.verdict == "well_calibrated"


# --- within tolerance -----------------------------------------------------


def test_within_tolerance_rate() -> None:
    # tolerance 20%. recommended 1000 -> within if |error| <= 200.
    # run1: 1000/1100 (error 100) -> within. run2: 1000/1400 (error 400) -> not.
    runs = [(1000, 1100), (1000, 1400)]
    r = measure_ceiling_accuracy(runs, tolerance=0.20)
    assert r.within_tolerance_rate == 0.5


def test_custom_tolerance_changes_within_rate() -> None:
    runs = [(1000, 1100), (1000, 1200)]
    # error 100 and 200. tolerance 10% -> |error| <= 100 -> 1 within.
    strict = measure_ceiling_accuracy(runs, tolerance=0.10)
    assert strict.within_tolerance_rate == 0.5
    # tolerance 25% -> |error| <= 250 -> both within.
    loose = measure_ceiling_accuracy(runs, tolerance=0.25)
    assert loose.within_tolerance_rate == 1.0


# --- mean_abs_error (direction-agnostic magnitude) ------------------------


def test_mean_abs_error_ignores_direction() -> None:
    # +100 and -100 cancel in mean_bias (0) but abs_error = 100.
    runs = [(1000, 1100), (1000, 900)]
    r = measure_ceiling_accuracy(runs)
    assert r.mean_bias == 0.0
    assert r.mean_abs_error == 100.0


# --- mean_bias_pct --------------------------------------------------------


def test_mean_bias_pct_relative_to_recommended() -> None:
    # recommended 1000 avg, bias +200 -> 20% of recommended.
    runs = [(1000, 1200)]
    r = measure_ceiling_accuracy(runs)
    assert r.mean_bias_pct == pytest.approx(0.20)


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_tolerance_raises(bad: float) -> None:
    with pytest.raises(CeilingAccuracyError, match="tolerance"):
        measure_ceiling_accuracy([(1000, 1000)], tolerance=bad)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_stall_threshold_raises(bad: float) -> None:
    with pytest.raises(CeilingAccuracyError, match="stall_threshold"):
        measure_ceiling_accuracy([(1000, 1000)], stall_threshold=bad)


def test_negative_actual_raises() -> None:
    with pytest.raises(CeilingAccuracyError, match="non-negative"):
        measure_ceiling_accuracy([(1000, -5)])


def test_negative_recommended_raises() -> None:
    with pytest.raises(CeilingAccuracyError, match="non-negative"):
        measure_ceiling_accuracy([(-5, 1000)])


def test_none_recommended_raises() -> None:
    with pytest.raises(CeilingAccuracyError, match="non-negative"):
        measure_ceiling_accuracy([(None, 1000)])


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    runs = [(1000, 1100), (1000, 900)]
    r1 = measure_ceiling_accuracy(runs)
    r2 = measure_ceiling_accuracy(runs)
    assert dataclasses.is_dataclass(r1)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]
    assert isinstance(r1, CeilingAccuracyReport)


def test_notes_are_non_empty_and_auditable() -> None:
    r = measure_ceiling_accuracy([(1000, 1000)])
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)

"""Tests for the Midnight Oil spend-tempo axis (ask #13).

Every fixture is hand-counted: deviations, peaks, and net-load are verified by
inspection before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.mo_spend_tempo import (
    CheckpointTempo,
    MoSpendTempoReport,
    SpendCheckpoint,
    measure_mo_spend_tempo,
)


def cp(elapsed: float, spent: float) -> SpendCheckpoint:
    return SpendCheckpoint(elapsed_fraction=elapsed, spent_fraction=spent)


# ---------------------------------------------------------------------------
# Base case.
# ---------------------------------------------------------------------------


def test_no_checkpoints_is_unknown() -> None:
    report = measure_mo_spend_tempo([])
    assert report.verdict == "unknown"
    assert report.front_load_peak is None
    assert report.back_load_peak is None
    assert report.net_load is None
    assert report.max_abs_deviation is None
    assert report.checkpoint_tempos == ()
    assert report.authority == "advisory"


# ---------------------------------------------------------------------------
# Linear — spend tracks time within tolerance.
# ---------------------------------------------------------------------------


def test_perfectly_linear() -> None:
    report = measure_mo_spend_tempo(
        [cp(0.0, 0.0), cp(0.25, 0.26), cp(0.5, 0.48), cp(0.75, 0.77), cp(1.0, 1.0)]
    )
    assert report.front_load_peak == pytest.approx(0.02)
    assert report.back_load_peak == pytest.approx(0.02)
    assert report.max_abs_deviation == pytest.approx(0.02)
    assert report.verdict == "linear"


def test_linear_at_tolerance_boundary() -> None:
    # max deviation exactly 0.15 (the default tolerance) -> linear (<=).
    report = measure_mo_spend_tempo([cp(0.2, 0.35)])  # deviation 0.15
    assert report.max_abs_deviation == pytest.approx(0.15)
    assert report.verdict == "linear"


# ---------------------------------------------------------------------------
# Front-loaded — spend races ahead of time.
# ---------------------------------------------------------------------------


def test_front_loaded() -> None:
    # 80% spent at 20% elapsed -> deviation 0.60 ahead.
    report = measure_mo_spend_tempo(
        [cp(0.2, 0.80), cp(0.5, 0.85), cp(1.0, 1.0)]
    )
    assert report.front_load_peak == pytest.approx(0.60)
    assert report.back_load_peak == pytest.approx(0.0)  # no checkpoint lags time
    assert report.verdict == "front_loaded"


def test_front_loaded_net_load_positive() -> None:
    report = measure_mo_spend_tempo([cp(0.1, 0.7), cp(1.0, 1.0)])
    assert report.front_load_peak == pytest.approx(0.60)
    assert report.back_load_peak == pytest.approx(0.0)
    assert report.net_load is not None and report.net_load > 0


# ---------------------------------------------------------------------------
# Back-loaded — spend lags time.
# ---------------------------------------------------------------------------


def test_back_loaded() -> None:
    # 20% spent at 80% elapsed -> deviation -0.60 (back-loaded).
    report = measure_mo_spend_tempo(
        [cp(0.5, 0.10), cp(0.8, 0.20), cp(1.0, 1.0)]
    )
    assert report.back_load_peak == pytest.approx(0.60)  # at 0.8 elapsed, 0.20 spent -> 0.60 lag
    assert report.verdict == "back_loaded"


def test_back_loaded_net_load_negative() -> None:
    report = measure_mo_spend_tempo([cp(0.9, 0.1), cp(1.0, 1.0)])
    assert report.back_load_peak == pytest.approx(0.80)
    assert report.net_load is not None and report.net_load < 0


# ---------------------------------------------------------------------------
# Deviation auditability + clamping.
# ---------------------------------------------------------------------------


def test_checkpoint_tempos_carry_deviation() -> None:
    report = measure_mo_spend_tempo([cp(0.3, 0.5), cp(0.7, 0.6)])
    assert all(isinstance(t, CheckpointTempo) for t in report.checkpoint_tempos)
    assert report.checkpoint_tempos[0].deviation == pytest.approx(0.20)
    assert report.checkpoint_tempos[1].deviation == pytest.approx(-0.10)


def test_out_of_range_fractions_clamped() -> None:
    # negative elapsed / over-1 spent clamped to [0,1].
    report = measure_mo_spend_tempo([cp(-0.2, 1.5)])
    assert report.checkpoint_tempos[0].elapsed_fraction == pytest.approx(0.0)
    assert report.checkpoint_tempos[0].spent_fraction == pytest.approx(1.0)
    assert report.checkpoint_tempos[0].deviation == pytest.approx(1.0)


def test_max_abs_deviation_is_max_of_peaks() -> None:
    report = measure_mo_spend_tempo([cp(0.2, 0.8), cp(0.8, 0.2)])
    assert report.front_load_peak == pytest.approx(0.60)
    assert report.back_load_peak == pytest.approx(0.60)
    assert report.max_abs_deviation == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Threshold validation + custom tolerance.
# ---------------------------------------------------------------------------


def test_linear_tolerance_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="linear_tolerance"):
        measure_mo_spend_tempo([cp(0.5, 0.5)], linear_tolerance=-0.1)
    with pytest.raises(ValueError, match="linear_tolerance"):
        measure_mo_spend_tempo([cp(0.5, 0.5)], linear_tolerance=1.5)


def test_custom_tolerance_reclassifies_linear_to_front_loaded() -> None:
    # deviation 0.10: linear at default 0.15, front_loaded at strict 0.05.
    cps = [cp(0.4, 0.5)]
    assert measure_mo_spend_tempo(cps).verdict == "linear"
    assert measure_mo_spend_tempo(cps, linear_tolerance=0.05).verdict == "front_loaded"


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_mo_spend_tempo([cp(0.5, 0.5)])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "front_loaded"  # type: ignore[misc]


def test_deterministic_output() -> None:
    cps = [cp(0.2, 0.8), cp(0.5, 0.9), cp(1.0, 1.0)]
    assert measure_mo_spend_tempo(cps) == measure_mo_spend_tempo(cps)


def test_report_is_mo_spend_tempo_report_instance() -> None:
    report = measure_mo_spend_tempo([cp(0.5, 0.5)])
    assert isinstance(report, MoSpendTempoReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_mo_spend_tempo([cp(0.2, 0.8)])
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)
    assert any("trajectory" in n.lower() for n in report.notes)

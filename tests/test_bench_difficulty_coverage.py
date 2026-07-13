"""Tests for substrate/bench_difficulty_coverage.py — spectrum-spanning quality."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.bench_difficulty_coverage import (
    TaskMeanScore,
    measure_difficulty_coverage,
)


def _tasks(*pairs: tuple[str, float]) -> list[TaskMeanScore]:
    return [TaskMeanScore(task_id=t, mean_score=m) for t, m in pairs]


# --- unknown ---------------------------------------------------------------


def test_unknown_no_tasks() -> None:
    r = measure_difficulty_coverage([])
    assert r.verdict == "unknown"
    assert r.difficulty_span is None
    assert r.mean_difficulty is None
    assert r.difficulty_spread is None
    assert r.authority == "advisory"
    assert r.empty_band_count == 4


def test_unknown_never_fabricates_broad() -> None:
    assert measure_difficulty_coverage([]).verdict != "broad_spectrum"


# --- single_task (honest base case) ---------------------------------------


def test_single_task_base_case() -> None:
    r = measure_difficulty_coverage(_tasks(("t1", 0.5)))
    assert r.verdict == "single_task"
    assert r.difficulty_span == pytest.approx(0.0)
    assert r.difficulty_spread == pytest.approx(0.0)


def test_single_task_distinct_from_unknown_and_narrow() -> None:
    assert measure_difficulty_coverage([]).verdict == "unknown"
    assert measure_difficulty_coverage(_tasks(("t1", 0.5))).verdict == "single_task"


# --- narrow_band (cluster at one tier) ------------------------------------


def test_narrow_band_all_hard() -> None:
    # All tasks hard: means ~0.1-0.15 -> difficulty ~0.85-0.9, span ~0.05 < 0.20.
    r = measure_difficulty_coverage(
        _tasks(("t1", 0.10), ("t2", 0.12), ("t3", 0.15))
    )
    assert r.verdict == "narrow_band"
    assert r.difficulty_span is not None and r.difficulty_span < 0.20
    assert r.empty_band_count >= 1


def test_narrow_band_all_easy() -> None:
    # All tasks easy: means ~0.85-0.9 -> difficulty ~0.1-0.15.
    r = measure_difficulty_coverage(
        _tasks(("t1", 0.85), ("t2", 0.88), ("t3", 0.90))
    )
    assert r.verdict == "narrow_band"


def test_narrow_band_boundary_inclusive() -> None:
    # span exactly == narrow_span 0.20 -> NOT narrow (< is strict).
    # means 0.8 (diff 0.2) and 0.6 (diff 0.4) -> span exactly 0.20.
    r = measure_difficulty_coverage(_tasks(("t1", 0.8), ("t2", 0.6)))
    assert r.difficulty_span == pytest.approx(0.20)
    # span == 0.20 is NOT < 0.20, so not narrow. But may be partial (only 2 bands).
    assert r.verdict != "narrow_band"


# --- broad_spectrum (full range, all bands) -------------------------------


def test_broad_spectrum_all_bands() -> None:
    # One task in each band: easy (0.9, diff 0.1), medium (0.5, diff 0.5),
    # hard (0.2, diff 0.8), frontier (0.05, diff 0.95).
    r = measure_difficulty_coverage(
        _tasks(("easy", 0.90), ("med", 0.50), ("hard", 0.20), ("front", 0.05))
    )
    assert r.verdict == "broad_spectrum"
    assert r.empty_band_count == 0
    assert r.difficulty_span is not None and r.difficulty_span > 0.20


def test_broad_spectrum_is_measured_not_default() -> None:
    assert measure_difficulty_coverage([]).verdict == "unknown"
    assert measure_difficulty_coverage(_tasks(("t1", 0.5))).verdict == "single_task"
    assert (
        measure_difficulty_coverage(
            _tasks(("easy", 0.90), ("med", 0.50), ("hard", 0.20), ("front", 0.05))
        ).verdict
        == "broad_spectrum"
    )


# --- partial_coverage (wide span but a blind spot) ------------------------


def test_partial_coverage_missing_frontier() -> None:
    # easy + medium + hard, but no frontier. Span wide, but frontier empty.
    r = measure_difficulty_coverage(
        _tasks(("easy", 0.90), ("med", 0.50), ("hard", 0.25))
    )
    assert r.verdict == "partial_coverage"
    assert r.empty_band_count >= 1
    assert "frontier" in r.empty_bands
    assert r.difficulty_span is not None and r.difficulty_span > 0.20


def test_partial_coverage_blind_spot_surfaced() -> None:
    r = measure_difficulty_coverage(_tasks(("easy", 0.90), ("hard", 0.25)))
    assert r.verdict == "partial_coverage"
    assert any("blind spot" in n for n in r.notes)


# --- difficulty stats ------------------------------------------------------


def test_difficulty_min_max_span() -> None:
    # means 0.9 (diff 0.1) and 0.1 (diff 0.9).
    r = measure_difficulty_coverage(_tasks(("easy", 0.9), ("hard", 0.1)))
    assert r.difficulty_min == pytest.approx(0.1)
    assert r.difficulty_max == pytest.approx(0.9)
    assert r.difficulty_span == pytest.approx(0.8)


def test_mean_difficulty() -> None:
    # two tasks: difficulties 0.2 and 0.6 -> mean 0.4.
    r = measure_difficulty_coverage(_tasks(("t1", 0.8), ("t2", 0.4)))
    assert r.mean_difficulty == pytest.approx(0.4)


def test_difficulty_spread_zero_uniform() -> None:
    # all same difficulty -> spread 0.
    r = measure_difficulty_coverage(_tasks(("t1", 0.5), ("t2", 0.5), ("t3", 0.5)))
    assert r.difficulty_spread == pytest.approx(0.0)


def test_difficulty_spread_positive_varied() -> None:
    r = measure_difficulty_coverage(_tasks(("t1", 0.9), ("t2", 0.1)))
    # difficulties 0.1, 0.9 -> mean 0.5, var = (0.4^2 + 0.4^2)/2 = 0.16, sd 0.4.
    assert r.difficulty_spread == pytest.approx(0.4)


# --- band counts auditable -------------------------------------------------


def test_band_counts() -> None:
    r = measure_difficulty_coverage(
        _tasks(("easy", 0.90), ("med", 0.50), ("hard", 0.20), ("front", 0.05))
    )
    assert r.band_counts["easy"] == 1
    assert r.band_counts["medium"] == 1
    assert r.band_counts["hard"] == 1
    assert r.band_counts["frontier"] == 1


def test_empty_bands_order() -> None:
    # Only easy tasks -> empty bands = medium, hard, frontier (in order).
    r = measure_difficulty_coverage(_tasks(("t1", 0.9), ("t2", 0.88)))
    assert r.empty_bands == ("medium", "hard", "frontier")


# --- load-bearing: discrimination vs coverage orthogonal ------------------


def test_orthogonal_to_discrimination() -> None:
    # A benchmark can span the full difficulty spectrum (this broad) yet have
    # every task be a poor discriminator (every model scores the same on each).
    # Here all 4 bands covered -> broad_spectrum, regardless of per-task variance.
    r = measure_difficulty_coverage(
        _tasks(("easy", 0.90), ("med", 0.50), ("hard", 0.20), ("front", 0.05))
    )
    assert r.verdict == "broad_spectrum"
    # (discrimination #1960 would look at inter-model variance per task —
    #  not computable from means alone. Orthogonal.)


# --- custom threshold ------------------------------------------------------


def test_custom_narrow_span() -> None:
    # span 0.25 is not narrow under default 0.20, but is narrow under 0.30.
    base = _tasks(("t1", 0.8), ("t2", 0.55))  # diff 0.2, 0.45 -> span 0.25
    assert measure_difficulty_coverage(base).verdict != "narrow_band"
    assert measure_difficulty_coverage(base, narrow_span=0.30).verdict == "narrow_band"


# --- validation ------------------------------------------------------------


def test_invalid_narrow_span_negative() -> None:
    with pytest.raises(ValueError, match="narrow_span"):
        measure_difficulty_coverage([], narrow_span=-0.1)


def test_invalid_narrow_span_over_one() -> None:
    with pytest.raises(ValueError, match="narrow_span"):
        measure_difficulty_coverage([], narrow_span=1.5)


def test_invalid_score_negative() -> None:
    with pytest.raises(ValueError, match="outside"):
        measure_difficulty_coverage(_tasks(("t1", -0.1)))


def test_invalid_score_over_one() -> None:
    with pytest.raises(ValueError, match="outside"):
        measure_difficulty_coverage(_tasks(("t1", 1.2)))


def test_nan_score_rejected() -> None:
    with pytest.raises(ValueError, match="NaN"):
        measure_difficulty_coverage(_tasks(("t1", float("nan"))))


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_difficulty_coverage(_tasks(("t1", 0.5)))
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]

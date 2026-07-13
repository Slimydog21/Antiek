"""Tests for substrate/bench_stability.py — benchmark reproducibility quality."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.bench_stability import (
    RepeatRunSet,
    measure_bench_stability,
)


def _set(model: str, task: str, *scores: float) -> RepeatRunSet:
    return RepeatRunSet(model_id=model, task_id=task, scores=tuple(scores))


# --- unknown ---------------------------------------------------------------


def test_unknown_no_run_sets() -> None:
    r = measure_bench_stability([])
    assert r.verdict == "unknown"
    assert r.max_range is None
    assert r.mean_range is None
    assert r.min_range is None
    assert r.authority == "advisory"


def test_unknown_only_single_run_pairs() -> None:
    # A single run has no reproducibility to assess — never fabricated stable.
    r = measure_bench_stability([_set("m1", "t1", 0.8), _set("m2", "t1", 0.5)])
    assert r.verdict == "unknown"
    assert r.unmeasurable_pair_count == 2


def test_unknown_never_fabricates_stable() -> None:
    assert measure_bench_stability([_set("m1", "t1", 1.0)]).verdict != "stable"


# --- stable ----------------------------------------------------------------


def test_stable_all_consistent() -> None:
    r = measure_bench_stability(
        [_set("m1", "t1", 0.8, 0.8, 0.8), _set("m2", "t1", 0.5, 0.52)]
    )
    assert r.verdict == "stable"
    assert r.unstable_group_count == 0
    assert r.measurable_pair_count == 2
    assert r.max_range == pytest.approx(0.02)


def test_stable_is_measured_not_default() -> None:
    assert measure_bench_stability([]).verdict == "unknown"
    assert measure_bench_stability([_set("m1", "t1", 0.8, 0.8)]).verdict == "stable"


# --- unstable --------------------------------------------------------------


def test_unstable_one_pair_swings() -> None:
    r = measure_bench_stability(
        [_set("m1", "t1", 0.8, 0.8), _set("m2", "t1", 0.2, 0.9)]
    )
    assert r.verdict == "unstable"
    assert r.unstable_group_count == 1
    assert r.unstable_groups[0].model_id == "m2"
    assert r.unstable_groups[0].range_value == pytest.approx(0.7)
    assert r.max_range == pytest.approx(0.7)


def test_unstable_boundary_inclusive() -> None:
    # range exactly == threshold (0.10) IS unstable (>= is inclusive).
    r = measure_bench_stability([_set("m1", "t1", 0.3, 0.4)])
    assert r.verdict == "unstable"
    assert r.max_range == pytest.approx(0.10)


def test_unstable_groups_sorted_by_range_desc() -> None:
    r = measure_bench_stability(
        [
            _set("m1", "t1", 0.1, 0.9),  # 0.8
            _set("m2", "t1", 0.2, 0.4),  # 0.2
            _set("m3", "t1", 0.0, 0.6),  # 0.6
        ]
    )
    ranges = [u.range_value for u in r.unstable_groups]
    assert ranges == sorted(ranges, reverse=True)


# --- single-run unmeasurable ----------------------------------------------


def test_single_run_unmeasurable_not_stable() -> None:
    r = measure_bench_stability(
        [_set("m1", "t1", 0.8, 0.8), _set("m2", "t1", 0.5)]
    )
    assert r.verdict == "stable"
    assert r.measurable_pair_count == 1
    assert r.unmeasurable_pair_count == 1
    assert any("unmeasurable" in n for n in r.notes)


# --- audit fields ----------------------------------------------------------


def test_unstable_pair_carries_min_max_run_count() -> None:
    r = measure_bench_stability([_set("m1", "t1", 0.2, 0.9, 0.5)])
    u = r.unstable_groups[0]
    assert u.run_count == 3
    assert u.min_score == pytest.approx(0.2)
    assert u.max_score == pytest.approx(0.9)


def test_min_and_mean_range() -> None:
    r = measure_bench_stability(
        [_set("m1", "t1", 0.8, 0.8), _set("m2", "t1", 0.2, 0.9)]
    )
    assert r.min_range == pytest.approx(0.0)
    assert r.mean_range == pytest.approx(0.35)


# --- custom params ---------------------------------------------------------


def test_custom_threshold_flags_stable_as_unstable() -> None:
    base = [_set("m1", "t1", 0.8, 0.85)]
    assert measure_bench_stability(base).verdict == "stable"
    assert (
        measure_bench_stability(base, instability_threshold=0.01).verdict
        == "unstable"
    )


def test_custom_min_runs() -> None:
    # With min_runs=3, a 2-run pair becomes unmeasurable.
    r = measure_bench_stability([_set("m1", "t1", 0.8, 0.2)], min_runs=3)
    assert r.verdict == "unknown"
    assert r.unmeasurable_pair_count == 1


# --- validation ------------------------------------------------------------


def test_invalid_min_runs_below_two() -> None:
    with pytest.raises(ValueError, match="min_runs"):
        measure_bench_stability([], min_runs=1)


def test_invalid_threshold_zero() -> None:
    with pytest.raises(ValueError, match="instability_threshold"):
        measure_bench_stability([], instability_threshold=0.0)


def test_invalid_threshold_over_one() -> None:
    with pytest.raises(ValueError, match="instability_threshold"):
        measure_bench_stability([], instability_threshold=1.5)


def test_invalid_score_negative() -> None:
    with pytest.raises(ValueError, match="outside"):
        measure_bench_stability([_set("m1", "t1", -0.1, 0.5)])


def test_invalid_score_over_one() -> None:
    with pytest.raises(ValueError, match="outside"):
        measure_bench_stability([_set("m1", "t1", 1.2, 0.5)])


def test_nan_score_rejected() -> None:
    with pytest.raises(ValueError, match="NaN"):
        measure_bench_stability([_set("m1", "t1", float("nan"), 0.5)])


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_bench_stability([_set("m1", "t1", 0.8, 0.8)])
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]


# --- orthogonal-to-discrimination (documented in a test) ------------------


def test_reproducible_but_uniform_is_stable() -> None:
    # Every model scores 0.5 every run — reproducible (stable) though it fails
    # to discriminate. Proves stability != discrimination (orthogonal axes).
    r = measure_bench_stability(
        [_set("m1", "t1", 0.5, 0.5), _set("m2", "t1", 0.5, 0.5)]
    )
    assert r.verdict == "stable"
    assert r.max_range == pytest.approx(0.0)

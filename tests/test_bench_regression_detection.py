"""Tests for the Antiek-bench regression-detection axis (ask #11).

The guardrail for the recursive benchmark rewrite: did a rewrite silently make a
previously-strong model score worse on a task? Exercises held/regressing/unknown
verdicts, the strict tolerance boundary, regression rate, mean/worst delta, the
model/task slicings of regressions, validation, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.bench_regression_detection import (
    RegressionDetectionError,
    ScoreTransition,
    measure_regression,
)

# --- unknown (no transitions) --------------------------------------------


def test_unknown_when_no_transitions() -> None:
    r = measure_regression([])
    assert r.verdict == "unknown"
    assert r.transition_count == 0
    assert r.regression_count == 0
    assert r.regression_rate is None
    assert r.mean_delta is None
    assert r.worst_transition_delta is None
    assert r.regressed_models == ()
    assert r.regressed_tasks == ()
    assert r.authority == "advisory"


# --- held (no regressions) -----------------------------------------------


def test_held_when_every_pair_improves() -> None:
    transitions = [
        ScoreTransition("m1", "t1", 0.50, 0.60),
        ScoreTransition("m2", "t1", 0.40, 0.55),
    ]
    r = measure_regression(transitions)
    assert r.verdict == "held"
    assert r.regression_count == 0
    assert r.regression_rate == 0.0
    # deltas +0.10, +0.15 -> mean 0.125, worst 0.10.
    assert r.mean_delta == pytest.approx(0.125)
    assert r.worst_transition_delta == pytest.approx(0.10)


def test_held_when_drop_within_tolerance() -> None:
    # drop 0.03 <= default tolerance 0.05 -> within noise, not a regression.
    r = measure_regression([ScoreTransition("m1", "t1", 0.80, 0.77)])
    assert r.verdict == "held"
    assert r.regression_count == 0
    assert r.worst_transition_delta == pytest.approx(-0.03)


def test_held_at_exact_tolerance_boundary() -> None:
    # drop exactly equals tolerance (same float value) -> strict inequality -> held.
    # (0.80 - 0.75 is not exactly 0.05 in float, so tolerance is set to the
    # computed drop to make the boundary representation-exact.)
    drop = 0.80 - 0.75
    r = measure_regression(
        [ScoreTransition("m1", "t1", 0.80, 0.75)], tolerance=drop
    )
    assert r.verdict == "held"
    assert r.regression_count == 0


# --- regressing -----------------------------------------------------------


def test_regressing_just_beyond_tolerance() -> None:
    # drop 0.051 > 0.05 -> regression.
    r = measure_regression([ScoreTransition("m1", "t1", 0.80, 0.749)])
    assert r.verdict == "regressing"
    assert r.regression_count == 1
    assert r.regression_rate == 1.0
    assert r.worst_transition_delta == pytest.approx(-0.051)
    assert r.regressed_models == ("m1",)
    assert r.regressed_tasks == ("t1",)


def test_regressing_mixed_set_counts_only_real_drops() -> None:
    transitions = [
        ScoreTransition("m1", "t1", 0.50, 0.60),  # +0.10 improve
        ScoreTransition("m2", "t2", 0.80, 0.70),  # -0.10 regression
        ScoreTransition("m3", "t1", 0.40, 0.42),  # +0.02 improve
    ]
    r = measure_regression(transitions)
    assert r.verdict == "regressing"
    assert r.regression_count == 1
    assert r.regression_rate == pytest.approx(1 / 3)
    # deltas 0.10, -0.10, 0.02 -> mean 0.02/3, worst -0.10.
    assert r.mean_delta == pytest.approx(0.02 / 3)
    assert r.worst_transition_delta == pytest.approx(-0.10)
    assert r.regressed_models == ("m2",)
    assert r.regressed_tasks == ("t2",)


def test_regression_rate_half() -> None:
    transitions = [
        ScoreTransition("m1", "t1", 0.80, 0.70),  # reg
        ScoreTransition("m2", "t2", 0.80, 0.70),  # reg
        ScoreTransition("m3", "t3", 0.50, 0.60),  # improve
        ScoreTransition("m4", "t4", 0.50, 0.55),  # improve
    ]
    r = measure_regression(transitions)
    assert r.verdict == "regressing"
    assert r.regression_count == 2
    assert r.regression_rate == 0.5
    # deltas -0.10, -0.10, 0.10, 0.05 -> mean -0.05/4 = -0.0125, worst -0.10.
    assert r.mean_delta == pytest.approx(-0.0125)
    assert r.worst_transition_delta == pytest.approx(-0.10)
    assert r.regressed_models == ("m1", "m2")
    assert r.regressed_tasks == ("t1", "t2")


def test_regressed_sets_dedupe_one_model_many_tasks() -> None:
    transitions = [
        ScoreTransition("m1", "t1", 0.80, 0.70),  # reg
        ScoreTransition("m1", "t2", 0.80, 0.70),  # reg
    ]
    r = measure_regression(transitions)
    assert r.verdict == "regressing"
    assert r.regression_count == 2
    assert r.regression_rate == 1.0
    assert r.regressed_models == ("m1",)
    assert r.regressed_tasks == ("t1", "t2")


def test_regressed_sets_dedupe_one_task_many_models() -> None:
    transitions = [
        ScoreTransition("m1", "t9", 0.80, 0.70),  # reg
        ScoreTransition("m2", "t9", 0.80, 0.70),  # reg
        ScoreTransition("m3", "t9", 0.50, 0.60),  # improve
    ]
    r = measure_regression(transitions)
    assert r.regressed_models == ("m1", "m2")
    assert r.regressed_tasks == ("t9",)


# --- custom tolerance -----------------------------------------------------


def test_zero_tolerance_flags_any_drop() -> None:
    # tolerance 0 -> any strictly-negative delta is a regression.
    r = measure_regression([ScoreTransition("m1", "t1", 0.50, 0.499)], tolerance=0.0)
    assert r.verdict == "regressing"
    assert r.regression_count == 1


def test_zero_tolerance_no_drop_is_held() -> None:
    # delta exactly 0 with tolerance 0 -> 0 > 0 is False -> held.
    r = measure_regression([ScoreTransition("m1", "t1", 0.50, 0.50)], tolerance=0.0)
    assert r.verdict == "held"
    assert r.regression_count == 0


def test_wider_tolerance_absorbs_a_drop() -> None:
    # drop 0.10 is a regression at tolerance 0.05 but held at tolerance 0.20.
    r_default = measure_regression([ScoreTransition("m1", "t1", 0.80, 0.70)])
    assert r_default.verdict == "regressing"
    r_loose = measure_regression(
        [ScoreTransition("m1", "t1", 0.80, 0.70)], tolerance=0.20
    )
    assert r_loose.verdict == "held"
    assert r_loose.tolerance == 0.20


# --- validation -----------------------------------------------------------


def test_negative_tolerance_raises() -> None:
    with pytest.raises(RegressionDetectionError):
        measure_regression([ScoreTransition("m1", "t1", 0.5, 0.5)], tolerance=-0.01)


def test_score_above_one_raises() -> None:
    with pytest.raises(RegressionDetectionError):
        measure_regression([ScoreTransition("m1", "t1", 0.5, 1.5)])


def test_score_below_zero_raises() -> None:
    with pytest.raises(RegressionDetectionError):
        measure_regression([ScoreTransition("m1", "t1", -0.1, 0.5)])


def test_non_finite_score_raises() -> None:
    with pytest.raises(RegressionDetectionError):
        measure_regression([ScoreTransition("m1", "t1", float("nan"), 0.5)])
    with pytest.raises(RegressionDetectionError):
        measure_regression([ScoreTransition("m1", "t1", 0.5, float("inf"))])


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    transitions = [
        ScoreTransition("m1", "t1", 0.80, 0.70),
        ScoreTransition("m2", "t2", 0.40, 0.55),
    ]
    assert measure_regression(transitions) == measure_regression(transitions)


def test_report_is_frozen_immutable() -> None:
    r = measure_regression([ScoreTransition("m1", "t1", 0.5, 0.6)])
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "regressing"  # type: ignore[misc]


def test_worst_delta_positive_when_all_improve() -> None:
    # worst_transition_delta is signed; positive when every transition improved.
    transitions = [ScoreTransition("m1", "t1", 0.50, 0.80)]
    r = measure_regression(transitions)
    assert r.verdict == "held"
    assert r.worst_transition_delta is not None
    assert r.worst_transition_delta == pytest.approx(0.30)
    assert r.worst_transition_delta > 0.0



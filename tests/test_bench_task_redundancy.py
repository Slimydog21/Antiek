"""Tests for the Antiek-bench task-redundancy axis (ask #11).

Measures whether benchmark sub-tasks redundantly measure the same capability
(strong positive inter-task correlation) or differentiate (distinct
capabilities). Exercises differentiating/redundant/unknown verdicts, the
positive-correlation-only rule (anti-correlated pairs are kept), Pearson math,
zero-variance degenerate exclusion, min_overlap gating, validation,
purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.bench_task_redundancy import (
    RedundantTaskPair,
    TaskRedundancyError,
    TaskScore,
    measure_task_redundancy,
)


def sc(rows: list[tuple[str, str, float]]) -> list[TaskScore]:
    return [TaskScore(model_id=m, task_id=t, score=s) for m, t, s in rows]


# --- unknown (no computable pairs) ----------------------------------------


def test_unknown_when_no_scores() -> None:
    r = measure_task_redundancy([])
    assert r.verdict == "unknown"
    assert r.task_count == 0
    assert r.pair_count == 0
    assert r.max_correlation is None
    assert r.mean_correlation is None
    assert r.redundant_pairs == ()
    assert r.authority == "advisory"


def test_unknown_when_single_task() -> None:
    r = measure_task_redundancy(sc([("m1", "t1", 0.5), ("m2", "t1", 0.6)]))
    assert r.verdict == "unknown"
    assert r.pair_count == 0


def test_unknown_when_insufficient_shared_models() -> None:
    # Two tasks but only 2 shared models (< default min_overlap 3).
    r = measure_task_redundancy(
        sc([("m1", "t1", 0.5), ("m2", "t1", 0.6), ("m1", "t2", 0.4), ("m2", "t2", 0.7)])
    )
    assert r.verdict == "unknown"
    assert r.pair_count == 0


# --- differentiating ------------------------------------------------------


def test_differentiating_uncorrelated_tasks() -> None:
    # A and B have low correlation (-0.5) -> differentiating.
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.2),
            ("m2", "A", 0.5), ("m2", "B", 0.8),
            ("m3", "A", 0.1), ("m3", "B", 0.5),
        ]
    )
    r = measure_task_redundancy(scores)
    assert r.verdict == "differentiating"
    assert r.pair_count == 1
    assert r.redundant_pairs == ()
    assert r.max_correlation == pytest.approx(-0.5)


def test_differentiating_anti_correlated_tasks_are_kept() -> None:
    # Perfect anti-correlation (r = -1.0) measures DIFFERENT capabilities -> kept.
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.1),
            ("m2", "A", 0.5), ("m2", "B", 0.5),
            ("m3", "A", 0.1), ("m3", "B", 0.9),
        ]
    )
    r = measure_task_redundancy(scores)
    assert r.verdict == "differentiating"
    assert r.redundant_pairs == ()
    assert r.max_correlation == pytest.approx(-1.0)


def test_differentiating_moderate_positive_below_threshold() -> None:
    # r around 0.3-0.4 -> below 0.85 default -> differentiating.
    scores = sc(
        [
            ("m1", "A", 0.8), ("m1", "B", 0.7),
            ("m2", "A", 0.6), ("m2", "B", 0.4),
            ("m3", "A", 0.3), ("m3", "B", 0.5),
            ("m4", "A", 0.1), ("m4", "B", 0.2),
        ]
    )
    r = measure_task_redundancy(scores)
    assert r.verdict == "differentiating"
    assert r.redundant_pairs == ()
    assert r.max_correlation is not None
    assert r.max_correlation < 0.85


# --- redundant ------------------------------------------------------------


def test_redundant_strong_positive_correlation() -> None:
    # A and B near-perfectly positively correlated (r ≈ 0.997) -> redundant.
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.85),
            ("m2", "A", 0.5), ("m2", "B", 0.45),
            ("m3", "A", 0.1), ("m3", "B", 0.15),
        ]
    )
    r = measure_task_redundancy(scores)
    assert r.verdict == "redundant"
    assert len(r.redundant_pairs) == 1
    pair = r.redundant_pairs[0]
    assert pair.task_a_id == "A"
    assert pair.task_b_id == "B"
    assert pair.correlation == pytest.approx(0.9966, abs=0.01)
    assert pair.shared_model_count == 3
    assert r.redundant_task_ids == ("A", "B")


def test_redundant_mixed_matrix_flags_only_redundant_pair() -> None:
    # 3 tasks: A-B redundant, A-C and B-C differentiating.
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.88), ("m1", "C", 0.1),
            ("m2", "A", 0.5), ("m2", "B", 0.52), ("m2", "C", 0.9),
            ("m3", "A", 0.1), ("m3", "B", 0.12), ("m3", "C", 0.5),
            ("m4", "A", 0.7), ("m4", "B", 0.68), ("m4", "C", 0.3),
        ]
    )
    r = measure_task_redundancy(scores)
    assert r.verdict == "redundant"
    assert r.pair_count == 3  # all 3 pairs computable
    # Only the A-B pair should be redundant (strong positive).
    ab = [p for p in r.redundant_pairs if {p.task_a_id, p.task_b_id} == {"A", "B"}]
    assert len(ab) == 1
    assert r.redundant_task_ids == ("A", "B")


# --- zero-variance degenerate exclusion -----------------------------------


def test_zero_variance_task_pair_excluded() -> None:
    # Task Z: all models score 0.5 (zero variance) -> pair excluded, not counted.
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "Z", 0.5),
            ("m2", "A", 0.5), ("m2", "Z", 0.5),
            ("m3", "A", 0.1), ("m3", "Z", 0.5),
        ]
    )
    r = measure_task_redundancy(scores)
    # The A-Z pair is excluded (Z has zero variance); no computable pairs remain.
    assert r.pair_count == 0
    assert r.verdict == "unknown"


# --- custom thresholds ----------------------------------------------------


def test_custom_min_overlap_allows_two_model_pairs() -> None:
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.9),
            ("m2", "A", 0.1), ("m2", "B", 0.1),
        ]
    )
    # Default min_overlap 3 -> unknown; min_overlap 2 -> computable (r=1.0 redundant).
    r_default = measure_task_redundancy(scores)
    assert r_default.verdict == "unknown"
    r2 = measure_task_redundancy(scores, min_overlap=2)
    assert r2.verdict == "redundant"
    assert r2.min_overlap == 2


def test_custom_redundancy_threshold() -> None:
    # r ≈ 0.997 with default threshold 0.85 -> redundant; threshold 0.999 -> differentiating.
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.85),
            ("m2", "A", 0.5), ("m2", "B", 0.45),
            ("m3", "A", 0.1), ("m3", "B", 0.15),
        ]
    )
    r_default = measure_task_redundancy(scores)
    assert r_default.verdict == "redundant"
    r_strict = measure_task_redundancy(scores, redundancy_threshold=0.999)
    assert r_strict.verdict == "differentiating"
    assert r_strict.redundancy_threshold == 0.999


# --- validation -----------------------------------------------------------


def test_invalid_min_overlap_raises() -> None:
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy([], min_overlap=1)


def test_invalid_threshold_raises() -> None:
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy([], redundancy_threshold=0.0)
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy([], redundancy_threshold=1.01)


def test_score_out_of_range_raises() -> None:
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy(sc([("m1", "t1", 1.5)]))
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy(sc([("m1", "t1", -0.1)]))


def test_non_finite_score_raises() -> None:
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy([TaskScore("m1", "t1", float("nan"))])
    with pytest.raises(TaskRedundancyError):
        measure_task_redundancy([TaskScore("m1", "t1", float("inf"))])


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.85),
            ("m2", "A", 0.5), ("m2", "B", 0.45),
            ("m3", "A", 0.1), ("m3", "B", 0.15),
        ]
    )
    assert measure_task_redundancy(scores) == measure_task_redundancy(scores)


def test_report_is_frozen_immutable() -> None:
    r = measure_task_redundancy(sc([("m1", "A", 0.5), ("m2", "A", 0.6)]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "redundant"  # type: ignore[misc]


def test_redundant_pair_dataclass_is_frozen() -> None:
    pair = RedundantTaskPair(task_a_id="A", task_b_id="B", correlation=0.9, shared_model_count=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.correlation = 0.5  # type: ignore[misc]


def test_mean_correlation_carried() -> None:
    scores = sc(
        [
            ("m1", "A", 0.9), ("m1", "B", 0.85),
            ("m2", "A", 0.5), ("m2", "B", 0.45),
            ("m3", "A", 0.1), ("m3", "B", 0.15),
        ]
    )
    r = measure_task_redundancy(scores)
    assert r.mean_correlation is not None
    assert r.mean_correlation == pytest.approx(0.9966, abs=0.01)

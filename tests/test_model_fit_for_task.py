"""Tests for the model-fit-for-task axis (asks #8/#9/#10).

Pure arithmetic — every rank/gap computed by hand from simple float scores.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.model_fit_for_task import (
    ModelFitError,
    ModelTaskScore,
    measure_model_fit_for_task,
)

T = "deep_research"


def _rows(*pairs: tuple[str, float], task: str = T) -> list[ModelTaskScore]:
    return [ModelTaskScore(model_id=m, task_id=task, score=s) for m, s in pairs]


# --- verdicts ---------------------------------------------------------------


def test_optimal_fit_chosen_is_top() -> None:
    rows = _rows(("A", 1.0), ("B", 0.9), ("C", 0.8))
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "optimal_fit"
    assert report.chosen_score == 1.0
    assert report.best_score == 1.0
    assert report.chosen_rank == 1
    assert report.rank_ratio == 1.0
    assert report.relative_gap == 0.0
    assert report.scored_model_count == 3
    assert report.authority == "advisory"


def test_near_optimal_at_tolerance_boundary_is_a_hit() -> None:
    # gap = (1.0 - 0.9)/1.0 = 0.10 == tolerance 0.10 -> near_optimal (>= boundary).
    rows = _rows(("A", 1.0), ("B", 0.9), ("C", 0.8))
    report = measure_model_fit_for_task("B", T, rows)
    assert report.verdict == "near_optimal"
    assert report.relative_gap == pytest.approx(0.10)
    assert report.chosen_rank == 2
    assert report.rank_ratio == pytest.approx(0.5)


def test_near_optimal_within_band() -> None:
    # gap = (1.0 - 0.95)/1.0 = 0.05 < 0.10 -> near_optimal.
    rows = _rows(("A", 1.0), ("B", 0.95), ("C", 0.8))
    report = measure_model_fit_for_task("B", T, rows)
    assert report.verdict == "near_optimal"
    assert report.relative_gap == pytest.approx(0.05)


def test_suboptimal_fit_leaves_performance_on_table() -> None:
    # gap = (1.0 - 0.8)/1.0 = 0.20 > 0.10 -> suboptimal_fit.
    rows = _rows(("A", 1.0), ("B", 0.9), ("C", 0.8))
    report = measure_model_fit_for_task("C", T, rows)
    assert report.verdict == "suboptimal_fit"
    assert report.relative_gap == pytest.approx(0.20)
    assert report.chosen_rank == 3
    assert report.rank_ratio == 0.0


def test_worst_pick_rank_ratio_zero() -> None:
    rows = _rows(("A", 1.0), ("B", 0.5))
    report = measure_model_fit_for_task("B", T, rows)
    assert report.verdict == "suboptimal_fit"
    assert report.chosen_rank == 2
    assert report.rank_ratio == 0.0
    assert report.relative_gap == pytest.approx(0.5)


def test_best_pick_rank_ratio_one() -> None:
    rows = _rows(("A", 1.0), ("B", 0.5))
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "optimal_fit"
    assert report.rank_ratio == 1.0


# --- ties (load-bearing) ----------------------------------------------------


def test_tie_at_top_is_optimal() -> None:
    rows = _rows(("A", 0.9), ("B", 0.9), ("C", 0.7))
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "optimal_fit"
    assert report.chosen_rank == 1
    assert report.rank_ratio == 1.0
    assert report.relative_gap == 0.0


def test_tie_at_top_both_models_optimal() -> None:
    rows = _rows(("A", 0.9), ("B", 0.9), ("C", 0.7))
    report_b = measure_model_fit_for_task("B", T, rows)
    assert report_b.verdict == "optimal_fit"
    assert report_b.chosen_rank == 1


def test_tie_non_top_pick_is_suboptimal() -> None:
    rows = _rows(("A", 0.9), ("B", 0.9), ("C", 0.7))
    report = measure_model_fit_for_task("C", T, rows)
    # gap = (0.9 - 0.7)/0.9 = 0.222... > 0.10
    assert report.verdict == "suboptimal_fit"
    assert report.chosen_rank == 3


# --- unknown (honesty keystones) --------------------------------------------


def test_unknown_when_no_models_scored_for_task() -> None:
    rows = _rows(("A", 1.0), task="other_task")
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "unknown"
    assert report.scored_model_count == 0
    assert report.chosen_score is None
    assert report.best_score is None
    assert report.chosen_rank is None
    assert report.rank_ratio is None
    assert report.relative_gap is None


def test_unknown_when_chosen_model_unbenchmarked() -> None:
    rows = _rows(("A", 1.0), ("B", 0.9))
    report = measure_model_fit_for_task("C", T, rows)
    assert report.verdict == "unknown"
    assert report.chosen_score is None
    assert report.best_score == 1.0  # carried — the measured baseline among others
    assert report.chosen_rank is None
    assert report.relative_gap is None


def test_unknown_when_single_scored_model() -> None:
    rows = _rows(("A", 0.9))
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "unknown"
    assert report.chosen_score == 0.9
    assert report.best_score == 0.9
    assert report.chosen_rank is None  # no peer to rank against
    assert report.rank_ratio is None
    assert report.relative_gap is None


def test_unknown_when_best_score_is_zero() -> None:
    rows = _rows(("A", 0.0), ("B", 0.0))
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "unknown"
    assert report.chosen_score == 0.0
    assert report.best_score == 0.0
    assert report.relative_gap is None  # division-by-zero deferred, never fabricated


# --- filtering --------------------------------------------------------------


def test_filters_to_task_other_tasks_ignored() -> None:
    rows = [
        ModelTaskScore("A", T, 1.0),
        ModelTaskScore("B", T, 0.8),
        ModelTaskScore("X", "summarize", 1.0),  # other task — ignored
        ModelTaskScore("A", "summarize", 0.5),  # other task — ignored
    ]
    report = measure_model_fit_for_task("A", T, rows)
    assert report.scored_model_count == 2  # only A, B on T
    assert report.verdict == "optimal_fit"


# --- custom tolerance -------------------------------------------------------


def test_custom_tolerance_promotes_near_optimal() -> None:
    # gap = (1.0 - 0.8)/1.0 = 0.20; at default 0.10 -> suboptimal, at 0.25 -> near_optimal.
    rows = _rows(("A", 1.0), ("B", 0.8))
    report_default = measure_model_fit_for_task("B", T, rows)
    assert report_default.verdict == "suboptimal_fit"
    report_wide = measure_model_fit_for_task("B", T, rows, tolerance=0.25)
    assert report_wide.verdict == "near_optimal"
    assert report_wide.tolerance == 0.25


def test_tolerance_zero_only_exact_top_is_optimal() -> None:
    # tolerance 0.0: gap 0 -> optimal, any gap -> suboptimal (no near band).
    rows = _rows(("A", 1.0), ("B", 0.999))
    report = measure_model_fit_for_task("B", T, rows, tolerance=0.0)
    assert report.verdict == "suboptimal_fit"


# --- validation (load-bearing invariants) -----------------------------------


def test_tolerance_out_of_range_raises() -> None:
    rows = _rows(("A", 1.0), ("B", 0.5))
    with pytest.raises(ModelFitError, match="tolerance"):
        measure_model_fit_for_task("A", T, rows, tolerance=1.5)
    with pytest.raises(ModelFitError, match="tolerance"):
        measure_model_fit_for_task("A", T, rows, tolerance=-0.1)


def test_score_out_of_range_raises() -> None:
    with pytest.raises(ModelFitError, match="must be in \\[0,1\\]"):
        measure_model_fit_for_task("A", T, _rows(("A", 1.5)))
    with pytest.raises(ModelFitError, match="must be in \\[0,1\\]"):
        measure_model_fit_for_task("A", T, [ModelTaskScore("A", T, -0.1)])


def test_duplicate_score_for_model_task_raises() -> None:
    rows = [
        ModelTaskScore("A", T, 0.9),
        ModelTaskScore("A", T, 0.8),  # ambiguous duplicate
        ModelTaskScore("B", T, 0.5),
    ]
    with pytest.raises(ModelFitError, match="duplicate score"):
        measure_model_fit_for_task("A", T, rows)


def test_duplicate_in_other_task_does_not_raise() -> None:
    # Same model on a DIFFERENT task is not a duplicate (different measurement).
    rows = [
        ModelTaskScore("A", T, 0.9),
        ModelTaskScore("A", "summarize", 0.8),
        ModelTaskScore("B", T, 0.5),
    ]
    report = measure_model_fit_for_task("A", T, rows)
    assert report.verdict == "optimal_fit"


def test_empty_chosen_model_raises() -> None:
    with pytest.raises(ModelFitError, match="chosen_model"):
        measure_model_fit_for_task("", T, _rows(("A", 0.9), ("B", 0.5)))


def test_empty_task_id_raises() -> None:
    with pytest.raises(ModelFitError, match="task_id"):
        measure_model_fit_for_task("A", "  ", _rows(("A", 0.9)))


def test_empty_model_id_in_row_raises() -> None:
    with pytest.raises(ModelFitError, match="model_id"):
        measure_model_fit_for_task("A", T, [ModelTaskScore("  ", T, 0.5), ModelTaskScore("B", T, 0.5)])


def test_empty_task_id_in_row_raises() -> None:
    with pytest.raises(ModelFitError, match="task_id"):
        measure_model_fit_for_task("A", T, [ModelTaskScore("A", "", 0.5), ModelTaskScore("B", T, 0.5)])


# --- purity / determinism ---------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_model_fit_for_task("A", T, _rows(("A", 1.0), ("B", 0.5)))
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    rows = _rows(("A", 1.0), ("B", 0.5), ("C", 0.3))
    first = measure_model_fit_for_task("B", T, rows)
    second = measure_model_fit_for_task("B", T, rows)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_model_fit_for_task("A", T, _rows(("A", 1.0), ("B", 0.5)))
    joined = " ".join(report.notes)
    assert "model-fit-for-task" in joined
    assert "verdict optimal_fit" in joined
    assert "rank 1 of 2" in joined

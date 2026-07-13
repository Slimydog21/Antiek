"""Tests for the open-question closure axis (artifact convergence — ask #1).

Pure count arithmetic — resolved/total ratios computed by hand.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.open_question_closure import (
    OpenQuestion,
    OpenQuestionClosureError,
    measure_open_question_closure,
)


def qs(*ids: str, resolved: tuple[str, ...] = ()) -> list[OpenQuestion]:
    return [OpenQuestion(question_id=i, resolved=(i in resolved)) for i in ids]


# --- verdicts ---------------------------------------------------------------


def test_converging_above_threshold() -> None:
    # 6 of 10 resolved -> 0.60 == converged_threshold -> converging (>= boundary).
    report = measure_open_question_closure(qs(*(f"q{i}" for i in range(10)), resolved=tuple(f"q{i}" for i in range(6))))
    assert report.verdict == "converging"
    assert report.closure_rate == pytest.approx(0.60)
    assert report.resolved_count == 6
    assert report.open_count == 4
    assert report.authority == "advisory"


def test_converging_strong() -> None:
    report = measure_open_question_closure(qs("a", "b", "c", resolved=("a", "b", "c")))
    assert report.verdict == "converging"
    assert report.closure_rate == 1.0


def test_partial_between_thresholds() -> None:
    # 4 of 10 -> 0.40 (between 0.20 and 0.60) -> partial.
    report = measure_open_question_closure(qs(*(f"q{i}" for i in range(10)), resolved=("q0", "q1", "q2", "q3")))
    assert report.verdict == "partial"
    assert report.closure_rate == pytest.approx(0.40)


def test_stalled_at_threshold_boundary_is_a_hit() -> None:
    # 2 of 10 -> 0.20 == stalled_threshold -> stalled (<= boundary).
    report = measure_open_question_closure(qs(*(f"q{i}" for i in range(10)), resolved=("q0", "q1")))
    assert report.verdict == "stalled"
    assert report.closure_rate == pytest.approx(0.20)


def test_stalled_none_resolved() -> None:
    report = measure_open_question_closure(qs("a", "b", "c", resolved=()))
    assert report.verdict == "stalled"
    assert report.closure_rate == 0.0
    assert report.resolved_count == 0
    assert report.open_count == 3


# --- the load-bearing distinction: stalled(0.0) != unknown -----------------


def test_stalled_zero_rate_is_not_unknown() -> None:
    # Questions recorded, none resolved -> stalled (measured), NOT unknown.
    report = measure_open_question_closure(qs("a", "b", resolved=()))
    assert report.verdict == "stalled"
    assert report.closure_rate == 0.0  # real measured value, not None


# --- unknown (load-bearing: not converged-by-default) ---------------------


def test_unknown_when_no_questions() -> None:
    report = measure_open_question_closure([])
    assert report.verdict == "unknown"
    assert report.total_questions == 0
    assert report.closure_rate is None  # defer, never 0.0


# --- custom thresholds -----------------------------------------------------


def test_custom_converged_threshold() -> None:
    # 4 of 10 = 0.40 -> partial at default 0.60, converging at threshold 0.30.
    questions = qs(*(f"q{i}" for i in range(10)), resolved=("q0", "q1", "q2", "q3"))
    assert measure_open_question_closure(questions).verdict == "partial"
    assert measure_open_question_closure(questions, converged_threshold=0.30).verdict == "converging"


def test_custom_stalled_threshold() -> None:
    # 3 of 10 = 0.30 -> partial at default 0.20, stalled at threshold 0.35.
    questions = qs(*(f"q{i}" for i in range(10)), resolved=("q0", "q1", "q2"))
    assert measure_open_question_closure(questions).verdict == "partial"
    assert measure_open_question_closure(questions, stalled_threshold=0.35).verdict == "stalled"


def test_converged_at_one_stalled_at_zero_extremes() -> None:
    # With default thresholds, all-resolved -> converging, none-resolved -> stalled.
    all_resolved = measure_open_question_closure(qs("a", "b", resolved=("a", "b")))
    assert all_resolved.verdict == "converging"
    none_resolved = measure_open_question_closure(qs("a", "b", resolved=()))
    assert none_resolved.verdict == "stalled"


def test_stalled_above_converged_threshold_raises() -> None:
    with pytest.raises(OpenQuestionClosureError, match="cannot exceed"):
        measure_open_question_closure(
            qs("a"), converged_threshold=0.10, stalled_threshold=0.50,
        )


# --- validation -----------------------------------------------------------


def test_converged_threshold_out_of_range_raises() -> None:
    with pytest.raises(OpenQuestionClosureError, match="converged_threshold"):
        measure_open_question_closure([], converged_threshold=1.5)


def test_stalled_threshold_out_of_range_raises() -> None:
    with pytest.raises(OpenQuestionClosureError, match="stalled_threshold"):
        measure_open_question_closure([], stalled_threshold=-0.1)


def test_empty_question_id_raises() -> None:
    with pytest.raises(OpenQuestionClosureError, match="question_id"):
        measure_open_question_closure([OpenQuestion(question_id="  ", resolved=False)])


def test_duplicate_question_id_raises() -> None:
    with pytest.raises(OpenQuestionClosureError, match="duplicate question_id"):
        measure_open_question_closure([
            OpenQuestion(question_id="a", resolved=True),
            OpenQuestion(question_id="a", resolved=False),
        ])


# --- purity / determinism -------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_open_question_closure(qs("a", "b", resolved=("a",)))
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    questions = qs("a", "b", "c", resolved=("a", "b"))
    first = measure_open_question_closure(questions)
    second = measure_open_question_closure(questions)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_open_question_closure(qs("a", "b", resolved=("a",)))
    joined = " ".join(report.notes)
    assert "open-question closure" in joined
    assert "verdict partial" in joined

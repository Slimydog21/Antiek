"""Tests for the task-discrimination axis (benchmark recursion meta-quality, ask #11).

Exercises: discriminates/trivial/impossible/unattempted/insufficient_sample verdicts,
pass-rate math, passes_all/fails_all flags, min_attempts floor, purity/immutability,
validation. Fixtures use explicit boolean tuples so rates are exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.antiek_bench.task_discrimination import (
    TaskDiscriminationError,
    TaskDiscriminationReport,
    measure_task_discrimination,
)

# --- core: discriminates (mixed split, enough attempts) --------------------


def test_discriminates_even_split() -> None:
    # 2 pass, 2 fail -> pass_rate 0.5 -> discriminates (max signal)
    report = measure_task_discrimination("task-1", (True, True, False, False))
    assert report.pass_rate == pytest.approx(0.5)
    assert report.discrimination == "discriminates"
    assert report.pass_count == 2
    assert report.fail_count == 2
    assert report.passes_all is False
    assert report.fails_all is False


def test_discriminates_asymmetric_split() -> None:
    # 3 pass, 1 fail -> pass_rate 0.75 -> still discriminates (>=2 attempts, mixed)
    report = measure_task_discrimination("task-2", (True, True, True, False))
    assert report.pass_rate == pytest.approx(0.75)
    assert report.discrimination == "discriminates"


def test_discriminates_one_failure() -> None:
    # 2 attempts (== min default 2), 1 pass 1 fail -> discriminates
    report = measure_task_discrimination("task-3", (True, False))
    assert report.discrimination == "discriminates"
    assert report.pass_rate == pytest.approx(0.5)


# --- core: trivial (all pass) ---------------------------------------------


def test_trivial_all_pass() -> None:
    report = measure_task_discrimination("task-4", (True, True, True))
    assert report.pass_rate == pytest.approx(1.0)
    assert report.discrimination == "trivial"
    assert report.passes_all is True
    assert report.fails_all is False


def test_trivial_single_pass() -> None:
    # 1 of 1 pass -> trivial (one data point cannot prove separation)
    report = measure_task_discrimination("task-5", (True,))
    assert report.pass_rate == pytest.approx(1.0)
    assert report.discrimination == "trivial"


# --- core: impossible (all fail) ------------------------------------------


def test_impossible_all_fail() -> None:
    report = measure_task_discrimination("task-6", (False, False, False))
    assert report.pass_rate == pytest.approx(0.0)
    assert report.discrimination == "impossible"
    assert report.fails_all is True
    assert report.passes_all is False


def test_impossible_single_fail() -> None:
    report = measure_task_discrimination("task-7", (False,))
    assert report.pass_rate == pytest.approx(0.0)
    assert report.discrimination == "impossible"


# --- honesty: unattempted -------------------------------------------------


def test_unattempted_no_outcomes() -> None:
    report = measure_task_discrimination("task-8", ())
    assert report.pass_rate is None
    assert report.discrimination == "unattempted"
    assert report.attempt_count == 0
    assert report.pass_count == 0
    assert report.fail_count == 0
    assert report.passes_all is False
    assert report.fails_all is False


# --- honesty: insufficient sample (mixed but < min_attempts) ---------------


def test_insufficient_sample_default_min() -> None:
    # default min_attempts=2; a single mixed outcome is impossible structurally
    # (1 attempt is either all-pass or all-fail). So test with min_attempts=3.
    report = measure_task_discrimination(
        "task-9", (True, False), min_attempts=3
    )
    # 2 attempts < 3, mixed -> insufficient_sample
    assert report.discrimination == "insufficient_sample"
    assert report.pass_rate == pytest.approx(0.5)  # raw signal still honest


def test_insufficient_sample_keeps_pass_rate() -> None:
    report = measure_task_discrimination("task-10", (True, True, False), min_attempts=5)
    assert report.discrimination == "insufficient_sample"
    assert report.pass_rate == pytest.approx(2 / 3)


def test_min_attempts_one_allows_single_outcome_discriminates_impossible() -> None:
    # min_attempts=1: a single pass is trivial, single fail impossible (never discriminates)
    assert measure_task_discrimination("a", (True,), min_attempts=1).discrimination == "trivial"
    assert measure_task_discrimination("b", (False,), min_attempts=1).discrimination == "impossible"
    # 2 mixed still discriminates at min 1
    assert measure_task_discrimination("c", (True, False), min_attempts=1).discrimination == "discriminates"


# --- custom min_attempts changes the discriminating floor ------------------


def test_higher_min_attempts_demands_more_evidence() -> None:
    # 2 attempts mixed: discriminates at min=2, insufficient at min=3
    outcomes = (True, False)
    assert measure_task_discrimination("t", outcomes, min_attempts=2).discrimination == "discriminates"
    assert measure_task_discrimination("t", outcomes, min_attempts=3).discrimination == "insufficient_sample"


# --- pass-rate range + invariant ------------------------------------------


def test_pass_rate_in_unit_interval() -> None:
    for outcomes in [(True, True, False), (True,), (False, False), ()]:
        report = measure_task_discrimination("t", outcomes)
        if report.pass_rate is not None:
            assert 0.0 <= report.pass_rate <= 1.0


def test_pass_plus_fail_equals_attempts() -> None:
    outcomes = (True, False, True, True, False)
    report = measure_task_discrimination("t", outcomes)
    assert report.pass_count + report.fail_count == report.attempt_count == 5


# --- provenance / purity ---------------------------------------------------


def test_task_id_carried_through() -> None:
    report = measure_task_discrimination("task-xyz", (True, False))
    assert report.task_id == "task-xyz"


def test_authority_is_always_advisory() -> None:
    assert measure_task_discrimination("t", (True, False)).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_task_discrimination("t", (True, False))
    assert isinstance(report, TaskDiscriminationReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.pass_rate = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    outcomes = (True, False, True)
    assert measure_task_discrimination("t", outcomes) == measure_task_discrimination("t", outcomes)


def test_notes_describe_verdict() -> None:
    report = measure_task_discrimination("t", (True, False))
    joined = " | ".join(report.notes).lower()
    assert "discriminat" in joined or "trivial" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -5])
def test_validation_rejects_bad_min_attempts(bad: int) -> None:
    with pytest.raises(TaskDiscriminationError, match="min_attempts"):
        measure_task_discrimination("t", (True,), min_attempts=bad)


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.antiek_bench import task_discrimination as mod

    assert set(mod.__all__) == {
        "TaskDiscriminationError",
        "TaskDiscriminationReport",
        "measure_task_discrimination",
    }
    assert issubclass(mod.TaskDiscriminationError, ValueError)
    assert dataclasses.is_dataclass(mod.TaskDiscriminationReport)

"""Tests for the bench task-novelty axis (ask #11).

Every fixture is hand-counted: novelty rates, ages, and verdicts are verified by
inspection before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.bench_task_novelty import (
    BenchTaskNoveltyReport,
    TaskAge,
    measure_bench_task_novelty,
)

# ---------------------------------------------------------------------------
# Base cases — unknown when no current tasks or no prior history.
# ---------------------------------------------------------------------------


def test_no_current_tasks_is_unknown() -> None:
    report = measure_bench_task_novelty([], [["t1", "t2"]])
    assert report.verdict == "unknown"
    assert report.novelty_rate is None
    assert report.new_task_count is None
    assert report.task_ages == ()
    assert report.authority == "advisory"


def test_no_prior_history_is_unknown() -> None:
    # First week — nothing to compare against. Every task is trivially "new".
    report = measure_bench_task_novelty(["t1", "t2"], [])
    assert report.verdict == "unknown"
    assert report.novelty_rate is None
    assert report.prior_history_count == 0


def test_both_empty_is_unknown() -> None:
    report = measure_bench_task_novelty([], [])
    assert report.verdict == "unknown"


# ---------------------------------------------------------------------------
# Frozen — all tasks recycled, novelty_rate 0.
# ---------------------------------------------------------------------------


def test_all_recycled_is_frozen() -> None:
    report = measure_bench_task_novelty(
        ["t1", "t2", "t3"], [["t1", "t2", "t3"]]
    )
    assert report.verdict == "frozen"
    assert report.novelty_rate == pytest.approx(0.0)
    assert report.new_task_count == 0
    assert report.recycled_task_count == 3


def test_frozen_with_multi_week_history() -> None:
    # t1 in week 0; t2 in week 1; both still current -> frozen, ages 2 and 1.
    report = measure_bench_task_novelty(["t1", "t2"], [["t1"], ["t2"]])
    assert report.verdict == "frozen"
    assert report.novelty_rate == pytest.approx(0.0)
    assert report.max_task_age_weeks == 2  # t1 first seen in week 0, 2 prior weeks
    assert report.mean_task_age_weeks == pytest.approx(1.5)  # (2+1)/2


# ---------------------------------------------------------------------------
# Stagnant — mostly recycled, some new.
# ---------------------------------------------------------------------------


def test_mostly_recycled_is_stagnant() -> None:
    # 5 tasks: 1 new + 4 recycled -> novelty 0.20 < 0.30 -> stagnant.
    report = measure_bench_task_novelty(
        ["t1", "t2", "t3", "t4", "new1"], [["t1", "t2", "t3", "t4"]]
    )
    assert report.verdict == "stagnant"
    assert report.novelty_rate == pytest.approx(0.20)
    assert report.new_task_count == 1
    assert report.recycled_task_count == 4


# ---------------------------------------------------------------------------
# Evolving — healthy blend.
# ---------------------------------------------------------------------------


def test_healthy_blend_is_evolving() -> None:
    # 5 tasks: 2 new + 3 recycled -> novelty 0.40 >= 0.30 -> evolving.
    report = measure_bench_task_novelty(
        ["t1", "t2", "t3", "new1", "new2"], [["t1", "t2", "t3"]]
    )
    assert report.verdict == "evolving"
    assert report.novelty_rate == pytest.approx(0.40)
    assert report.new_task_count == 2
    assert report.recycled_task_count == 3


# ---------------------------------------------------------------------------
# Fully novel — complete rotation.
# ---------------------------------------------------------------------------


def test_all_new_is_fully_novel() -> None:
    report = measure_bench_task_novelty(
        ["new1", "new2", "new3"], [["old1", "old2"]]
    )
    assert report.verdict == "fully_novel"
    assert report.novelty_rate == pytest.approx(1.0)
    assert report.new_task_count == 3
    assert report.recycled_task_count == 0
    assert report.max_task_age_weeks == 0  # no recycled tasks
    assert report.mean_task_age_weeks == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Full-history age vs pairwise churn (the load-bearing distinction).
# ---------------------------------------------------------------------------


def test_reintroduced_task_is_recycled_not_new() -> None:
    # t1 in week 0, dropped week 1, re-introduced week 2.
    # Pairwise (#1862) would call it "new" (absent last week).
    # Full-history (THIS) correctly calls it recycled (age 2).
    report = measure_bench_task_novelty(["t1", "new1"], [["t1", "old1"], ["old1"]])
    assert report.verdict == "evolving"  # 1 new of 2 = 0.50
    assert "t1" in report.recycled_task_ids
    assert "new1" in report.new_task_ids
    t1_age = next(ta for ta in report.task_ages if ta.task_id == "t1")
    assert t1_age.age_weeks == 2  # first seen week 0, 2 prior weeks
    assert not t1_age.is_new


def test_task_age_increases_across_weeks() -> None:
    # t1 in week 0; current week after 3 prior weeks -> age 3.
    report = measure_bench_task_novelty(
        ["t1", "n1", "n2", "n3"], [["t1"], ["t1"], ["t1"]]
    )
    t1 = next(ta for ta in report.task_ages if ta.task_id == "t1")
    assert t1.age_weeks == 3


# ---------------------------------------------------------------------------
# Per-task auditability.
# ---------------------------------------------------------------------------


def test_task_ages_carry_is_new_flag() -> None:
    report = measure_bench_task_novelty(
        ["t1", "new1"], [["t1"]]
    )
    assert all(isinstance(ta, TaskAge) for ta in report.task_ages)
    new_task = next(ta for ta in report.task_ages if ta.task_id == "new1")
    assert new_task.is_new is True
    assert new_task.age_weeks == 0
    old_task = next(ta for ta in report.task_ages if ta.task_id == "t1")
    assert old_task.is_new is False


def test_new_and_recycled_ids_partition() -> None:
    report = measure_bench_task_novelty(
        ["t1", "t2", "n1", "n2"], [["t1", "t2"]]
    )
    assert sorted(report.new_task_ids) == ["n1", "n2"]
    assert sorted(report.recycled_task_ids) == ["t1", "t2"]
    # partition is complete and disjoint
    assert len(report.new_task_ids) + len(report.recycled_task_ids) == report.current_task_count


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_evolving_threshold_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="evolving_threshold"):
        measure_bench_task_novelty(["t1"], [["t2"]], evolving_threshold=0.0)
    with pytest.raises(ValueError, match="evolving_threshold"):
        measure_bench_task_novelty(["t1"], [["t2"]], evolving_threshold=1.5)


def test_custom_threshold_reclassifies() -> None:
    # novelty 0.20: stagnant at default 0.30, evolving at strict 0.15.
    ids = ["t1", "t2", "t3", "t4", "n1"]
    prior = [["t1", "t2", "t3", "t4"]]
    assert measure_bench_task_novelty(ids, prior).verdict == "stagnant"
    assert (
        measure_bench_task_novelty(ids, prior, evolving_threshold=0.15).verdict
        == "evolving"
    )


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_bench_task_novelty(["t1", "n1"], [["t1"]])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "frozen"  # type: ignore[misc]


def test_deterministic_output() -> None:
    ids = ["n1", "t1", "t2"]
    prior = [["t1", "t2", "x"]]
    assert measure_bench_task_novelty(ids, prior) == measure_bench_task_novelty(ids, prior)


def test_report_is_bench_task_novelty_report_instance() -> None:
    report = measure_bench_task_novelty(["t1", "n1"], [["t1"]])
    assert isinstance(report, BenchTaskNoveltyReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_bench_task_novelty(["t1", "n1", "n2"], [["t1"]])
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)
    assert any("full" in n.lower() and "history" in n.lower() for n in report.notes)


def test_duplicate_current_ids_deduplicated() -> None:
    report = measure_bench_task_novelty(["t1", "t1", "n1"], [["t1"]])
    assert report.current_task_count == 2  # t1 deduped


def test_mean_age_excludes_new_tasks() -> None:
    # 3 recycled (ages 2,2,2) + 1 new -> mean age of recycled only = 2.0.
    report = measure_bench_task_novelty(
        ["t1", "t2", "t3", "n1"], [["t1", "t2", "t3"]]
    )
    assert report.mean_task_age_weeks == pytest.approx(1.0)  # all seen week 0, 1 prior week

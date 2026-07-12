"""Tests for the week-over-week bench diff (ask #11 recursion)."""

from __future__ import annotations

import pytest

from substrate.antiek_bench.week_diff import (
    ScoreDelta,
    WeekDiffError,
    WeeklyModelResult,
    WeekOverWeekDiff,
    WeekSnapshot,
    diff_weeks,
    improvements,
    regressions,
)


def _week(week_id: str, results, incomplete=False) -> WeekSnapshot:
    return WeekSnapshot(week_id=week_id, results=tuple(results), incomplete=incomplete)


def _r(family: str, model: str, score, completed=3) -> WeeklyModelResult:
    return WeeklyModelResult(
        task_family=family, model_id=model, mean_score=score, completed_runs=completed
    )


# --------------------------------------------------------------------------- #
# Invariant #1 — new/dropped never compared against fabricated zero.
# --------------------------------------------------------------------------- #
def test_new_model_direction_new_not_fabricated_delta():
    prev = _week("W01", [_r("exact", "model-a", 0.5)])
    curr = _week("W02", [_r("exact", "model-a", 0.5), _r("exact", "model-b", 0.9)])
    diff = diff_weeks(prev, curr)
    new_entries = [d for d in diff.deltas if d.direction == "new"]
    assert len(new_entries) == 1
    assert new_entries[0].model_id == "model-b"
    assert new_entries[0].delta is None  # never fabricated
    assert diff.new_count == 1


def test_dropped_model_direction_dropped():
    prev = _week("W01", [_r("exact", "model-a", 0.5), _r("exact", "model-b", 0.3)])
    curr = _week("W02", [_r("exact", "model-a", 0.5)])
    diff = diff_weeks(prev, curr)
    dropped = [d for d in diff.deltas if d.direction == "dropped"]
    assert len(dropped) == 1
    assert dropped[0].model_id == "model-b"
    assert dropped[0].delta is None
    assert diff.dropped_count == 1


# --------------------------------------------------------------------------- #
# Invariant #2 — unknown never produces a numeric delta.
# --------------------------------------------------------------------------- #
def test_either_score_none_yields_unknown_direction():
    prev = _week("W01", [_r("exact", "m", None, completed=0)])
    curr = _week("W02", [_r("exact", "m", 0.8)])
    diff = diff_weeks(prev, curr)
    d = diff.deltas[0]
    assert d.direction == "unknown"
    assert d.delta is None
    assert diff.unknown_count == 1


def test_both_none_yields_unknown():
    prev = _week("W01", [_r("exact", "m", None, completed=0)])
    curr = _week("W02", [_r("exact", "m", None, completed=0)])
    diff = diff_weeks(prev, curr)
    assert diff.deltas[0].direction == "unknown"
    assert diff.unknown_count == 1


# --------------------------------------------------------------------------- #
# Invariant #3 — epsilon noise floor.
# --------------------------------------------------------------------------- #
def test_small_delta_within_epsilon_is_unchanged():
    prev = _week("W01", [_r("exact", "m", 0.5)])
    curr = _week("W02", [_r("exact", "m", 0.5 + 1e-12)])
    diff = diff_weeks(prev, curr)
    assert diff.deltas[0].direction == "unchanged"
    assert diff.unchanged_count == 1


def test_custom_epsilon_suppresses_small_movement():
    prev = _week("W01", [_r("exact", "m", 0.50)])
    curr = _week("W02", [_r("exact", "m", 0.52)])
    # epsilon 0.05 -> a 0.02 delta is "unchanged"
    diff = diff_weeks(prev, curr, epsilon=0.05)
    assert diff.deltas[0].direction == "unchanged"
    # default epsilon -> it's "improved"
    diff_default = diff_weeks(prev, curr)
    assert diff_default.deltas[0].direction == "improved"


# --------------------------------------------------------------------------- #
# Direction: improved / regressed.
# --------------------------------------------------------------------------- #
def test_score_increase_is_improved():
    prev = _week("W01", [_r("exact", "m", 0.6)])
    curr = _week("W02", [_r("exact", "m", 0.8)])
    diff = diff_weeks(prev, curr)
    d = diff.deltas[0]
    assert d.direction == "improved"
    assert d.delta == pytest.approx(0.2)
    assert diff.improved_count == 1


def test_score_decrease_is_regressed():
    prev = _week("W01", [_r("exact", "m", 0.8)])
    curr = _week("W02", [_r("exact", "m", 0.5)])
    diff = diff_weeks(prev, curr)
    d = diff.deltas[0]
    assert d.direction == "regressed"
    assert d.delta == pytest.approx(-0.3)
    assert diff.regressed_count == 1


# --------------------------------------------------------------------------- #
# Invariant #4 — both raw scores survive for auditability.
# --------------------------------------------------------------------------- #
def test_both_raw_scores_survive_on_delta():
    prev = _week("W01", [_r("exact", "m", 0.6)])
    curr = _week("W02", [_r("exact", "m", 0.9)])
    diff = diff_weeks(prev, curr)
    d = diff.deltas[0]
    assert d.previous_score == 0.6
    assert d.current_score == 0.9
    assert d.delta == pytest.approx(0.3)


# --------------------------------------------------------------------------- #
# Invariant #5 — task-family churn surfaced separately.
# --------------------------------------------------------------------------- #
def test_new_task_family_surfaced():
    prev = _week("W01", [_r("exact", "m", 0.5)])
    curr = _week("W02", [_r("exact", "m", 0.5), _r("rubric", "m", 0.7)])
    diff = diff_weeks(prev, curr)
    assert diff.new_task_families == ("rubric",)
    assert diff.dropped_task_families == ()


def test_dropped_task_family_surfaced():
    prev = _week("W01", [_r("exact", "m", 0.5), _r("rubric", "m", 0.7)])
    curr = _week("W02", [_r("exact", "m", 0.5)])
    diff = diff_weeks(prev, curr)
    assert diff.dropped_task_families == ("rubric",)
    assert diff.new_task_families == ()


# --------------------------------------------------------------------------- #
# Invariant #6 — summary counts partition exactly once.
# --------------------------------------------------------------------------- #
def test_counts_partition_every_comparable_once():
    prev = _week("W01", [
        _r("exact", "a", 0.5),       # will improve
        _r("exact", "b", 0.8),       # will regress
        _r("exact", "c", 0.5),       # unchanged
        _r("exact", "d", None, 0),   # unknown (both None)
        _r("exact", "e", 0.4),       # dropped
    ])
    curr = _week("W02", [
        _r("exact", "a", 0.7),       # improved
        _r("exact", "b", 0.6),       # regressed
        _r("exact", "c", 0.5),       # unchanged
        _r("exact", "d", None, 0),   # unknown
        _r("exact", "f", 0.9),       # new
    ])
    diff = diff_weeks(prev, curr)
    assert diff.improved_count == 1
    assert diff.regressed_count == 1
    assert diff.unchanged_count == 1
    assert diff.unknown_count == 1
    assert diff.new_count == 1
    assert diff.dropped_count == 1
    # partition: every entry counted exactly once
    assert diff.total_comparables == len(diff.deltas) == 6


# --------------------------------------------------------------------------- #
# Invariant #7 — deterministic + pure; fail-closed on bad input.
# --------------------------------------------------------------------------- #
def test_deterministic_output_order():
    prev = _week("W01", [_r("b-fam", "z-model", 0.5), _r("a-fam", "m-model", 0.5)])
    curr = _week("W02", [_r("a-fam", "m-model", 0.6), _r("b-fam", "z-model", 0.7)])
    diff = diff_weeks(prev, curr)
    keys = [(d.task_family, d.model_id) for d in diff.deltas]
    assert keys == sorted(keys)  # stable (task_family, model_id) order


def test_same_week_id_rejected():
    with pytest.raises(WeekDiffError, match="must differ"):
        diff_weeks(_week("W01", [_r("t", "m", 0.5)]), _week("W01", [_r("t", "m", 0.6)]))


def test_blank_week_id_rejected():
    with pytest.raises(WeekDiffError, match="non-empty"):
        diff_weeks(_week(" ", [_r("t", "m", 0.5)]), _week("W02", [_r("t", "m", 0.6)]))


def test_negative_epsilon_rejected():
    with pytest.raises(WeekDiffError, match="epsilon must be >= 0"):
        diff_weeks(
            _week("W01", [_r("t", "m", 0.5)]),
            _week("W02", [_r("t", "m", 0.6)]),
            epsilon=-0.01,
        )


def test_duplicate_key_rejected():
    with pytest.raises(WeekDiffError, match="duplicate"):
        bad = WeekSnapshot(
            week_id="W01",
            results=(_r("t", "m", 0.5), _r("t", "m", 0.6)),  # same key twice
        )
        diff_weeks(bad, _week("W02", [_r("t", "m", 0.7)]))


def test_purity_no_io_imports():
    import inspect

    from substrate.antiek_bench import week_diff as mod

    src = inspect.getsource(mod)
    for forbidden in ("import os", "import time", "import asyncio", "open(", "datetime.now", "requests"):
        assert forbidden not in src, f"purity breach: {forbidden!r}"


# --------------------------------------------------------------------------- #
# Convenience filters.
# --------------------------------------------------------------------------- #
def test_regressions_filter():
    prev = _week("W01", [_r("t", "a", 0.8), _r("t", "b", 0.5)])
    curr = _week("W02", [_r("t", "a", 0.4), _r("t", "b", 0.9)])
    diff = diff_weeks(prev, curr)
    regs = regressions(diff)
    assert len(regs) == 1
    assert regs[0].model_id == "a"


def test_improvements_filter():
    prev = _week("W01", [_r("t", "a", 0.8), _r("t", "b", 0.5)])
    curr = _week("W02", [_r("t", "a", 0.4), _r("t", "b", 0.9)])
    diff = diff_weeks(prev, curr)
    imps = improvements(diff)
    assert len(imps) == 1
    assert imps[0].model_id == "b"


# --------------------------------------------------------------------------- #
# Incomplete-week honesty note.
# --------------------------------------------------------------------------- #
def test_incomplete_week_adds_honesty_note():
    prev = _week("W01", [_r("t", "m", 0.5)], incomplete=True)
    curr = _week("W02", [_r("t", "m", 0.6)])
    diff = diff_weeks(prev, curr)
    assert any("incomplete" in note for note in diff.honesty_notes)


# --------------------------------------------------------------------------- #
# Boundary types frozen.
# --------------------------------------------------------------------------- #
def test_boundary_types_frozen():
    import dataclasses

    for cls in (WeeklyModelResult, WeekSnapshot, ScoreDelta, WeekOverWeekDiff):
        assert dataclasses.is_dataclass(cls)

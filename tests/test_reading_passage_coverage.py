"""Tests for the reading-passage-coverage axis (asks #2/#6).

Measures document BREADTH — what fraction of passages the reader engaged with.
Exercises thorough/partial/unread/unknown verdicts, coverage ratio, gap detection,
the unread-vs-unknown distinction, deduplication, validation,
purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.reading_passage_coverage import (
    CoverageGap,
    ReadingPassageCoverageError,
    measure_reading_passage_coverage,
)

# --- unknown --------------------------------------------------------------


def test_unknown_when_empty_document() -> None:
    r = measure_reading_passage_coverage(0, [])
    assert r.verdict == "unknown"
    assert r.total_passages == 0
    assert r.touched_count == 0
    assert r.coverage_ratio is None
    assert r.gaps == ()
    assert r.authority == "advisory"


# --- unread ---------------------------------------------------------------


def test_unread_when_nothing_touched() -> None:
    r = measure_reading_passage_coverage(10, [])
    assert r.verdict == "unread"
    assert r.touched_count == 0
    assert r.coverage_ratio == 0.0
    assert r.untouched_count == 10
    # One gap covering the whole document.
    assert len(r.gaps) == 1
    assert r.gaps[0] == CoverageGap(start_index=0, end_index=9, length=10)


def test_unread_distinct_from_unknown() -> None:
    # Empty doc = unknown; non-empty with zero touches = unread. Never collapsed.
    r_empty = measure_reading_passage_coverage(0, [])
    r_unread = measure_reading_passage_coverage(5, [])
    assert r_empty.verdict == "unknown"
    assert r_unread.verdict == "unread"
    assert r_unread.coverage_ratio == 0.0  # real measured 0.0, not deferred


# --- thorough -------------------------------------------------------------


def test_thorough_full_coverage() -> None:
    r = measure_reading_passage_coverage(5, [0, 1, 2, 3, 4])
    assert r.verdict == "thorough"
    assert r.coverage_ratio == 1.0
    assert r.touched_count == 5
    assert r.untouched_count == 0
    assert r.gaps == ()


def test_thorough_near_complete() -> None:
    # 9 of 10 = 0.9 >= 0.85 threshold.
    r = measure_reading_passage_coverage(10, [0, 1, 2, 3, 4, 5, 6, 7, 8])
    assert r.verdict == "thorough"
    assert r.coverage_ratio == 0.9
    assert len(r.gaps) == 1  # gap at index 9


def test_thorough_boundary_inclusive() -> None:
    # 0.85 exactly = thorough (>=).
    r = measure_reading_passage_coverage(20, list(range(17)))
    assert r.coverage_ratio == pytest.approx(0.85)
    assert r.verdict == "thorough"


# --- partial --------------------------------------------------------------


def test_partial_moderate_coverage() -> None:
    # 5 of 20 = 0.25 < 0.85.
    r = measure_reading_passage_coverage(20, [0, 1, 2, 3, 4])
    assert r.verdict == "partial"
    assert r.coverage_ratio == 0.25
    assert r.untouched_count == 15


def test_partial_just_below_threshold() -> None:
    # 16 of 20 = 0.80 < 0.85.
    r = measure_reading_passage_coverage(20, list(range(16)))
    assert r.verdict == "partial"
    assert r.coverage_ratio == 0.8


# --- gap detection --------------------------------------------------------


def test_gaps_at_start_middle_end() -> None:
    # touched 3,4,5 of 10 -> gap [0,2], gap [6,9].
    r = measure_reading_passage_coverage(10, [3, 4, 5])
    assert len(r.gaps) == 2
    assert r.gaps[0] == CoverageGap(start_index=0, end_index=2, length=3)
    assert r.gaps[1] == CoverageGap(start_index=6, end_index=9, length=4)


def test_gaps_multiple_internal_runs() -> None:
    # touched 1,4,7 of 10 -> gaps [0,0],[2,3],[5,6],[8,9].
    r = measure_reading_passage_coverage(10, [1, 4, 7])
    assert len(r.gaps) == 4
    assert r.gaps[0] == CoverageGap(start_index=0, end_index=0, length=1)
    assert r.gaps[1] == CoverageGap(start_index=2, end_index=3, length=2)
    assert r.gaps[2] == CoverageGap(start_index=5, end_index=6, length=2)
    assert r.gaps[3] == CoverageGap(start_index=8, end_index=9, length=2)


def test_gaps_sorted_deterministic() -> None:
    r = measure_reading_passage_coverage(10, [5, 1, 8, 3])
    starts = [g.start_index for g in r.gaps]
    assert starts == sorted(starts)


# --- deduplication --------------------------------------------------------


def test_duplicate_indices_deduplicated() -> None:
    # Touching passage 3 five times = one touched passage.
    r = measure_reading_passage_coverage(10, [3, 3, 3, 3, 3])
    assert r.touched_count == 1
    assert r.coverage_ratio == pytest.approx(0.1)


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_shifts_verdict() -> None:
    # 5 of 10 = 0.5: thorough at 0.50, partial at 0.85.
    r_default = measure_reading_passage_coverage(10, [0, 1, 2, 3, 4])
    assert r_default.verdict == "partial"
    r_loose = measure_reading_passage_coverage(10, [0, 1, 2, 3, 4], thorough_threshold=0.50)
    assert r_loose.verdict == "thorough"
    assert r_loose.thorough_threshold == 0.50


# --- validation -----------------------------------------------------------


def test_negative_total_raises() -> None:
    with pytest.raises(ReadingPassageCoverageError):
        measure_reading_passage_coverage(-1, [])


def test_index_out_of_range_high_raises() -> None:
    with pytest.raises(ReadingPassageCoverageError):
        measure_reading_passage_coverage(5, [5])


def test_index_negative_raises() -> None:
    with pytest.raises(ReadingPassageCoverageError):
        measure_reading_passage_coverage(5, [-1])


def test_invalid_threshold_raises() -> None:
    with pytest.raises(ReadingPassageCoverageError):
        measure_reading_passage_coverage(10, [], thorough_threshold=0.0)
    with pytest.raises(ReadingPassageCoverageError):
        measure_reading_passage_coverage(10, [], thorough_threshold=1.01)


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    assert measure_reading_passage_coverage(10, [1, 3, 5]) == \
        measure_reading_passage_coverage(10, [1, 3, 5])


def test_report_is_frozen_immutable() -> None:
    r = measure_reading_passage_coverage(10, [1])
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "thorough"  # type: ignore[misc]


def test_coverage_gap_is_frozen() -> None:
    gap = CoverageGap(start_index=0, end_index=2, length=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        gap.length = 5  # type: ignore[misc]


def test_notes_carry_context() -> None:
    r = measure_reading_passage_coverage(10, [1, 2])
    assert any("touched" in note for note in r.notes)
    assert any("gap" in note for note in r.notes)

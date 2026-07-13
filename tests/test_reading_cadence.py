"""Tests for the reading cadence axis (ask #2)."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from substrate.reading_cadence import (
    ReadingCadenceReport,
    measure_reading_cadence,
)


def test_no_events_is_unknown() -> None:
    report = measure_reading_cadence([])
    assert report.verdict == "unknown"
    assert report.event_count == 0
    assert report.session_duration is None
    assert report.mean_gap is None
    assert report.gap_std is None
    assert report.gap_cv is None
    assert report.burstiness_coefficient is None
    assert report.authority == "advisory"


def test_single_event_is_base_case() -> None:
    report = measure_reading_cadence([5.0])
    assert report.verdict == "single_event"
    assert report.event_count == 1
    assert report.gap_count == 0
    assert report.session_duration is None
    assert report.burstiness_coefficient is None


def test_all_events_same_instant_is_unmeasurable() -> None:
    report = measure_reading_cadence([3.0, 3.0, 3.0])
    assert report.verdict == "unmeasurable"
    assert report.session_duration == 0.0
    assert report.mean_gap == 0.0
    assert report.gap_std == 0.0
    assert report.gap_cv is None
    assert report.burstiness_coefficient is None


def test_perfectly_regular_is_steady() -> None:
    # gaps [10,10,10] -> std 0 -> cv 0, B = -1
    report = measure_reading_cadence([0.0, 10.0, 20.0, 30.0])
    assert report.verdict == "steady_cadence"
    assert report.event_count == 4
    assert report.gap_count == 3
    assert report.session_duration == 30.0
    assert report.mean_gap == 10.0
    assert report.gap_std == 0.0
    assert report.gap_cv == 0.0
    assert report.burstiness_coefficient == pytest.approx(-1.0)
    assert report.min_gap == 10.0
    assert report.max_gap == 10.0


def test_bursty_gaps_one_outlier() -> None:
    # events [0,1,2,3,4,103] -> gaps [1,1,1,1,99]
    # mean = 103/5 = 20.6 ; var = 1536.64 -> std = 39.2 (exact)
    # cv = 196/103 ; B = 93/299 ~= 0.311 (>= 0.30 -> bursty)
    report = measure_reading_cadence([0.0, 1.0, 2.0, 3.0, 4.0, 103.0])
    assert report.verdict == "bursty_cadence"
    assert report.gap_count == 5
    assert report.session_duration == 103.0
    assert report.mean_gap == pytest.approx(103 / 5)
    assert report.gap_std == pytest.approx(39.2)
    assert report.gap_cv == pytest.approx(196 / 103)
    assert report.burstiness_coefficient == pytest.approx(93 / 299)
    assert report.min_gap == 1.0
    assert report.max_gap == 99.0


def test_irregular_near_random_timing() -> None:
    # events [0,1,3,6,12] -> gaps [1,2,3,6] ; mean 3 ; var 3.5 -> std sqrt(3.5)
    # cv = sqrt(3.5)/3 ; B ~= -0.232 (between -0.30 and 0.30 -> irregular)
    report = measure_reading_cadence([0.0, 1.0, 3.0, 6.0, 12.0])
    assert report.verdict == "irregular_cadence"
    assert report.mean_gap == 3.0
    assert report.gap_std == pytest.approx(math.sqrt(3.5))
    std = math.sqrt(3.5)
    assert report.burstiness_coefficient == pytest.approx((std - 3.0) / (std + 3.0))


def test_unsorted_input_normalized_to_steady() -> None:
    # unordered -> sorted ascending -> gaps [10,10,10] -> steady
    report = measure_reading_cadence([30.0, 0.0, 10.0, 20.0])
    assert report.verdict == "steady_cadence"
    assert report.burstiness_coefficient == pytest.approx(-1.0)


def test_near_zero_burstiness_carried_not_deferred() -> None:
    # irregular carries a REAL measured B, never None
    report = measure_reading_cadence([0.0, 1.0, 3.0, 6.0, 12.0])
    assert report.burstiness_coefficient is not None
    assert report.verdict == "irregular_cadence"


def test_custom_thresholds_reclassify_boundary() -> None:
    # B ~= -0.232: irregular at +/-0.30, steady at -0.20
    events = [0.0, 1.0, 3.0, 6.0, 12.0]
    assert measure_reading_cadence(events).verdict == "irregular_cadence"
    assert measure_reading_cadence(events, steady_threshold=-0.20).verdict == "steady_cadence"


def test_threshold_validation_rejects_out_of_range() -> None:
    events = [0.0, 1.0, 2.0]
    with pytest.raises(ValueError, match="steady_threshold"):
        measure_reading_cadence(events, steady_threshold=0.0)
    with pytest.raises(ValueError, match="steady_threshold"):
        measure_reading_cadence(events, steady_threshold=-1.5)
    with pytest.raises(ValueError, match="bursty_threshold"):
        measure_reading_cadence(events, bursty_threshold=0.0)
    with pytest.raises(ValueError, match="bursty_threshold"):
        measure_reading_cadence(events, bursty_threshold=1.5)


def test_report_is_frozen_and_deterministic() -> None:
    events = [0.0, 1.0, 2.0, 3.0, 4.0, 103.0]
    first = measure_reading_cadence(events)
    second = measure_reading_cadence(events)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: ReadingCadenceReport = measure_reading_cadence([0.0, 10.0, 20.0, 30.0])
    assert isinstance(report, ReadingCadenceReport)
    assert isinstance(report.notes, tuple)
    assert report.steady_threshold == -0.30
    assert report.bursty_threshold == 0.30
    assert report.authority == "advisory"

"""Tests for the reading re-engagement axis (ask #2).

Every fixture is hand-counted: session counts, return counts, gaps, and spans are
verified by inspection before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

import pytest

from substrate.reading_re_engagement import (
    ReadingReEngagementReport,
    measure_reading_re_engagement,
)


def dt(year: int, month: int, day: int, hour: int = 9) -> datetime:
    return datetime(year, month, day, hour)


# ---------------------------------------------------------------------------
# Base cases — distinct honest states, never collapsed.
# ---------------------------------------------------------------------------


def test_no_sessions_is_unknown() -> None:
    report = measure_reading_re_engagement([])
    assert report.verdict == "unknown"
    assert report.session_count == 0
    assert report.return_count == 0
    assert report.return_rate is None
    assert report.engagement_span_days is None
    assert report.mean_inter_session_gap_days is None
    assert report.max_inter_session_gap_days is None
    assert report.session_starts == ()
    assert report.authority == "advisory"


def test_single_session_is_base_case() -> None:
    report = measure_reading_re_engagement([dt(2024, 3, 1)])
    assert report.verdict == "single_session"
    assert report.session_count == 1
    assert report.return_count == 0
    assert report.return_rate == pytest.approx(0.0)
    assert report.engagement_span_days is None  # a point has no span
    assert report.mean_inter_session_gap_days is None
    assert report.max_inter_session_gap_days is None


def test_single_session_distinct_from_unknown() -> None:
    assert measure_reading_re_engagement([]).verdict == "unknown"
    assert measure_reading_re_engagement([dt(2024, 1, 1)]).verdict == "single_session"


# ---------------------------------------------------------------------------
# Returned (2 sessions — minimal return) and recurring (>= threshold).
# ---------------------------------------------------------------------------


def test_two_sessions_returned() -> None:
    report = measure_reading_re_engagement([dt(2024, 3, 1), dt(2024, 3, 3)])
    assert report.verdict == "returned"
    assert report.session_count == 2
    assert report.return_count == 1
    assert report.return_rate == pytest.approx(0.5)
    assert report.engagement_span_days == pytest.approx(2.0)
    assert report.mean_inter_session_gap_days == pytest.approx(2.0)
    assert report.max_inter_session_gap_days == pytest.approx(2.0)


def test_three_sessions_recurring_default_threshold() -> None:
    report = measure_reading_re_engagement(
        [dt(2024, 3, 1), dt(2024, 3, 8), dt(2024, 3, 15)]
    )
    assert report.verdict == "recurring"
    assert report.session_count == 3
    assert report.return_count == 2
    assert report.return_rate == pytest.approx(2 / 3)
    assert report.engagement_span_days == pytest.approx(14.0)
    assert report.mean_inter_session_gap_days == pytest.approx(7.0)
    assert report.max_inter_session_gap_days == pytest.approx(7.0)


def test_return_rate_approaches_one_with_many_sessions() -> None:
    sessions = [dt(2024, 3, 1 + i) for i in range(10)]
    report = measure_reading_re_engagement(sessions)
    assert report.verdict == "recurring"
    assert report.return_rate is not None
    assert report.return_rate == pytest.approx(0.9)
    assert 0.0 <= report.return_rate < 1.0


# ---------------------------------------------------------------------------
# Inter-session gap math — mean, max, span hand-verified.
# ---------------------------------------------------------------------------


def test_uneven_gaps_mean_and_max() -> None:
    # gaps: 1 day, 10 days -> mean 5.5, max 10, span 11
    report = measure_reading_re_engagement(
        [dt(2024, 3, 1), dt(2024, 3, 2), dt(2024, 3, 12)]
    )
    assert report.verdict == "recurring"
    assert report.mean_inter_session_gap_days == pytest.approx(5.5)
    assert report.max_inter_session_gap_days == pytest.approx(10.0)
    assert report.engagement_span_days == pytest.approx(11.0)


def test_span_is_first_to_last() -> None:
    report = measure_reading_re_engagement(
        [dt(2023, 1, 1), dt(2023, 2, 1), dt(2023, 4, 1)]  # 2023 non-leap: 31+28+31 = 90 days
    )
    assert report.engagement_span_days == pytest.approx(90.0)


def test_session_starts_deduplicated_and_sorted() -> None:
    # duplicates + out-of-order -> sorted, unique
    report = measure_reading_re_engagement(
        [dt(2024, 3, 5), dt(2024, 3, 1), dt(2024, 3, 1), dt(2024, 3, 10)]
    )
    assert report.session_count == 3  # one duplicate collapsed
    assert [s.day for s in report.session_starts] == [1, 5, 10]


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_recurring_threshold_below_two_raises() -> None:
    with pytest.raises(ValueError, match="recurring_threshold"):
        measure_reading_re_engagement([dt(2024, 1, 1)], recurring_threshold=1)


def test_custom_threshold_reclassifies_recurring_to_returned() -> None:
    sessions = [dt(2024, 3, 1), dt(2024, 3, 8), dt(2024, 3, 15)]
    assert measure_reading_re_engagement(sessions).verdict == "recurring"
    assert (
        measure_reading_re_engagement(sessions, recurring_threshold=5).verdict
        == "returned"
    )


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_reading_re_engagement([dt(2024, 1, 1), dt(2024, 1, 2)])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "recurring"  # type: ignore[misc]


def test_deterministic_output() -> None:
    sessions = [dt(2024, 3, 5), dt(2024, 3, 1), dt(2024, 3, 10), dt(2024, 3, 8)]
    assert measure_reading_re_engagement(sessions) == measure_reading_re_engagement(
        sessions
    )


def test_report_is_reading_re_engagement_report_instance() -> None:
    report = measure_reading_re_engagement([dt(2024, 1, 1)])
    assert isinstance(report, ReadingReEngagementReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_reading_re_engagement(
        [dt(2024, 3, 1), dt(2024, 3, 8), dt(2024, 3, 15)]
    )
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)
    assert any("cross-session" in n.lower() for n in report.notes)


def test_timedelta_inputs_accepted() -> None:
    # sessions spanning hours within one day
    base = dt(2024, 3, 1, 9)
    report = measure_reading_re_engagement(
        [base, base + timedelta(hours=6), base + timedelta(hours=12)]
    )
    assert report.verdict == "recurring"
    assert report.engagement_span_days == pytest.approx(0.5)

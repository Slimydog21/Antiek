"""Tests for the temporal-spread axis (ask #7).

Every fixture is hand-counted: spans, year counts, and shares are verified by
inspection before assertions are written. The anchored-vs-broad pair proves the
load-bearing concentration distinction (same span, different temporal integrity).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from substrate.temporal_spread import (
    TemporalSpreadReport,
    measure_temporal_spread,
)

D = date  # shorthand for fixtures


# ---------------------------------------------------------------------------
# Base cases — distinct honest states, never collapsed.
# ---------------------------------------------------------------------------


def test_empty_is_unknown() -> None:
    report = measure_temporal_spread([])
    assert report.verdict == "unknown"
    assert report.dated_source_count == 0
    assert report.earliest_date is None
    assert report.latest_date is None
    assert report.date_span_years is None
    assert report.distinct_year_count is None
    assert report.max_year_share is None
    assert report.year_histogram == ()
    assert report.dominant_years == ()
    assert report.authority == "advisory"


def test_single_moment_all_one_date() -> None:
    # single_moment requires span 0 (identical dates); a single source is the
    # cleanest case, plus a multi-identical-date case.
    report = measure_temporal_spread([D(2024, 3, 1)])
    assert report.verdict == "single_moment"
    assert report.dated_source_count == 1
    assert report.date_span_years == 0.0  # honest measured zero
    assert report.distinct_year_count == 1
    assert report.max_year_share == pytest.approx(1.0)
    assert report.earliest_date == D(2024, 3, 1)
    assert report.latest_date == D(2024, 3, 1)
    assert len(report.year_histogram) == 1

    multi = measure_temporal_spread([D(2024, 3, 1), D(2024, 3, 1)])
    assert multi.verdict == "single_moment"
    assert multi.date_span_years == 0.0
    assert multi.dated_source_count == 2


def test_single_moment_distinct_from_unknown() -> None:
    assert measure_temporal_spread([]).verdict == "unknown"
    assert measure_temporal_spread([D(2024, 1, 1)]).verdict == "single_moment"


# ---------------------------------------------------------------------------
# Measurable spreads — verdict bands.
# ---------------------------------------------------------------------------


def test_narrow_window_short_span() -> None:
    report = measure_temporal_spread([D(2024, 1, 1), D(2024, 12, 1)])
    assert report.verdict == "narrow_window"
    assert report.date_span_years is not None
    assert 0.0 < report.date_span_years < 5.0
    assert report.distinct_year_count == 1


def test_anchored_spectrum_wide_span_dominant_year() -> None:
    # 1 source in 2014, 9 sources in 2024 -> span 10 years but 90% in 2024.
    dates = [D(2014, 5, 1)] + [D(2024, m, 1) for m in range(1, 10)]
    report = measure_temporal_spread(dates)
    assert report.dated_source_count == 10
    assert report.date_span_years is not None
    assert report.date_span_years > 5.0
    assert report.max_year_share == pytest.approx(0.90)
    assert report.verdict == "anchored_spectrum"
    assert 2024 in report.dominant_years
    assert 2014 not in report.dominant_years


def test_broad_spectrum_wide_span_distributed() -> None:
    # One source per year across 2014-2024 -> span 10 years, no dominant year.
    dates = [D(y, 6, 1) for y in range(2014, 2025)]
    report = measure_temporal_spread(dates)
    assert report.dated_source_count == 11
    assert report.date_span_years is not None
    assert report.date_span_years > 5.0
    assert report.max_year_share == pytest.approx(1 / 11)
    assert report.verdict == "broad_spectrum"
    assert report.dominant_years == ()


def test_anchored_vs_broad_same_span_different_integrity() -> None:
    """The load-bearing test: identical span, different verdict via concentration."""
    anchored = [D(2014, 5, 1)] + [D(2024, m, 1) for m in range(1, 10)]
    broad = [D(y, 6, 1) for y in range(2015, 2025)]
    a = measure_temporal_spread(anchored)
    b = measure_temporal_spread(broad)
    assert a.date_span_years is not None and b.date_span_years is not None
    assert abs(a.date_span_years - b.date_span_years) < 1.5  # same ~10yr span
    assert a.verdict == "anchored_spectrum"
    assert b.verdict == "broad_spectrum"


# ---------------------------------------------------------------------------
# Distribution auditability — year_histogram, dominant_years.
# ---------------------------------------------------------------------------


def test_year_histogram_sorted_by_year() -> None:
    report = measure_temporal_spread(
        [D(2022, 1, 1), D(2020, 1, 1), D(2022, 6, 1), D(2021, 1, 1)]
    )
    years = [yc.year for yc in report.year_histogram]
    assert years == [2020, 2021, 2022]
    assert [yc.count for yc in report.year_histogram] == [1, 1, 2]


def test_dominant_years_threshold_boundary() -> None:
    # 4 sources in 2020, 4 in 2024 -> each share 0.50 = concentration_threshold.
    report = measure_temporal_spread(
        [D(2020, 1, 1)] * 4 + [D(2024, 1, 1)] * 4
    )
    assert report.max_year_share == pytest.approx(0.50)
    # >= threshold, so both years are dominant
    assert sorted(report.dominant_years) == [2020, 2024]


def test_earliest_latest_dates() -> None:
    report = measure_temporal_spread([D(2024, 3, 1), D(2018, 7, 15), D(2021, 9, 9)])
    assert report.earliest_date == D(2018, 7, 15)
    assert report.latest_date == D(2024, 3, 1)


def test_distinct_year_count() -> None:
    report = measure_temporal_spread(
        [D(2020, 1, 1), D(2020, 6, 1), D(2022, 1, 1), D(2024, 1, 1)]
    )
    assert report.distinct_year_count == 3  # 2020, 2022, 2024


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_broad_span_years_must_be_positive() -> None:
    with pytest.raises(ValueError, match="broad_span_years"):
        measure_temporal_spread([D(2024, 1, 1)], broad_span_years=0)


def test_concentration_threshold_must_be_in_unit() -> None:
    with pytest.raises(ValueError, match="concentration_threshold"):
        measure_temporal_spread([D(2024, 1, 1)], concentration_threshold=0.0)
    with pytest.raises(ValueError, match="concentration_threshold"):
        measure_temporal_spread([D(2024, 1, 1)], concentration_threshold=1.5)


def test_custom_broad_span_reclassifies() -> None:
    # 4-year span: default (5.0) -> narrow_window; tightened (3.0) -> anchored/broad.
    dates = [D(2020, 1, 1), D(2024, 1, 1)]
    default = measure_temporal_spread(dates)
    assert default.verdict == "narrow_window"
    tightened = measure_temporal_spread(dates, broad_span_years=3.0)
    assert tightened.date_span_years is not None
    assert tightened.date_span_years > 3.0
    assert tightened.max_year_share == pytest.approx(0.50)
    assert tightened.verdict == "anchored_spectrum"  # dominant year present


def test_custom_concentration_threshold_makes_anchored_broad() -> None:
    # 2014 + nine 2024 sources: share 0.90. Default (0.50) -> anchored; (0.95) -> broad.
    dates = [D(2014, 5, 1)] + [D(2024, m, 1) for m in range(1, 10)]
    default = measure_temporal_spread(dates)
    assert default.verdict == "anchored_spectrum"
    raised = measure_temporal_spread(dates, concentration_threshold=0.95)
    assert raised.verdict == "broad_spectrum"


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_temporal_spread([D(2024, 1, 1), D(2020, 1, 1)])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "broad_spectrum"  # type: ignore[misc]


def test_deterministic_output() -> None:
    dates = [D(2022, 1, 1), D(2018, 7, 15), D(2024, 3, 1), D(2021, 9, 9)]
    assert measure_temporal_spread(dates) == measure_temporal_spread(dates)


def test_report_is_temporal_spread_report_instance() -> None:
    report = measure_temporal_spread([D(2024, 1, 1)])
    assert isinstance(report, TemporalSpreadReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_temporal_spread([D(2024, 1, 1), D(2020, 1, 1)])
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("temporal spread" in n.lower() for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)


def test_unknown_notes_when_no_dates() -> None:
    report = measure_temporal_spread([])
    assert len(report.notes) == 1
    assert "no dated sources" in report.notes[0]

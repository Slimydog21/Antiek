"""Tests for the source-recency axis (ask #7 — highest quality DR).

Exercises: age computation, median/max, stale fraction, undated-defer, verdict
bands, honest date-availability, validation, purity/immutability. Uses fixed
reference_date for deterministic math.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import pytest

from substrate.deep_research_quality.source_recency import (
    SourceDateMap,
    SourceRecencyError,
    SourceRecencyReport,
    measure_source_recency,
)

REF = date(2025, 1, 1)


def _years_ago(years: float) -> date:
    return REF - timedelta(days=int(years * 365.25))


def _dates(mapping: dict[str, date]) -> SourceDateMap:
    return SourceDateMap(dates=mapping)


# --- age computation -------------------------------------------------------


def test_dated_sources_age_computed() -> None:
    report = measure_source_recency(
        "inv-1",
        ["s1", "s2"],
        _dates({"s1": _years_ago(1), "s2": _years_ago(2)}),
        reference_date=REF,
    )
    assert report.dated_source_count == 2
    assert report.median_source_age_years == pytest.approx(1.5, abs=0.02)
    assert report.max_source_age_years == pytest.approx(2.0, abs=0.02)


def test_median_odd_count() -> None:
    report = measure_source_recency(
        "inv-1",
        ["s1", "s2", "s3"],
        _dates({"s1": _years_ago(1), "s2": _years_ago(3), "s3": _years_ago(5)}),
        reference_date=REF,
    )
    assert report.median_source_age_years == pytest.approx(3.0, abs=0.02)


# --- undated sources: honest defer ----------------------------------------


def test_undated_sources_excluded_not_fabricated() -> None:
    report = measure_source_recency(
        "inv-1",
        ["s1", "s2", "s3"],
        _dates({"s1": _years_ago(1)}),  # s2, s3 undated
        reference_date=REF,
    )
    assert report.dated_source_count == 1
    assert report.undated_source_count == 2
    assert report.undated_source_fraction == pytest.approx(2 / 3)
    assert report.median_source_age_years == pytest.approx(1.0, abs=0.02)


def test_all_undated_is_unknown() -> None:
    report = measure_source_recency(
        "inv-1", ["s1", "s2"], _dates({}), reference_date=REF
    )
    assert report.dated_source_count == 0
    assert report.median_source_age_years is None
    assert report.stale_source_fraction is None
    assert report.verdict == "unknown"


def test_no_sources_is_unknown() -> None:
    report = measure_source_recency("inv-1", [], _dates({}), reference_date=REF)
    assert report.total_source_count == 0
    assert report.verdict == "unknown"
    assert report.median_source_age_years is None


# --- stale fraction --------------------------------------------------------


def test_stale_fraction_computed() -> None:
    # 2 of 4 sources older than 3-year threshold -> 0.5
    report = measure_source_recency(
        "inv-1",
        ["s1", "s2", "s3", "s4"],
        _dates({
            "s1": _years_ago(1), "s2": _years_ago(2),
            "s3": _years_ago(5), "s4": _years_ago(6),
        }),
        reference_date=REF,
    )
    assert report.stale_source_fraction == pytest.approx(0.5)


# --- verdict bands ---------------------------------------------------------


def test_verdict_current() -> None:
    report = measure_source_recency(
        "inv-1", ["s1", "s2"],
        _dates({"s1": _years_ago(0.5), "s2": _years_ago(1)}),
        reference_date=REF,
    )
    assert report.verdict == "current"


def test_verdict_stale_via_median() -> None:
    report = measure_source_recency(
        "inv-1", ["s1", "s2"],
        _dates({"s1": _years_ago(4), "s2": _years_ago(5)}),
        reference_date=REF,
    )
    assert report.verdict == "stale"


def test_verdict_stale_via_high_stale_fraction() -> None:
    # median is 1.5 (below threshold) but 50% are stale -> stale
    report = measure_source_recency(
        "inv-1", ["s1", "s2", "s3", "s4"],
        _dates({
            "s1": _years_ago(0.5), "s2": _years_ago(1),
            "s3": _years_ago(5), "s4": _years_ago(6),
        }),
        reference_date=REF,
    )
    assert report.median_source_age_years is not None and report.median_source_age_years < 3.0
    assert report.stale_source_fraction is not None and report.stale_source_fraction >= 0.40
    assert report.verdict == "stale"


def test_verdict_aging() -> None:
    # median ~2.5 years (>= 1.5 = 0.5*3, < 3 threshold) -> aging
    report = measure_source_recency(
        "inv-1", ["s1", "s2"],
        _dates({"s1": _years_ago(2), "s2": _years_ago(3)}),
        reference_date=REF,
    )
    assert report.median_source_age_years is not None and report.median_source_age_years >= 1.5
    assert report.verdict == "aging"


# --- duplicate source ids de-duplicated ------------------------------------


def test_duplicate_source_ids_deduplicated() -> None:
    report = measure_source_recency(
        "inv-1", ["s1", "s1", "s1"],
        _dates({"s1": _years_ago(1)}),
        reference_date=REF,
    )
    assert report.total_source_count == 1
    assert report.dated_source_count == 1


# --- future-dated source clamps to 0 --------------------------------------


def test_future_dated_source_clamps_to_zero() -> None:
    future = REF + timedelta(days=100)
    report = measure_source_recency(
        "inv-1", ["s1"], _dates({"s1": future}), reference_date=REF
    )
    assert report.median_source_age_years == pytest.approx(0.0)


# --- custom threshold ------------------------------------------------------


def test_custom_freshness_threshold_changes_verdict() -> None:
    # 2 years < 3 default -> current or aging
    report_strict = measure_source_recency(
        "inv-1", ["s1"], _dates({"s1": _years_ago(2)}),
        reference_date=REF, freshness_threshold_years=1.0,
    )
    # 2 years >= 1 strict threshold -> stale
    assert report_strict.verdict == "stale"


# --- provenance / purity ---------------------------------------------------


def test_artifact_id_carried_through() -> None:
    report = measure_source_recency(
        "inv-777", ["s1"], _dates({"s1": _years_ago(1)}), reference_date=REF
    )
    assert report.artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    report = measure_source_recency(
        "inv-1", ["s1"], _dates({"s1": _years_ago(1)}), reference_date=REF
    )
    assert report.authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_source_recency(
        "inv-1", ["s1"], _dates({"s1": _years_ago(1)}), reference_date=REF
    )
    assert isinstance(report, SourceRecencyReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "stale"  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    args = ("inv-1", ["s1", "s2"], _dates({"s1": _years_ago(1), "s2": _years_ago(2)}))
    assert measure_source_recency(*args, reference_date=REF) == measure_source_recency(*args, reference_date=REF)


def test_notes_describe_verdict() -> None:
    report = measure_source_recency(
        "inv-1", ["s1"], _dates({"s1": _years_ago(5)}), reference_date=REF
    )
    joined = " | ".join(report.notes).lower()
    assert "factual" in joined
    assert "undated" in joined


def test_undated_fraction_always_carried() -> None:
    report = measure_source_recency(
        "inv-1", ["s1"], _dates({"s1": _years_ago(1)}), reference_date=REF
    )
    assert report.undated_source_fraction == pytest.approx(0.0)


# --- validation ------------------------------------------------------------


def test_validation_rejects_zero_threshold() -> None:
    with pytest.raises(SourceRecencyError, match="freshness_threshold"):
        measure_source_recency(
            "inv-1", ["s1"], _dates({}), reference_date=REF, freshness_threshold_years=0
        )


def test_validation_rejects_bad_stale_fractions() -> None:
    with pytest.raises(SourceRecencyError, match="stale_fraction_low"):
        measure_source_recency(
            "inv-1", ["s1"], _dates({}), reference_date=REF, stale_fraction_low=-0.1
        )
    with pytest.raises(SourceRecencyError, match="stale_fraction_high"):
        measure_source_recency(
            "inv-1", ["s1"], _dates({}), reference_date=REF,
            stale_fraction_low=0.5, stale_fraction_high=0.3,
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import source_recency as mod

    assert set(mod.__all__) == {
        "SourceDateMap",
        "SourceRecencyError",
        "SourceRecencyReport",
        "measure_source_recency",
    }
    assert issubclass(mod.SourceRecencyError, ValueError)
    assert dataclasses.is_dataclass(mod.SourceDateMap)
    assert dataclasses.is_dataclass(mod.SourceRecencyReport)

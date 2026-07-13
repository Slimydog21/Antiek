"""Tests for the source-type coverage axis (publication-type diversity — ask #7)."""

from __future__ import annotations

import dataclasses

import pytest

from substrate.source_type_coverage import (
    SourceTypeCoverageError,
    TypedSource,
    measure_source_type_coverage,
)

KNOWN = ["arxiv", "substack", "journal", "blog", "report"]


def srcs(*pairs: tuple[str, str]) -> list[TypedSource]:
    return [TypedSource(source_id=sid, source_type=st) for sid, st in pairs]


# --- verdicts ---------------------------------------------------------------


def test_broad_coverage_above_threshold() -> None:
    # 3 of 5 known types -> 0.60 == threshold -> broad_coverage (>= boundary).
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "substack"), ("c", "journal")), KNOWN,
    )
    assert report.verdict == "broad_coverage"
    assert report.present_type_count == 3
    assert report.coverage_ratio == pytest.approx(0.60)
    assert report.cited_source_count == 3
    assert report.authority == "advisory"


def test_broad_coverage_all_types() -> None:
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "substack"), ("c", "journal"), ("d", "blog"), ("e", "report")),
        KNOWN,
    )
    assert report.verdict == "broad_coverage"
    assert report.coverage_ratio == 1.0


def test_partial_coverage_below_threshold() -> None:
    # 2 of 5 -> 0.40 < 0.60 -> partial_coverage.
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "substack")), KNOWN,
    )
    assert report.verdict == "partial_coverage"
    assert report.coverage_ratio == pytest.approx(0.40)


def test_type_monoculture_many_sources_one_type() -> None:
    # 5 sources all arxiv -> present_types = {arxiv} = 1 -> type_monoculture.
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "arxiv"), ("c", "arxiv"), ("d", "arxiv"), ("e", "arxiv")),
        KNOWN,
    )
    assert report.verdict == "type_monoculture"
    assert report.present_type_count == 1
    assert report.cited_source_count == 5
    assert report.coverage_ratio == pytest.approx(0.20)


def test_type_monoculture_single_source() -> None:
    # 1 source -> present_types = 1 -> type_monoculture (NOT unknown).
    report = measure_source_type_coverage(
        srcs(("a", "arxiv")), KNOWN,
    )
    assert report.verdict == "type_monoculture"


# --- the load-bearing distinction: monoculture != unknown -----------------


def test_type_monoculture_is_not_unknown() -> None:
    # Sources cited but all one type -> monoculture (measured), NOT unknown.
    report = measure_source_type_coverage(srcs(("a", "arxiv"), ("b", "arxiv")), KNOWN)
    assert report.verdict == "type_monoculture"
    assert report.coverage_ratio == pytest.approx(0.20)  # real measured, not None


# --- unknown (no cited sources) --------------------------------------------


def test_unknown_when_no_sources() -> None:
    report = measure_source_type_coverage([], KNOWN)
    assert report.verdict == "unknown"
    assert report.coverage_ratio is None  # defer, never 0.0


# --- untyped sources (honest — not forced into a known type) --------------


def test_untyped_sources_carried_not_counted() -> None:
    # 1 arxiv + 1 untyped (empty) -> present {arxiv}=1 -> monoculture; untyped carried.
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "")), KNOWN,
    )
    assert report.verdict == "type_monoculture"
    assert report.untyped_count == 1
    assert report.present_type_count == 1


def test_unrecognized_type_carried_not_counted() -> None:
    # A type NOT in known_types is untyped (carried, not forced).
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "wikipedia")), KNOWN,
    )
    assert report.present_type_count == 1  # only arxiv
    assert report.verdict == "type_monoculture"


def test_all_untyped_sources_still_measured() -> None:
    # All untyped -> present 0 -> type_monoculture (present <= 1); NOT unknown
    # (sources WERE cited). coverage_ratio = 0/5 = 0.0 (real measured).
    report = measure_source_type_coverage(
        srcs(("a", ""), ("b", "")), KNOWN,
    )
    assert report.cited_source_count == 2
    assert report.untyped_count == 2
    assert report.present_type_count == 0
    assert report.coverage_ratio == 0.0
    assert report.verdict == "type_monoculture"


# --- whitespace type handling ---------------------------------------------


def test_whitespace_type_treated_as_untyped() -> None:
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "   ")), KNOWN,
    )
    assert report.untyped_count == 1
    assert report.present_type_count == 1


# --- missing types reported ------------------------------------------------


def test_missing_types_in_notes() -> None:
    report = measure_source_type_coverage(
        srcs(("a", "arxiv"), ("b", "substack")), KNOWN,
    )
    joined = " ".join(report.notes)
    assert "missing types" in joined.lower()
    assert "journal" in joined  # a known type not present


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_promotes_to_broad() -> None:
    # 2 of 5 = 0.40 -> partial at default 0.60, broad at threshold 0.30.
    sources = srcs(("a", "arxiv"), ("b", "substack"))
    assert measure_source_type_coverage(sources, KNOWN).verdict == "partial_coverage"
    assert measure_source_type_coverage(sources, KNOWN, broad_threshold=0.30).verdict == "broad_coverage"


# --- validation ------------------------------------------------------------


def test_broad_threshold_out_of_range_raises() -> None:
    with pytest.raises(SourceTypeCoverageError, match="broad_threshold"):
        measure_source_type_coverage([], KNOWN, broad_threshold=1.5)


def test_empty_known_types_raises() -> None:
    with pytest.raises(SourceTypeCoverageError, match="known_types must be non-empty"):
        measure_source_type_coverage(srcs(("a", "arxiv")), [])


def test_empty_entry_in_known_types_raises() -> None:
    with pytest.raises(SourceTypeCoverageError, match="empty/whitespace"):
        measure_source_type_coverage(srcs(("a", "arxiv")), ["arxiv", "  "])


def test_empty_source_id_raises() -> None:
    with pytest.raises(SourceTypeCoverageError, match="source_id"):
        measure_source_type_coverage([TypedSource(source_id="  ", source_type="arxiv")], KNOWN)


def test_duplicate_source_id_raises() -> None:
    with pytest.raises(SourceTypeCoverageError, match="duplicate source_id"):
        measure_source_type_coverage(
            [TypedSource("a", "arxiv"), TypedSource("a", "substack")], KNOWN,
        )


# --- purity / determinism --------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_source_type_coverage(srcs(("a", "arxiv"), ("b", "substack")), KNOWN)
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    sources = srcs(("a", "arxiv"), ("b", "substack"), ("c", "journal"))
    first = measure_source_type_coverage(sources, KNOWN)
    second = measure_source_type_coverage(sources, KNOWN)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_source_type_coverage(srcs(("a", "arxiv")), KNOWN)
    joined = " ".join(report.notes)
    assert "source-type coverage" in joined
    assert "verdict type_monoculture" in joined

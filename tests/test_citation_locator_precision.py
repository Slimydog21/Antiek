"""Tests for the citation locator-precision axis (ask #7)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.citation_locator_precision import (
    CitationLocatorPrecisionReport,
    LocatorBucket,
    measure_citation_locator_precision,
)


def test_no_citations_is_unknown() -> None:
    report = measure_citation_locator_precision([])
    assert report.verdict == "unknown"
    assert report.citation_count == 0
    assert report.located_precise_fraction is None
    assert report.unlocated_fraction is None
    assert report.locator_distribution == ()
    assert report.authority == "advisory"


def test_all_anchored_is_anchored() -> None:
    report = measure_citation_locator_precision(
        [("c1", "quote"), ("c2", "paragraph"), ("c3", "page")]
    )
    assert report.verdict == "anchored"
    assert report.anchor_count == 3
    assert report.document_count == 0
    assert report.unlocated_count == 0
    assert report.located_count == 3
    assert report.located_precise_fraction == 1.0


def test_all_document_is_document_level() -> None:
    report = measure_citation_locator_precision(
        [("c1", "document"), ("c2", "document")]
    )
    assert report.verdict == "document_level"
    assert report.anchor_count == 0
    assert report.document_count == 2
    assert report.located_precise_fraction == 0.0


def test_all_unlocated_is_unlocated_state() -> None:
    # missing locators are distinct from document-level (a data gap, not a precision verdict)
    report = measure_citation_locator_precision([("c1", "unknown"), ("c2", "")])
    assert report.verdict == "unlocated"
    assert report.unlocated_count == 2
    assert report.located_count == 0
    assert report.located_precise_fraction is None
    assert report.unlocated_fraction == 1.0


def test_unrecognized_locator_type_defers_to_unlocated() -> None:
    report = measure_citation_locator_precision([("c1", "weirdtype")])
    assert report.verdict == "unlocated"
    assert report.unlocated_count == 1
    assert report.located_count == 0
    assert report.located_precise_fraction is None


def test_mixed_precision() -> None:
    # 2 anchor / 3 document (located) -> lpf 0.40 between thresholds
    report = measure_citation_locator_precision(
        [("c1", "quote"), ("c2", "document"), ("c3", "document"),
         ("c4", "document"), ("c5", "section")]
    )
    assert report.verdict == "mixed_precision"
    assert report.anchor_count == 2
    assert report.document_count == 3
    assert report.located_precise_fraction == pytest.approx(0.40)


def test_anchored_boundary_inclusive() -> None:
    # 3 anchor / 5 located -> lpf 0.60 == precise_threshold -> anchored
    report = measure_citation_locator_precision(
        [("c1", "quote"), ("c2", "document"), ("c3", "page"),
         ("c4", "document"), ("c5", "section")]
    )
    assert report.located_precise_fraction == pytest.approx(0.60)
    assert report.verdict == "anchored"


def test_document_level_boundary_inclusive() -> None:
    # 1 anchor / 5 located -> lpf 0.20 == vague_threshold -> document_level
    report = measure_citation_locator_precision(
        [("c1", "quote"), ("c2", "document"), ("c3", "document"),
         ("c4", "document"), ("c5", "document")]
    )
    assert report.located_precise_fraction == pytest.approx(0.20)
    assert report.verdict == "document_level"


def test_unlocated_does_not_masquerade_as_document_level() -> None:
    # 1 anchor, 1 document, 2 unlocated -> lpf over LOCATED only = 0.5 (mixed); unlocated carried
    report = measure_citation_locator_precision(
        [("c1", "quote"), ("c2", "unknown"), ("c3", "document"), ("c4", "")]
    )
    assert report.anchor_count == 1
    assert report.document_count == 1
    assert report.unlocated_count == 2
    assert report.located_count == 2
    assert report.located_precise_fraction == 0.5
    assert report.unlocated_fraction == 0.5
    assert report.verdict == "mixed_precision"


def test_locator_distribution_sorted_by_precision_rank_desc() -> None:
    report = measure_citation_locator_precision(
        [("c1", "document"), ("c2", "quote"), ("c3", "quote"), ("c4", "page")]
    )
    types = tuple(b.locator_type for b in report.locator_distribution)
    counts = tuple(b.count for b in report.locator_distribution)
    ranks = tuple(b.precision_rank for b in report.locator_distribution)
    assert types == ("quote", "page", "document")
    assert counts == (2, 1, 1)
    assert ranks == (4, 2, 0)


def test_whitespace_and_case_normalized() -> None:
    report = measure_citation_locator_precision([("c1", "Quote"), ("c2", " PAGE ")])
    assert report.anchor_count == 2
    assert report.verdict == "anchored"
    assert report.located_precise_fraction == 1.0


def test_single_anchored_and_single_document() -> None:
    assert measure_citation_locator_precision([("c", "quote")]).verdict == "anchored"
    assert measure_citation_locator_precision([("c", "document")]).verdict == "document_level"


def test_custom_thresholds_reclassify_mixed() -> None:
    mixed = [("c1", "quote"), ("c2", "document"), ("c3", "document"),
             ("c4", "document"), ("c5", "section")]  # lpf 0.40
    assert measure_citation_locator_precision(mixed).verdict == "mixed_precision"
    assert (
        measure_citation_locator_precision(mixed, precise_threshold=0.40).verdict == "anchored"
    )
    assert (
        measure_citation_locator_precision(mixed, vague_threshold=0.40).verdict == "document_level"
    )


def test_threshold_validation_rejects_out_of_range() -> None:
    c = [("c", "quote")]
    with pytest.raises(ValueError, match="precise_threshold"):
        measure_citation_locator_precision(c, precise_threshold=1.5)
    with pytest.raises(ValueError, match="vague_threshold"):
        measure_citation_locator_precision(c, vague_threshold=-0.1)
    with pytest.raises(ValueError, match="precise_threshold"):
        # precise below vague is invalid
        measure_citation_locator_precision(c, precise_threshold=0.20, vague_threshold=0.40)


def test_report_is_frozen_and_deterministic() -> None:
    citations = [("c1", "quote"), ("c2", "document"), ("c3", "page")]
    first = measure_citation_locator_precision(citations)
    second = measure_citation_locator_precision(citations)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: CitationLocatorPrecisionReport = measure_citation_locator_precision(
        [("c1", "quote"), ("c2", "document")]
    )
    assert isinstance(report, CitationLocatorPrecisionReport)
    assert all(isinstance(b, LocatorBucket) for b in report.locator_distribution)
    assert isinstance(report.notes, tuple)
    assert report.precise_threshold == 0.60
    assert report.vague_threshold == 0.20
    assert report.authority == "advisory"

"""Tests for the annotation interrogative-density axis (ask #2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.annotation_interrogative_density import (
    AnnotationInterrogativeDensityReport,
    measure_annotation_interrogative_density,
)


def test_no_annotations_is_unknown() -> None:
    report = measure_annotation_interrogative_density([])
    assert report.verdict == "unknown"
    assert report.annotation_count == 0
    assert report.interrogative_fraction is None
    assert report.interrogative_opener_fraction is None
    assert report.authority == "advisory"


def test_all_questioning() -> None:
    report = measure_annotation_interrogative_density(
        ["Why does this happen?", "How is X defined?"]
    )
    assert report.verdict == "questioning"
    assert report.annotation_count == 2
    assert report.interrogative_count == 2
    assert report.interrogative_fraction == 1.0
    assert report.interrogative_opener_count == 2
    assert report.interrogative_opener_fraction == 1.0
    assert report.non_interrogative_count == 0


def test_all_declarative() -> None:
    report = measure_annotation_interrogative_density(
        ["This is a key finding.", "Note the pattern here."]
    )
    assert report.verdict == "declarative"
    assert report.interrogative_count == 0
    assert report.interrogative_fraction == 0.0
    assert report.interrogative_opener_count == 0
    assert report.non_interrogative_count == 2


def test_mixed_mode() -> None:
    # 1 of 5 has "?" -> 0.20 (between 0.10 and 0.40)
    report = measure_annotation_interrogative_density(
        ["Why?", "Note A.", "Note B.", "Note C.", "Note D."]
    )
    assert report.verdict == "mixed_mode"
    assert report.interrogative_count == 1
    assert report.interrogative_fraction == 0.20
    assert report.non_interrogative_count == 4


def test_single_questioning_annotation() -> None:
    report = measure_annotation_interrogative_density(["Why?"])
    assert report.verdict == "questioning"
    assert report.interrogative_fraction == 1.0


def test_single_declarative_annotation() -> None:
    report = measure_annotation_interrogative_density(["A declarative note."])
    assert report.verdict == "declarative"
    assert report.interrogative_fraction == 0.0


def test_interrogative_opener_without_question_mark() -> None:
    # "Why this matters" -> no "?", but opens with "why" -> opener-only interrogative
    report = measure_annotation_interrogative_density(["Why this matters"])
    assert report.interrogative_count == 0
    assert report.interrogative_fraction == 0.0
    assert report.verdict == "declarative"
    assert report.interrogative_opener_count == 1
    assert report.interrogative_opener_fraction == 1.0


def test_question_mark_anywhere_counts_lexical_floor() -> None:
    # a "?" embedded in a quote still marks the annotation interrogative (lexical floor)
    report = measure_annotation_interrogative_density(['She said "what?" and left'])
    assert report.interrogative_count == 1
    assert report.interrogative_fraction == 1.0
    assert report.verdict == "questioning"
    assert report.interrogative_opener_count == 0  # first token "she" is not an opener


def test_leading_punctuation_stripped_for_opener_detection() -> None:
    report = measure_annotation_interrogative_density(['"why does X happen"'])
    assert report.interrogative_count == 0  # no "?"
    assert report.interrogative_opener_count == 1  # leading quote stripped -> "why"


def test_questioning_boundary_inclusive() -> None:
    # 2 of 5 -> 0.40 == interrogative_threshold -> questioning
    report = measure_annotation_interrogative_density(
        ["Why?", "How?", "A.", "B.", "C."]
    )
    assert report.interrogative_fraction == 0.40
    assert report.verdict == "questioning"


def test_declarative_boundary_inclusive() -> None:
    # 1 of 10 -> 0.10 == declarative_threshold -> declarative
    annotations = ["Q?"] + [chr(c) for c in range(ord("a"), ord("a") + 9)]
    report = measure_annotation_interrogative_density(annotations)
    assert report.interrogative_fraction == 0.10
    assert report.verdict == "declarative"


def test_custom_thresholds_reclassify_mixed() -> None:
    mixed = ["Why?", "Note A.", "Note B.", "Note C.", "Note D."]  # 0.20
    assert measure_annotation_interrogative_density(mixed).verdict == "mixed_mode"
    assert (
        measure_annotation_interrogative_density(mixed, interrogative_threshold=0.20).verdict
        == "questioning"
    )
    assert (
        measure_annotation_interrogative_density(mixed, declarative_threshold=0.30).verdict
        == "declarative"
    )


def test_threshold_validation_rejects_out_of_range() -> None:
    ann = ["Why?"]
    with pytest.raises(ValueError, match="interrogative_threshold"):
        measure_annotation_interrogative_density(ann, interrogative_threshold=1.5)
    with pytest.raises(ValueError, match="declarative_threshold"):
        measure_annotation_interrogative_density(ann, declarative_threshold=-0.1)
    with pytest.raises(ValueError, match="interrogative_threshold"):
        # interrogative below declarative is invalid
        measure_annotation_interrogative_density(
            ann, interrogative_threshold=0.10, declarative_threshold=0.40
        )


def test_report_is_frozen_and_deterministic() -> None:
    annotations = ["Why?", "How?", "A note.", "Another."]
    first = measure_annotation_interrogative_density(annotations)
    second = measure_annotation_interrogative_density(annotations)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: AnnotationInterrogativeDensityReport = measure_annotation_interrogative_density(
        ["Why?", "A note."]
    )
    assert isinstance(report, AnnotationInterrogativeDensityReport)
    assert isinstance(report.notes, tuple)
    assert report.interrogative_threshold == 0.40
    assert report.declarative_threshold == 0.10
    assert report.authority == "advisory"

"""Tests for the annotation-substantiveness axis (reading engagement depth — asks #2/#3).

Pure lexical arithmetic — distinctive terms (stop-words stripped), hand-counted.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.annotation_substantiveness import (
    AnnotationSubstantivenessError,
    measure_annotation_substantiveness,
)

# --- substantive (>= floor distinct content terms) ------------------------


def test_substantive_above_floor() -> None:
    # "alpha beta gamma delta echo" = 5 distinct content terms -> substantive (>= 5).
    report = measure_annotation_substantiveness("alpha beta gamma delta echo")
    assert report.verdict == "substantive"
    assert report.substantive_term_count == 5
    assert report.annotation_token_count == 5
    assert report.substantiveness_ratio == 1.0
    assert report.authority == "advisory"


def test_substantive_at_floor_boundary_is_a_hit() -> None:
    # exactly 5 distinct content terms -> substantive (>= boundary).
    report = measure_annotation_substantiveness("alpha beta gamma delta echo")
    assert report.verdict == "substantive"


def test_substantive_with_stop_words_interleaved() -> None:
    # "does alpha contradict beta finding gamma delta" -> content {alpha,contradict,beta,finding,gamma,delta}=6
    report = measure_annotation_substantiveness("does alpha contradict beta finding gamma delta")
    assert report.verdict == "substantive"
    assert report.substantive_term_count == 6
    assert report.annotation_token_count == 7
    assert report.substantiveness_ratio == pytest.approx(6 / 7)


# --- trivial (thin — some content terms but < floor) ----------------------


def test_trivial_below_floor() -> None:
    # "alpha beta" = 2 content terms (< 5) -> trivial.
    report = measure_annotation_substantiveness("alpha beta")
    assert report.verdict == "trivial"
    assert report.substantive_term_count == 2
    assert report.substantiveness_ratio == 1.0


def test_trivial_just_below_floor() -> None:
    # 4 distinct content terms (< 5) -> trivial.
    report = measure_annotation_substantiveness("alpha beta gamma delta")
    assert report.verdict == "trivial"
    assert report.substantive_term_count == 4


# --- bare (annotation exists but ALL glue — zero information) -------------


def test_bare_all_stop_words() -> None:
    # "the and of is" = 0 content terms, 4 tokens -> bare (NOT unknown).
    report = measure_annotation_substantiveness("the and of is")
    assert report.verdict == "bare"
    assert report.substantive_term_count == 0
    assert report.annotation_token_count == 4
    assert report.substantiveness_ratio == 0.0  # real measured value, not None


def test_bare_reaction_words() -> None:
    # "yes ok lol" — these are in the stop-word set -> bare.
    report = measure_annotation_substantiveness("yes ok lol")
    assert report.verdict == "bare"
    assert report.substantive_term_count == 0


def test_bare_is_not_unknown() -> None:
    # An annotation that exists but carries zero information -> bare (measured),
    # NOT unknown.
    report = measure_annotation_substantiveness("ok")
    assert report.verdict == "bare"
    assert report.annotation_token_count == 1
    assert report.substantiveness_ratio == 0.0


# --- unknown (no annotation recorded) -------------------------------------


def test_unknown_when_none() -> None:
    report = measure_annotation_substantiveness(None)
    assert report.verdict == "unknown"
    assert report.substantiveness_ratio is None  # defer, never 0.0


def test_unknown_when_empty_string() -> None:
    report = measure_annotation_substantiveness("")
    assert report.verdict == "unknown"
    assert report.substantiveness_ratio is None


def test_unknown_when_whitespace_only() -> None:
    report = measure_annotation_substantiveness("   ")
    assert report.verdict == "unknown"


# --- the three-way distinction: bare != trivial != unknown ---------------


def test_bare_trivial_substantive_are_distinct() -> None:
    bare = measure_annotation_substantiveness("ok")
    trivial = measure_annotation_substantiveness("alpha beta")
    substantive = measure_annotation_substantiveness("alpha beta gamma delta echo")
    unknown = measure_annotation_substantiveness(None)
    assert {bare.verdict, trivial.verdict, substantive.verdict, unknown.verdict} == {
        "bare", "trivial", "substantive", "unknown",
    }


# --- case + stop-word floor -----------------------------------------------


def test_case_insensitive() -> None:
    report = measure_annotation_substantiveness("ALPHA Beta GAMMA Delta Echo")
    assert report.verdict == "substantive"
    assert report.substantive_term_count == 5


def test_repeated_content_term_counts_distinct_once() -> None:
    # "alpha alpha alpha beta beta gamma" -> distinct content {alpha,beta,gamma}=3
    report = measure_annotation_substantiveness("alpha alpha alpha beta beta gamma")
    assert report.substantive_term_count == 3  # distinct, not total
    assert report.annotation_token_count == 6
    assert report.substantiveness_ratio == pytest.approx(3 / 6)
    assert report.verdict == "trivial"  # 3 < 5


# --- custom floor ---------------------------------------------------------


def test_custom_floor_promotes_to_substantive() -> None:
    # 3 content terms -> trivial at default floor 5, substantive at floor 2.
    ann = "alpha beta gamma"
    assert measure_annotation_substantiveness(ann).verdict == "trivial"
    assert measure_annotation_substantiveness(ann, substantive_floor=2).verdict == "substantive"


def test_custom_floor_at_boundary() -> None:
    # floor 3: exactly 3 content terms -> substantive (>= boundary).
    report = measure_annotation_substantiveness("alpha beta gamma", substantive_floor=3)
    assert report.verdict == "substantive"


# --- validation -----------------------------------------------------------


def test_floor_below_one_raises() -> None:
    with pytest.raises(AnnotationSubstantivenessError, match="substantive_floor"):
        measure_annotation_substantiveness("alpha", substantive_floor=0)


# --- purity / determinism -------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_annotation_substantiveness("alpha beta gamma delta echo")
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    ann = "alpha beta gamma delta echo foxtrot"
    first = measure_annotation_substantiveness(ann)
    second = measure_annotation_substantiveness(ann)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_annotation_substantiveness("alpha beta gamma delta echo")
    joined = " ".join(report.notes)
    assert "annotation-substantiveness" in joined
    assert "verdict substantive" in joined

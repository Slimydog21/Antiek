"""Tests for the citation-relevance axis (asks #1/#7/#14).

Measures citation QUALITY — when an insight cites a source, is that source
relevant to the insight's claim? Jaccard over distinctive terms. Distinct from
provenance_coverage #1940 (citation PRESENCE) and validate_refs (citation
VALIDITY). Exercises well_cited/misattributed/partially_misattributed/unknown
verdicts, the well_cited-vs-unknown distinction, threshold boundaries,
all-glue exclusion, validation, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.citation_relevance import (
    CitedInsight,
    measure_citation_relevance,
)

# --- unknown --------------------------------------------------------------


def test_unknown_when_no_cited_insights() -> None:
    r = measure_citation_relevance([])
    assert r.verdict == "unknown"
    assert r.pair_count == 0
    assert r.mean_relevance is None
    assert r.max_relevance is None
    assert r.misattribution_rate is None
    assert r.authority == "advisory"


def test_unknown_when_all_insights_are_glue() -> None:
    r = measure_citation_relevance(
        [CitedInsight("i1", "s1", "the of and", "alpha beta")]
    )
    assert r.verdict == "unknown"
    assert r.unmeasurable_pair_count == 1


def test_unknown_when_insight_text_none() -> None:
    r = measure_citation_relevance(
        [CitedInsight("i1", "s1", None, "alpha beta")]
    )
    assert r.verdict == "unknown"
    assert r.unmeasurable_pair_count == 1


# --- well_cited -----------------------------------------------------------


def test_well_cited_all_relevant() -> None:
    r = measure_citation_relevance(
        [
            CitedInsight("i1", "s1", "alpha beta gamma", "alpha beta delta"),
            CitedInsight("i2", "s2", "echo foxtrot", "echo golf"),
        ]
    )
    assert r.verdict == "well_cited"
    assert r.pair_count == 2
    assert r.misattribution_count == 0
    assert r.misattribution_rate == 0.0
    # i1: intersection {alpha,beta}=2, union {alpha,beta,gamma,delta}=4 -> 0.5.
    assert r.pairs[0].relevance == pytest.approx(0.5)


def test_well_cited_boundary_at_threshold() -> None:
    # relevance exactly 0.10 (== threshold) -> NOT misattributed (< threshold).
    # Jaccard = intersection / union = 1 / 10. insight 5 distinctive terms,
    # source 6 distinctive terms, 1 shared (alpha) -> union = 5+6-1 = 10.
    # (Must use non-stop-word tokens; single letters like "a"/"i" are stop-words.)
    r = measure_citation_relevance(
        [CitedInsight(
            "i1", "s1",
            "alpha beta gamma delta echo",
            "alpha foxtrot golf hotel india juliet",
        )]
    )
    assert r.pairs[0].relevance == pytest.approx(1 / 10)
    assert r.verdict == "well_cited"


# --- misattributed --------------------------------------------------------


def test_misattributed_majority_irrelevant() -> None:
    # 2 of 3 below threshold (0.10): i1 shares nothing, i2 shares nothing, i3 shares.
    r = measure_citation_relevance(
        [
            CitedInsight("i1", "s1", "alpha beta", "gamma delta echo foxtrot"),
            CitedInsight("i2", "s2", "golf hotel", "india juliet kilo lima"),
            CitedInsight("i3", "s3", "mike november", "mike oscar papa"),
        ]
    )
    assert r.verdict == "misattributed"
    assert r.misattribution_count == 2
    assert r.misattribution_rate == pytest.approx(2 / 3)
    assert len(r.misattributed_pair_ids) == 2


def test_misattributed_all_irrelevant() -> None:
    r = measure_citation_relevance(
        [CitedInsight("i1", "s1", "alpha beta", "gamma delta")]
    )
    assert r.verdict == "misattributed"
    assert r.misattribution_count == 1
    assert r.misattribution_rate == 1.0
    assert r.pairs[0].relevance == 0.0


# --- partially_misattributed ----------------------------------------------


def test_partially_misattributed_minority() -> None:
    # 1 of 3 misattributed -> rate 0.33 < 0.50 majority -> partially.
    r = measure_citation_relevance(
        [
            CitedInsight("i1", "s1", "alpha beta", "gamma delta"),
            CitedInsight("i2", "s2", "echo foxtrot", "echo golf"),
            CitedInsight("i3", "s3", "hotel india", "hotel juliet"),
        ]
    )
    assert r.verdict == "partially_misattributed"
    assert r.misattribution_count == 1
    assert r.misattribution_rate == pytest.approx(1 / 3)


def test_partially_misattributed_boundary_half() -> None:
    # exactly half misattributed -> rate 0.50 >= majority_threshold 0.50 -> misattributed.
    r = measure_citation_relevance(
        [
            CitedInsight("i1", "s1", "alpha beta", "gamma delta"),
            CitedInsight("i2", "s2", "echo foxtrot", "echo golf"),
        ]
    )
    assert r.misattribution_rate == 0.5
    assert r.verdict == "misattributed"


# --- relevance math --------------------------------------------------------


def test_relevance_zero_when_source_all_glue() -> None:
    # Source is all stop-words -> no distinctive terms -> union = insight terms,
    # intersection empty -> relevance 0.0 (real signal: source provides nothing).
    r = measure_citation_relevance(
        [CitedInsight("i1", "s1", "alpha beta", "the of and")]
    )
    assert r.pair_count == 1  # measured (insight has terms; source doesn't, but that's a real 0.0)
    assert r.pairs[0].relevance == 0.0
    assert r.verdict == "misattributed"


def test_matched_terms_auditable() -> None:
    r = measure_citation_relevance(
        [CitedInsight("i1", "s1", "zebra alpha mango", "zebra beta mango")]
    )
    assert r.pairs[0].matched_terms == ("mango", "zebra")


def test_mean_and_max_relevance() -> None:
    r = measure_citation_relevance(
        [
            CitedInsight("i1", "s1", "alpha beta", "alpha gamma"),  # 1/3
            CitedInsight("i2", "s2", "delta echo", "delta echo foxtrot"),  # 2/3
        ]
    )
    assert r.mean_relevance == pytest.approx(0.5)
    assert r.max_relevance == pytest.approx(2 / 3)


# --- custom thresholds -----------------------------------------------------


def test_custom_relevance_threshold() -> None:
    # relevance 0.5: well_cited at threshold 0.10, misattributed at 0.60.
    ci = [CitedInsight("i1", "s1", "alpha beta", "alpha gamma")]
    r_default = measure_citation_relevance(ci)
    assert r_default.verdict == "well_cited"
    r_strict = measure_citation_relevance(ci, relevance_threshold=0.60)
    assert r_strict.verdict == "misattributed"


# --- validation ------------------------------------------------------------


def test_invalid_relevance_threshold_raises() -> None:
    with pytest.raises(ValueError):
        measure_citation_relevance([], relevance_threshold=0.0)
    with pytest.raises(ValueError):
        measure_citation_relevance([], relevance_threshold=1.01)


def test_invalid_majority_threshold_raises() -> None:
    with pytest.raises(ValueError):
        measure_citation_relevance([], majority_threshold=0.0)
    with pytest.raises(ValueError):
        measure_citation_relevance([], majority_threshold=1.01)


# --- purity / determinism / immutability ----------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    ci = [CitedInsight("i1", "s1", "alpha beta", "alpha gamma")]
    assert measure_citation_relevance(ci) == measure_citation_relevance(ci)


def test_report_is_frozen_immutable() -> None:
    r = measure_citation_relevance([CitedInsight("i1", "s1", "alpha", "alpha")])
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "misattributed"  # type: ignore[misc]


def test_notes_carry_context() -> None:
    r = measure_citation_relevance(
        [CitedInsight("i1", "s1", "alpha beta", "gamma delta")]
    )
    assert any("misattributed" in note for note in r.notes)
    assert any("relevance" in note for note in r.notes)

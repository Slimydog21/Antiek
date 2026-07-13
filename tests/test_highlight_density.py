"""Tests for the highlight-density axis (reading engagement — asks #2/#3/#6).

Pure arithmetic — token counts are integers, union sizes computed by hand.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.highlight_density import (
    HighlightDensityError,
    HighlightSpan,
    measure_highlight_density,
)

# --- verdicts ---------------------------------------------------------------


def test_dense_above_threshold() -> None:
    # 100-token passage, 25 tokens highlighted -> coverage 0.25 >= 0.20 -> dense.
    report = measure_highlight_density(100, [HighlightSpan(0, 25)])
    assert report.verdict == "dense"
    assert report.coverage_ratio == pytest.approx(0.25)
    assert report.highlight_count == 1
    assert report.highlighted_token_count == 25
    assert report.authority == "advisory"


def test_dense_at_threshold_boundary_is_a_hit() -> None:
    # coverage 0.20 == threshold -> dense (>= boundary).
    report = measure_highlight_density(100, [HighlightSpan(0, 20)])
    assert report.verdict == "dense"
    assert report.coverage_ratio == pytest.approx(0.20)


def test_selective_below_threshold() -> None:
    # 100-token passage, 10 tokens highlighted -> coverage 0.10 < 0.20 -> selective.
    report = measure_highlight_density(100, [HighlightSpan(0, 10)])
    assert report.verdict == "selective"
    assert report.coverage_ratio == pytest.approx(0.10)


def test_selective_just_below_threshold() -> None:
    # coverage 0.19 -> selective.
    report = measure_highlight_density(100, [HighlightSpan(0, 19)])
    assert report.verdict == "selective"


# --- unmarked (load-bearing honest state — NOT unknown) --------------------


def test_unmarked_when_passage_exists_zero_highlights() -> None:
    report = measure_highlight_density(100, [])
    assert report.verdict == "unmarked"
    assert report.highlight_count == 0
    assert report.highlighted_token_count == 0
    assert report.coverage_ratio == 0.0  # real measured value, not None
    assert report.density_per_100 == 0.0


# --- unknown (load-bearing honest state — NOT unmarked) --------------------


def test_unknown_when_zero_token_passage() -> None:
    report = measure_highlight_density(0, [])
    assert report.verdict == "unknown"
    assert report.coverage_ratio is None  # defer, never 0.0
    assert report.density_per_100 is None


# --- union of overlapping spans (load-bearing — no double-count) -----------


def test_disjoint_spans_sum() -> None:
    # Two disjoint spans: [0,10) + [50,60) = 20 tokens.
    report = measure_highlight_density(100, [HighlightSpan(0, 10), HighlightSpan(50, 60)])
    assert report.highlighted_token_count == 20
    assert report.coverage_ratio == pytest.approx(0.20)
    assert report.verdict == "dense"


def test_overlapping_spans_union_not_sum() -> None:
    # [0,20) + [10,30) overlap -> union [0,30) = 30 tokens, NOT 40.
    report = measure_highlight_density(100, [HighlightSpan(0, 20), HighlightSpan(10, 30)])
    assert report.highlighted_token_count == 30
    assert report.coverage_ratio == pytest.approx(0.30)


def test_nested_spans_union() -> None:
    # [0,40) contains [10,20) -> union [0,40) = 40, NOT 50.
    report = measure_highlight_density(100, [HighlightSpan(0, 40), HighlightSpan(10, 20)])
    assert report.highlighted_token_count == 40


def test_touching_spans_union() -> None:
    # [0,20) + [20,40) touch at 20 -> union [0,40) = 40 (touching ranges merge).
    report = measure_highlight_density(100, [HighlightSpan(0, 20), HighlightSpan(20, 40)])
    assert report.highlighted_token_count == 40


def test_triple_overlap_complex_union() -> None:
    # [0,10), [5,25), [20,30) -> union [0,30) = 30.
    report = measure_highlight_density(
        100, [HighlightSpan(0, 10), HighlightSpan(5, 25), HighlightSpan(20, 30)]
    )
    assert report.highlighted_token_count == 30


def test_many_small_picks_high_count_low_coverage() -> None:
    # 5 disjoint 2-token spans = 10 tokens, 5 highlights (high granularity, low coverage).
    report = measure_highlight_density(
        100,
        [HighlightSpan(0, 2), HighlightSpan(10, 12), HighlightSpan(20, 22),
         HighlightSpan(30, 32), HighlightSpan(40, 42)],
    )
    assert report.highlight_count == 5
    assert report.highlighted_token_count == 10
    assert report.coverage_ratio == pytest.approx(0.10)
    assert report.density_per_100 == pytest.approx(5.0)
    assert report.verdict == "selective"


# --- custom threshold -------------------------------------------------------


def test_custom_threshold_promotes_to_dense() -> None:
    # coverage 0.10 -> selective at default 0.20, dense at threshold 0.05.
    report_default = measure_highlight_density(100, [HighlightSpan(0, 10)])
    assert report_default.verdict == "selective"
    report_loose = measure_highlight_density(100, [HighlightSpan(0, 10)], dense_threshold=0.05)
    assert report_loose.verdict == "dense"
    assert report_loose.dense_threshold == 0.05


def test_threshold_zero_only_zero_coverage_is_not_dense() -> None:
    # threshold 0.0: any coverage > 0 is dense; but 0 coverage is unmarked.
    report = measure_highlight_density(100, [HighlightSpan(0, 1)], dense_threshold=0.0)
    assert report.verdict == "dense"


# --- validation (load-bearing invariants) -----------------------------------


def test_negative_passage_token_count_raises() -> None:
    with pytest.raises(HighlightDensityError, match="passage_token_count"):
        measure_highlight_density(-1, [])


def test_dense_threshold_out_of_range_raises() -> None:
    with pytest.raises(HighlightDensityError, match="dense_threshold"):
        measure_highlight_density(100, [], dense_threshold=1.5)
    with pytest.raises(HighlightDensityError, match="dense_threshold"):
        measure_highlight_density(100, [], dense_threshold=-0.1)


def test_span_out_of_bounds_raises() -> None:
    with pytest.raises(HighlightDensityError, match="exceeds passage_token_count"):
        measure_highlight_density(50, [HighlightSpan(0, 60)])


def test_inverted_span_raises() -> None:
    with pytest.raises(HighlightDensityError, match="non-empty"):
        measure_highlight_density(100, [HighlightSpan(20, 20)])  # start == end
    with pytest.raises(HighlightDensityError, match="non-empty"):
        measure_highlight_density(100, [HighlightSpan(30, 10)])  # start > end


def test_negative_span_offset_raises() -> None:
    with pytest.raises(HighlightDensityError, match=">= 0"):
        measure_highlight_density(100, [HighlightSpan(-5, 10)])


# --- purity / determinism ---------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_highlight_density(100, [HighlightSpan(0, 20)])
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    spans = [HighlightSpan(0, 10), HighlightSpan(50, 60)]
    first = measure_highlight_density(100, spans)
    second = measure_highlight_density(100, spans)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_highlight_density(100, [HighlightSpan(0, 25)])
    joined = " ".join(report.notes)
    assert "highlight-density" in joined
    assert "verdict dense" in joined
    assert "coverage 25%" in joined

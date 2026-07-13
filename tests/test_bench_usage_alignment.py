"""Tests for the bench usage-alignment axis (ask #11).

Every fixture is hand-counted: shares, overlaps, and alignment are verified by
inspection before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.bench_usage_alignment import (
    BenchUsageAlignmentReport,
    FamilyAlignment,
    measure_bench_usage_alignment,
)

# ---------------------------------------------------------------------------
# Base cases — unknown when either distribution is empty.
# ---------------------------------------------------------------------------


def test_no_bench_tasks_is_unknown() -> None:
    report = measure_bench_usage_alignment({}, {"reading": 5})
    assert report.verdict == "unknown"
    assert report.alignment is None
    assert report.total_variation_distance is None
    assert report.family_alignments == ()
    assert report.authority == "advisory"


def test_no_usage_is_unknown() -> None:
    report = measure_bench_usage_alignment({"reading": 5}, {})
    assert report.verdict == "unknown"
    assert report.alignment is None


def test_both_empty_is_unknown() -> None:
    report = measure_bench_usage_alignment({}, {})
    assert report.verdict == "unknown"
    assert report.alignment is None
    assert report.notes[0].startswith("no bench tasks")


def test_zero_counts_treated_as_empty() -> None:
    # All-zero counts (no positive mass) -> unknown on both sides.
    report = measure_bench_usage_alignment({"reading": 0}, {"reading": 0})
    assert report.verdict == "unknown"


# ---------------------------------------------------------------------------
# Aligned — perfect mirror of usage.
# ---------------------------------------------------------------------------


def test_perfectly_aligned() -> None:
    report = measure_bench_usage_alignment(
        {"reading": 3, "research": 7}, {"reading": 3, "research": 7}
    )
    assert report.alignment == pytest.approx(1.0)
    assert report.total_variation_distance == pytest.approx(0.0)
    assert report.verdict == "aligned"
    assert report.bench_only_families == ()
    assert report.usage_only_families == ()
    assert report.family_count == 2


def test_aligned_within_threshold() -> None:
    # bench shares slightly off but overlap >= 0.80.
    # bench {a:4, b:6}=10, usage {a:3, b:7}=10 -> a: min(0.4,0.3)=0.3, b: min(0.6,0.7)=0.6 -> 0.9
    report = measure_bench_usage_alignment(
        {"a": 4, "b": 6}, {"a": 3, "b": 7}
    )
    assert report.alignment == pytest.approx(0.9)
    assert report.verdict == "aligned"


# ---------------------------------------------------------------------------
# Drifted — proportions off, no blind spots.
# ---------------------------------------------------------------------------


def test_drifted_proportions_off() -> None:
    # bench {reading:1, research:9}=10, usage {reading:5, research:5}=10
    # reading: min(0.1,0.5)=0.1, research: min(0.9,0.5)=0.5 -> 0.6
    report = measure_bench_usage_alignment(
        {"reading": 1, "research": 9}, {"reading": 5, "research": 5}
    )
    assert report.alignment == pytest.approx(0.6)
    assert report.total_variation_distance == pytest.approx(0.4)
    assert report.verdict == "drifted"
    assert report.usage_only_families == ()


def test_drifted_with_bench_only_over_built() -> None:
    # bench tests a surface nobody uses -> over-built, but no blind spots -> drifted.
    # bench {reading:5, niche:5}=10, usage {reading:10}=10
    # reading: min(0.5,1.0)=0.5, niche: min(0.5,0.0)=0.0 -> 0.5
    report = measure_bench_usage_alignment(
        {"reading": 5, "niche": 5}, {"reading": 10}
    )
    assert report.alignment == pytest.approx(0.5)
    assert report.bench_only_families == ("niche",)
    assert report.usage_only_families == ()
    assert report.verdict == "drifted"


# ---------------------------------------------------------------------------
# Blind spots — usage on a surface the bench never tests (worst drift).
# ---------------------------------------------------------------------------


def test_blind_spots_usage_untested() -> None:
    # bench {reading:10}, usage {reading:5, research:5} -> research is a blind spot.
    # reading: min(1.0,0.5)=0.5, research: min(0.0,0.5)=0.0 -> 0.5
    report = measure_bench_usage_alignment(
        {"reading": 10}, {"reading": 5, "research": 5}
    )
    assert report.alignment == pytest.approx(0.5)
    assert report.usage_only_families == ("research",)
    assert report.verdict == "blind_spots"


def test_blind_spots_takes_priority_over_alignment() -> None:
    # Even high overlap on covered families, a blind spot wins.
    # bench {a:5,b:5}=10, usage {a:5,b:5,new:1}=11 -> a: min(0.5,0.454)=0.454, b: same, new: 0
    # alignment ~0.909 but new is usage_only -> blind_spots.
    report = measure_bench_usage_alignment(
        {"a": 5, "b": 5}, {"a": 5, "b": 5, "new": 1}
    )
    assert report.alignment is not None
    assert report.alignment == pytest.approx(5 / 11 * 2)
    assert report.alignment > 0.80
    assert report.usage_only_families == ("new",)
    assert report.verdict == "blind_spots"


def test_perfectly_disjoint_is_blind_spots() -> None:
    # bench {a:10}, usage {b:10} -> no overlap, b is blind spot, a is bench-only.
    report = measure_bench_usage_alignment({"a": 10}, {"b": 10})
    assert report.alignment == pytest.approx(0.0)
    assert report.total_variation_distance == pytest.approx(1.0)
    assert report.usage_only_families == ("b",)
    assert report.bench_only_families == ("a",)
    assert report.verdict == "blind_spots"


# ---------------------------------------------------------------------------
# Per-family auditability.
# ---------------------------------------------------------------------------


def test_family_alignments_sorted_by_abs_gap() -> None:
    # bench {a:1,b:4,c:5}=10, usage {a:5,b:5}=10
    # a: bs=0.1 us=0.5 gap=-0.4 ; b: bs=0.4 us=0.5 gap=-0.1 ; c: bs=0.5 us=0.0 gap=+0.5
    report = measure_bench_usage_alignment(
        {"a": 1, "b": 4, "c": 5}, {"a": 5, "b": 5}
    )
    families = [fa.family for fa in report.family_alignments]
    # c (gap 0.5) first, then a (gap 0.4), then b (gap 0.1).
    assert families == ["c", "a", "b"]
    c_align = next(fa for fa in report.family_alignments if fa.family == "c")
    assert c_align.bench_count == 5
    assert c_align.usage_count == 0
    assert c_align.bench_share == pytest.approx(0.5)
    assert c_align.usage_share == pytest.approx(0.0)
    assert c_align.share_gap == pytest.approx(0.5)


def test_family_alignment_fields() -> None:
    report = measure_bench_usage_alignment(
        {"reading": 3, "research": 7}, {"reading": 3, "research": 7}
    )
    assert all(isinstance(fa, FamilyAlignment) for fa in report.family_alignments)
    reading = next(fa for fa in report.family_alignments if fa.family == "reading")
    assert reading.bench_share == pytest.approx(0.3)
    assert reading.usage_share == pytest.approx(0.3)
    assert reading.share_gap == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_alignment_threshold_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="alignment_threshold"):
        measure_bench_usage_alignment({"a": 1}, {"a": 1}, alignment_threshold=0.0)
    with pytest.raises(ValueError, match="alignment_threshold"):
        measure_bench_usage_alignment({"a": 1}, {"a": 1}, alignment_threshold=1.5)


def test_custom_threshold_reclassifies_aligned_to_drifted() -> None:
    # overlap 0.9: aligned at 0.80, drifted at 0.95.
    counts = {"a": 4, "b": 6}
    usage = {"a": 3, "b": 7}
    assert measure_bench_usage_alignment(counts, usage).verdict == "aligned"
    assert (
        measure_bench_usage_alignment(counts, usage, alignment_threshold=0.95).verdict
        == "drifted"
    )


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_bench_usage_alignment({"a": 5}, {"a": 5})
    with pytest.raises(FrozenInstanceError):
        report.alignment = 0.1  # type: ignore[misc]


def test_deterministic_output() -> None:
    bench = {"a": 1, "b": 4, "c": 5}
    usage = {"a": 5, "b": 5}
    assert measure_bench_usage_alignment(bench, usage) == measure_bench_usage_alignment(
        bench, usage
    )


def test_report_is_bench_usage_alignment_report_instance() -> None:
    report = measure_bench_usage_alignment({"a": 5}, {"a": 5})
    assert isinstance(report, BenchUsageAlignmentReport)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_bench_usage_alignment(
        {"reading": 1, "research": 9}, {"reading": 5, "research": 5}
    )
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)
    assert any("alignment" in n.lower() for n in report.notes)

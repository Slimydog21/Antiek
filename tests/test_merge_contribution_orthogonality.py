"""Tests for the merge contribution-orthogonality axis (ask #3)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.merge_contribution_orthogonality import (
    measure_merge_contribution_orthogonality,
)

# ---------------------------------------------------------------------------
# Base cases — honest defer states.
# ---------------------------------------------------------------------------

def test_zero_parents_is_unknown() -> None:
    report = measure_merge_contribution_orthogonality([])
    assert report.verdict == "unknown"
    assert report.parent_count == 0
    assert report.mean_overlap is None
    assert report.orthogonality is None
    assert report.pair_overlaps == ()


def test_one_parent_is_single_input() -> None:
    report = measure_merge_contribution_orthogonality(["alpha beta"])
    assert report.verdict == "single_input"
    assert report.parent_count == 1
    assert report.pair_count == 0
    assert report.mean_overlap is None


def test_two_glue_parents_is_unmeasurable() -> None:
    # Both parents have no distinctive terms (only stop-words).
    report = measure_merge_contribution_orthogonality(["the and of", "is a to"])
    assert report.verdict == "unmeasurable"
    assert report.parent_count == 2
    assert report.pair_count == 1
    assert report.measurable_pair_count == 0
    assert report.mean_overlap is None
    # None is NEVER a fabricated 0.0 — distinct from a measured 0.0 overlap.
    assert report.orthogonality is None


# ---------------------------------------------------------------------------
# Orthogonal — disjoint content.
# ---------------------------------------------------------------------------

def test_disjoint_parents_are_highly_orthogonal() -> None:
    # A={alpha,beta}, B={gamma,delta}. overlap=0/4=0.0.
    report = measure_merge_contribution_orthogonality(["alpha beta", "gamma delta"])
    assert report.verdict == "highly_orthogonal"
    assert report.mean_overlap == 0.0
    assert report.orthogonality == 1.0
    assert report.measurable_pair_count == 1
    assert report.max_pair_overlap == 0.0


# ---------------------------------------------------------------------------
# Overlapping — restated content.
# ---------------------------------------------------------------------------

def test_identical_parents_are_highly_overlapping() -> None:
    # Same content -> overlap=1.0.
    report = measure_merge_contribution_orthogonality(
        ["alpha beta gamma", "alpha beta gamma"]
    )
    assert report.verdict == "highly_overlapping"
    assert report.mean_overlap == 1.0
    assert report.orthogonality == 0.0
    assert report.max_pair_overlap == 1.0


def test_partially_overlapping_parents() -> None:
    # A={alpha,beta,gamma}, B={alpha,beta,delta}. overlap=2/4=0.5.
    report = measure_merge_contribution_orthogonality(
        ["alpha beta gamma", "alpha beta delta"]
    )
    assert report.verdict == "partially_overlapping"
    assert report.mean_overlap == pytest.approx(0.5)
    assert report.orthogonality == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Three parents — mean over pairs.
# ---------------------------------------------------------------------------

def test_three_parents_mixed_is_orthogonal() -> None:
    # A={alpha,beta}, B={alpha,gamma}, C={delta,epsilon}.
    # (A,B)=1/3=0.333, (A,C)=0/4=0, (B,C)=0/4=0. mean=(0.333+0+0)/3=0.111.
    report = measure_merge_contribution_orthogonality(
        ["alpha beta", "alpha gamma", "delta epsilon"]
    )
    assert report.verdict == "highly_orthogonal"
    assert report.pair_count == 3
    assert report.measurable_pair_count == 3
    assert report.mean_overlap == pytest.approx((1.0 / 3.0 + 0.0 + 0.0) / 3.0)
    assert report.max_pair_overlap == pytest.approx(1.0 / 3.0)
    # pair_overlaps sorted desc by overlap.
    assert report.pair_overlaps[0].overlap == pytest.approx(1.0 / 3.0)
    assert report.pair_overlaps[1].overlap == 0.0


def test_three_identical_parents_highly_overlapping() -> None:
    report = measure_merge_contribution_orthogonality(
        ["alpha beta", "alpha beta", "alpha beta"]
    )
    assert report.verdict == "highly_overlapping"
    assert report.mean_overlap == 1.0
    assert report.measurable_pair_count == 3


# ---------------------------------------------------------------------------
# One-empty pair excluded from mean (NOT counted as 0).
# ---------------------------------------------------------------------------

def test_one_empty_parent_excluded_not_deflated() -> None:
    # A={alpha,beta}, B=empty, C={alpha,gamma}.
    # (A,B) unmeasurable (B empty), (A,C)=1/3=0.333, (B,C) unmeasurable.
    # measurable=1, mean=0.333. If the empty pair were counted as 0, mean would
    # be 0.111 (falsely deflated). This asserts exclusion.
    report = measure_merge_contribution_orthogonality(
        ["alpha beta", "", "alpha gamma"]
    )
    assert report.parent_count == 3
    assert report.pair_count == 3
    assert report.measurable_pair_count == 1
    assert report.mean_overlap == pytest.approx(1.0 / 3.0)
    assert report.verdict == "partially_overlapping"


# ---------------------------------------------------------------------------
# Distinct from exact-dedup: non-duplicate parents can still overlap.
# ---------------------------------------------------------------------------

def test_non_duplicate_parents_can_overlap() -> None:
    # These are NOT exact duplicates (dedup would say all_distinct) but share content.
    # A={alpha,beta,gamma}, B={alpha,beta,delta} -> overlap 0.5.
    report = measure_merge_contribution_orthogonality(
        ["alpha beta gamma", "alpha beta delta"]
    )
    assert report.mean_overlap == pytest.approx(0.5)
    assert report.verdict == "partially_overlapping"


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------

def test_thresholds_out_of_order_raise() -> None:
    with pytest.raises(ValueError):
        measure_merge_contribution_orthogonality(
            ["alpha beta", "gamma delta"],
            redundant_threshold=0.10,
            orthogonal_threshold=0.80,
        )


def test_threshold_above_one_raises() -> None:
    with pytest.raises(ValueError):
        measure_merge_contribution_orthogonality(
            ["alpha beta", "gamma delta"], redundant_threshold=1.5
        )


def test_custom_thresholds_flip_verdict() -> None:
    # mean 0.5: above orthogonal 0.20 and below redundant 0.60 (partial).
    # With redundant=0.40 -> highly_overlapping; with orthogonal=0.60 -> highly_orthogonal.
    parents = ["alpha beta gamma", "alpha beta delta"]
    assert (
        measure_merge_contribution_orthogonality(parents).verdict
        == "partially_overlapping"
    )
    assert (
        measure_merge_contribution_orthogonality(
            parents, redundant_threshold=0.40, orthogonal_threshold=0.10
        ).verdict
        == "highly_overlapping"
    )


# ---------------------------------------------------------------------------
# Determinism + immutability.
# ---------------------------------------------------------------------------

def test_deterministic_across_input_order() -> None:
    parents = ["alpha beta", "alpha gamma", "delta epsilon"]
    first = measure_merge_contribution_orthogonality(parents)
    second = measure_merge_contribution_orthogonality(list(reversed(parents)))
    # mean_overlap is order-independent; pair_overlaps labels differ by index but
    # the aggregate metrics are stable.
    assert first.mean_overlap == second.mean_overlap
    assert first.orthogonality == second.orthogonality
    assert first.measurable_pair_count == second.measurable_pair_count


def test_report_is_frozen() -> None:
    report = measure_merge_contribution_orthogonality(["alpha beta", "gamma delta"])
    with pytest.raises(FrozenInstanceError):
        report.mean_overlap = 0.5  # type: ignore[misc]


def test_authority_is_advisory() -> None:
    report = measure_merge_contribution_orthogonality(["alpha beta", "gamma delta"])
    assert report.authority == "advisory"


def test_mean_overlap_none_only_for_defer_states() -> None:
    assert measure_merge_contribution_orthogonality([]).mean_overlap is None
    assert measure_merge_contribution_orthogonality(["alpha"]).mean_overlap is None
    assert (
        measure_merge_contribution_orthogonality(["the and", "is a"]).mean_overlap
        is None
    )
    # Two content parents: measured, never None.
    assert (
        measure_merge_contribution_orthogonality(["alpha beta", "gamma delta"]).mean_overlap
        == 0.0
    )

"""Tests for the merge input-deduplication axis (ask #3)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.merge_input_dedup import (
    DuplicateGroup,
    MergeInputDedupReport,
    measure_merge_input_dedup,
)


def test_empty_inputs_is_unknown() -> None:
    report = measure_merge_input_dedup([])
    assert report.input_count == 0
    assert report.verdict == "unknown"
    assert report.unique_count is None
    assert report.duplicate_count is None
    assert report.dedup_ratio is None
    assert report.duplicate_group_count is None
    assert report.largest_duplicate_group is None
    assert report.duplicate_groups == ()
    assert report.authority == "advisory"


def test_single_input_is_base_case() -> None:
    report = measure_merge_input_dedup(["only one parent"])
    assert report.verdict == "single_input"
    assert report.input_count == 1
    assert report.unique_count == 1
    assert report.duplicate_count == 0
    assert report.dedup_ratio == 0.0
    assert report.duplicate_group_count == 0
    assert report.largest_duplicate_group is None
    assert report.duplicate_groups == ()


def test_two_distinct_inputs_all_distinct() -> None:
    report = measure_merge_input_dedup(["alpha document", "beta document"])
    assert report.verdict == "all_distinct"
    assert report.input_count == 2
    assert report.unique_count == 2
    assert report.duplicate_count == 0
    assert report.dedup_ratio == 0.0
    assert report.duplicate_group_count == 0
    assert report.largest_duplicate_group is None


def test_two_identical_inputs_majority_redundant() -> None:
    # 2 inputs, 1 unique, 1 duplicate -> ratio 1/2 = 0.5 == majority_threshold
    report = measure_merge_input_dedup(["same body", "same body"])
    assert report.verdict == "majority_redundant"
    assert report.unique_count == 1
    assert report.duplicate_count == 1
    assert report.dedup_ratio == 0.5
    assert report.duplicate_group_count == 1
    assert report.largest_duplicate_group == 2
    assert tuple(g.count for g in report.duplicate_groups) == (2,)


def test_partial_redundancy_one_pair_among_four() -> None:
    # ["a","a","b","c"] -> input 4, unique 3, dup 1 -> ratio 1/4 = 0.25 (partial at default 0.5)
    report = measure_merge_input_dedup(["a", "a", "b", "c"])
    assert report.verdict == "partial_redundant"
    assert report.input_count == 4
    assert report.unique_count == 3
    assert report.duplicate_count == 1
    assert report.dedup_ratio == 0.25
    assert report.duplicate_group_count == 1
    assert report.largest_duplicate_group == 2


def test_majority_redundancy_three_of_five_copies() -> None:
    # ["a","a","a","a","b"] -> input 5, unique 2, dup 3 -> ratio 3/5 = 0.6 (majority)
    report = measure_merge_input_dedup(["a", "a", "a", "a", "b"])
    assert report.verdict == "majority_redundant"
    assert report.input_count == 5
    assert report.unique_count == 2
    assert report.duplicate_count == 3
    assert report.dedup_ratio == 0.6
    assert report.largest_duplicate_group == 4
    assert tuple(g.count for g in report.duplicate_groups) == (4,)


def test_all_identical_inputs() -> None:
    # ["x","x","x"] -> input 3, unique 1, dup 2 -> ratio 2/3 ~= 0.6667 (majority)
    report = measure_merge_input_dedup(["x", "x", "x"])
    assert report.verdict == "majority_redundant"
    assert report.unique_count == 1
    assert report.duplicate_count == 2
    assert report.dedup_ratio == pytest.approx(2 / 3)
    assert report.largest_duplicate_group == 3


def test_multiple_duplicate_groups_sorted_desc_by_count() -> None:
    # ["a","a","a","b","b","c"] -> a:3, b:2, c:1 -> groups [3,2] desc; input 6 unique 3 dup 3 ratio 0.5
    report = measure_merge_input_dedup(["a", "a", "a", "b", "b", "c"])
    assert report.duplicate_group_count == 2
    assert tuple(g.count for g in report.duplicate_groups) == (3, 2)
    assert report.largest_duplicate_group == 3
    assert report.unique_count == 3
    assert report.dedup_ratio == 0.5
    assert report.verdict == "majority_redundant"


def test_whitespace_normalization_outer_and_line_endings_collapse() -> None:
    # "text", "text\r\n", "  text  " all normalize to "text" -> 3 copies
    report = measure_merge_input_dedup(["text", "text\r\n", "  text  "])
    assert report.input_count == 3
    assert report.unique_count == 1
    assert report.duplicate_count == 2
    assert report.dedup_ratio == pytest.approx(2 / 3)
    assert report.largest_duplicate_group == 3


def test_internal_whitespace_not_collapsed_lexical_floor() -> None:
    # "a b" vs "a  b" (double internal space) -> NOT normalized -> distinct (lexical floor)
    report = measure_merge_input_dedup(["a b", "a  b"])
    assert report.verdict == "all_distinct"
    assert report.unique_count == 2
    assert report.dedup_ratio == 0.0
    assert report.duplicate_groups == ()


def test_duplicate_group_hash_keys_are_twelve_hex_auditable() -> None:
    report = measure_merge_input_dedup(["dup", "dup"])
    assert len(report.duplicate_groups) == 1
    group: DuplicateGroup = report.duplicate_groups[0]
    assert len(group.hash_key) == 12
    assert all(c in "0123456789abcdef" for c in group.hash_key)
    assert group.count == 2


def test_custom_threshold_changes_verdict_boundary() -> None:
    # ratio 0.25: partial at 0.5, majority at 0.2, partial at 1.0
    inputs = ["a", "a", "b", "c"]
    assert measure_merge_input_dedup(inputs, majority_threshold=0.5).verdict == "partial_redundant"
    assert measure_merge_input_dedup(inputs, majority_threshold=0.2).verdict == "majority_redundant"
    assert measure_merge_input_dedup(inputs, majority_threshold=1.0).verdict == "partial_redundant"


def test_all_distinct_independent_of_threshold() -> None:
    inputs = ["x", "y", "z"]
    for threshold in (0.0, 0.5, 1.0):
        assert measure_merge_input_dedup(inputs, majority_threshold=threshold).verdict == "all_distinct"


def test_threshold_validation_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="majority_threshold"):
        measure_merge_input_dedup(["a"], majority_threshold=-0.01)
    with pytest.raises(ValueError, match="majority_threshold"):
        measure_merge_input_dedup(["a"], majority_threshold=1.01)


def test_report_is_frozen_and_deterministic() -> None:
    inputs = ["a", "a", "b", "b", "c"]
    first = measure_merge_input_dedup(inputs)
    second = measure_merge_input_dedup(inputs)
    assert first == second  # deterministic + value-equal (frozen dataclass)
    with pytest.raises(FrozenInstanceError):
        # frozen dataclass: attribute assignment must fail
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: MergeInputDedupReport = measure_merge_input_dedup(["a", "a", "b"])
    assert isinstance(report, MergeInputDedupReport)
    assert isinstance(report.duplicate_groups, tuple)
    assert all(isinstance(g, DuplicateGroup) for g in report.duplicate_groups)
    assert isinstance(report.notes, tuple)
    assert report.authority == "advisory"
    assert report.majority_threshold == 0.50

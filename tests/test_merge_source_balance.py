"""Tests for the merge source-balance axis (ask #3 — collective-merge accountability)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.merge_source_balance import (
    ParentContribution,
    measure_merge_source_balance,
)


def test_balanced_two_way_even_split() -> None:
    report = measure_merge_source_balance(["A", "B", "A", "B"])
    assert report.attributed_count == 4
    assert report.unattributed_count == 0
    assert report.contributing_parent_count == 2
    assert report.silenced_parent_count is None
    assert report.max_share == pytest.approx(0.5)
    assert report.balance_entropy == pytest.approx(1.0)
    assert report.verdict == "balanced"
    assert report.authority == "advisory"
    assert len(report.per_parent) == 2
    assert report.per_parent[0] == ParentContribution("A", 2, 0.5)
    assert report.per_parent[1] == ParentContribution("B", 2, 0.5)


def test_dominated_one_parent_holds_majority() -> None:
    ids = ["A"] * 7 + ["B"] * 2 + ["C"] * 1
    report = measure_merge_source_balance(ids)
    assert report.contributing_parent_count == 3
    assert report.max_share == pytest.approx(0.7)
    assert report.dominant_parent == "A"
    assert report.balance_entropy == pytest.approx(0.7300, abs=1e-3)
    assert report.verdict == "dominated"
    assert [pc.parent_id for pc in report.per_parent] == ["A", "B", "C"]
    assert report.per_parent[0].share == pytest.approx(0.7)


def test_single_source_one_parent_voice() -> None:
    report = measure_merge_source_balance(["A", "A", "A"])
    assert report.contributing_parent_count == 1
    assert report.max_share == pytest.approx(1.0)
    assert report.balance_entropy == pytest.approx(0.0)
    assert report.verdict == "single_source"
    assert "one parent voice — the merge is single-sourced" in report.notes


def test_unknown_empty_inputs() -> None:
    report = measure_merge_source_balance([])
    assert report.attributed_count == 0
    assert report.unattributed_count == 0
    assert report.contributing_parent_count is None
    assert report.silenced_parent_count is None
    assert report.max_share is None
    assert report.balance_entropy is None
    assert report.dominant_parent is None
    assert report.per_parent == ()
    assert report.verdict == "unknown"
    assert report.notes == ()


def test_unknown_all_unattributed_carries_count() -> None:
    report = measure_merge_source_balance(["", "  ", ""])
    assert report.attributed_count == 0
    assert report.unattributed_count == 3
    assert report.verdict == "unknown"
    assert len(report.notes) == 1
    assert "all 3 output units were unattributed" in report.notes[0]


def test_skewed_between_dominated_and_balanced() -> None:
    # 55/35/10 over 20 units: max_share 0.55 (< 0.60), entropy ~0.843 (< 0.90).
    ids = ["A"] * 11 + ["B"] * 7 + ["C"] * 2
    report = measure_merge_source_balance(ids)
    assert report.max_share == pytest.approx(0.55)
    assert report.balance_entropy == pytest.approx(0.8433, abs=1e-3)
    assert report.verdict == "skewed"
    assert report.contributing_parent_count == 3


def test_silenced_parents_detected() -> None:
    report = measure_merge_source_balance(["A", "B"], total_parents=5)
    assert report.contributing_parent_count == 2
    assert report.silenced_parent_count == 3
    assert "3 of 5 parents contributed nothing to the output" in report.notes
    # Still balanced between the two that DID contribute.
    assert report.verdict == "balanced"


def test_silenced_zero_when_all_parents_contribute() -> None:
    report = measure_merge_source_balance(["A", "B"], total_parents=2)
    assert report.silenced_parent_count == 0


def test_silenced_none_when_total_parents_unknown() -> None:
    report = measure_merge_source_balance(["A", "B", "C"])
    assert report.silenced_parent_count is None


def test_total_parents_smaller_than_distinct_raises() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        measure_merge_source_balance(["A", "B"], total_parents=1)


def test_unattributed_count_excluded_from_denominator() -> None:
    # 2 attributed to A, 1 attributed to B, 2 unattributed -> denominator is 3, not 5.
    report = measure_merge_source_balance(["A", "A", "B", "", ""])
    assert report.attributed_count == 3
    assert report.unattributed_count == 2
    assert report.max_share == pytest.approx(2 / 3)
    assert report.per_parent[0].parent_id == "A"


def test_tie_break_by_parent_id_ascending() -> None:
    # B and C each contribute 1 — deterministic tie-break by id ascending.
    report = measure_merge_source_balance(["C", "B"])
    assert [pc.parent_id for pc in report.per_parent] == ["B", "C"]


def test_custom_dominance_threshold_flips_verdict() -> None:
    # 50/30/20: max_share 0.50 — balanced at default, dominated at threshold 0.45.
    ids = ["A"] * 5 + ["B"] * 3 + ["C"] * 2
    assert measure_merge_source_balance(ids).verdict == "balanced"
    lowered = measure_merge_source_balance(ids, dominance_threshold=0.45)
    assert lowered.verdict == "dominated"


def test_custom_balance_entropy_threshold_flips_verdict() -> None:
    # 50/30/20 entropy ~0.937 — balanced at default 0.90, skewed at 0.95.
    ids = ["A"] * 5 + ["B"] * 3 + ["C"] * 2
    raised = measure_merge_source_balance(ids, balance_entropy_threshold=0.95)
    assert raised.verdict == "skewed"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"dominance_threshold": 1.5}, "dominance_threshold"),
        ({"dominance_threshold": -0.1}, "dominance_threshold"),
        ({"balance_entropy_threshold": 1.1}, "balance_entropy_threshold"),
        ({"total_parents": -1}, "total_parents"),
    ],
)
def test_threshold_validation_raises(kwargs: dict[str, float | int | None], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        measure_merge_source_balance(["A"], **kwargs)  # type: ignore[arg-type]


def test_report_is_deterministic() -> None:
    a = measure_merge_source_balance(["B", "A", "C", "A", "B", "C"])
    b = measure_merge_source_balance(["B", "A", "C", "A", "B", "C"])
    assert a == b


def test_report_is_frozen() -> None:
    report = measure_merge_source_balance(["A"])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "balanced"  # type: ignore[misc]


def test_per_parent_shares_sum_to_one() -> None:
    ids = ["A"] * 7 + ["B"] * 2 + ["C"] * 1
    report = measure_merge_source_balance(ids)
    assert sum(pc.share for pc in report.per_parent) == pytest.approx(1.0)

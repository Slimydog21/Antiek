"""Tests for the book-acquisition budget planner (pre-purchase affordability gate).

Exercises: all five verdict states (no_candidates/all_free/batch_affordable/
partial_affordable/none_affordable), greedy DRM-free-first ordering, free-book
always-affordable, over-spend handling, auditable deferred reasons, projected-
remaining math, validation, purity/immutability/determinism. Fixtures use small
cent-denominated prices so arithmetic is exact.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.book_acquisition_budget import (
    BookAcquisitionBudgetError,
    CandidateAcquisition,
    plan_book_acquisition_budget,
)


def _cand(
    book_id: str, price: int, *, drm_free: bool = True, priority: int = 1
) -> CandidateAcquisition:
    return CandidateAcquisition(
        book_id=book_id, price_usd_cents=price, drm_free=drm_free, priority=priority
    )


# --- core: batch_affordable ------------------------------------------------


def test_batch_affordable_full_batch_fits() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 200), _cand("B", 300)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=400,
    )
    assert report.remaining_budget == 600
    assert report.batch_total == 500
    assert not report.would_exceed_budget
    assert report.affordable_count == 2
    assert report.deferred_count == 0
    assert report.projected_remaining_after_affordable == 100  # 600 - 500
    assert report.verdict == "batch_affordable"


def test_batch_affordable_exact_fit() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 500)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=500,
    )
    assert report.remaining_budget == 500
    assert not report.would_exceed_budget  # 500 <= 500
    assert report.verdict == "batch_affordable"
    assert report.projected_remaining_after_affordable == 0


# --- core: all_free -------------------------------------------------------


def test_all_free_consumes_no_budget() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 0), _cand("B", 0)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=400,
    )
    assert report.batch_total == 0
    assert not report.would_exceed_budget
    assert report.affordable_count == 2
    assert report.projected_remaining_after_affordable == 600  # unchanged
    assert report.verdict == "all_free"


def test_all_free_even_with_zero_budget() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 0)],
        budget_limit_usd_cents=0,
        current_period_spend_usd_cents=0,
    )
    assert report.verdict == "all_free"
    assert report.affordable_count == 1


# --- core: partial_affordable (greedy selection) --------------------------


def test_partial_greedy_selects_what_fits() -> None:
    # remaining = 1000 - 0 = 1000. Batch [A:600, B:600] total 1200 > 1000.
    # Greedy picks A (600), remaining drops to 400; B (600 > 400) deferred.
    report = plan_book_acquisition_budget(
        [_cand("A", 600), _cand("B", 600)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=0,
    )
    assert report.would_exceed_budget
    assert report.affordable_count == 1
    assert report.deferred_count == 1
    assert report.verdict == "partial_affordable"
    assert report.affordable_books[0].book_id == "A"
    assert report.deferred_books[0].book_id == "B"
    assert report.deferred_books[0].reason == "exceeds_remaining"
    assert report.projected_remaining_after_affordable == 400  # 1000 - 600


def test_greedy_drm_free_preferred_over_drm_locked() -> None:
    # Two books same price 600, same priority; remaining 600 (fits only ONE).
    # DRM-free (A) must be picked over DRM-locked (B) per spec invariant #3.
    report = plan_book_acquisition_budget(
        [_cand("A", 600, drm_free=True), _cand("B", 600, drm_free=False)],
        budget_limit_usd_cents=600,
        current_period_spend_usd_cents=0,
    )
    assert report.affordable_count == 1
    assert report.affordable_books[0].book_id == "A"
    assert report.affordable_books[0].drm_free
    assert report.deferred_books[0].book_id == "B"
    assert report.verdict == "partial_affordable"


def test_greedy_higher_priority_preferred() -> None:
    # Both DRM-free, same price 400, remaining 400 (fits ONE).
    # B (priority 5) must beat A (priority 1).
    report = plan_book_acquisition_budget(
        [_cand("A", 400, priority=1), _cand("B", 400, priority=5)],
        budget_limit_usd_cents=400,
        current_period_spend_usd_cents=0,
    )
    assert report.affordable_books[0].book_id == "B"


def test_greedy_cheaper_preferred_at_equal_priority_drm() -> None:
    # Both DRM-free, same priority, remaining 300. A=200, B=300.
    # Greedy picks cheaper A first (200), remaining 100; B (300 > 100) deferred.
    report = plan_book_acquisition_budget(
        [_cand("A", 200, priority=1), _cand("B", 300, priority=1)],
        budget_limit_usd_cents=300,
        current_period_spend_usd_cents=0,
    )
    affordable_ids = [b.book_id for b in report.affordable_books]
    assert "A" in affordable_ids
    assert report.affordable_count == 1


def test_greedy_packs_multiple_within_budget() -> None:
    # remaining 500. Books: A=200, B=200, C=200 (all DRM-free, priority 1).
    # Greedy: A (200, rem 300), B (200, rem 100), C (200 > 100) deferred.
    report = plan_book_acquisition_budget(
        [_cand("A", 200), _cand("B", 200), _cand("C", 200)],
        budget_limit_usd_cents=500,
        current_period_spend_usd_cents=0,
    )
    assert report.affordable_count == 2
    assert report.deferred_count == 1
    assert report.projected_remaining_after_affordable == 100


# --- core: none_affordable ------------------------------------------------


def test_none_affordable_zero_remaining() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 500), _cand("B", 300)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=1000,
    )
    assert report.remaining_budget == 0
    assert report.affordable_count == 0
    assert report.deferred_count == 2
    assert report.would_exceed_budget
    assert report.cheapest_affordable_price is None
    assert report.priciest_affordable_price is None
    assert report.verdict == "none_affordable"


def test_none_affordable_over_spent() -> None:
    # over-spent: remaining negative -> only free clears; paid books deferred
    report = plan_book_acquisition_budget(
        [_cand("A", 500)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=1200,
    )
    assert report.remaining_budget == -200
    assert report.affordable_count == 0
    assert report.verdict == "none_affordable"


def test_over_spent_free_book_still_affordable() -> None:
    report = plan_book_acquisition_budget(
        [_cand("Free", 0), _cand("Paid", 500)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=1200,
    )
    assert report.remaining_budget == -200
    assert report.affordable_count == 1
    assert report.affordable_books[0].book_id == "Free"
    assert report.deferred_books[0].book_id == "Paid"
    assert report.verdict == "partial_affordable"


# --- honesty: no_candidates ----------------------------------------------


def test_no_candidates_trivial() -> None:
    report = plan_book_acquisition_budget(
        [],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=400,
    )
    assert report.verdict == "no_candidates"
    assert report.batch_total == 0
    assert not report.would_exceed_budget
    assert report.affordable_count == 0
    assert report.projected_remaining_after_affordable == 600  # unchanged


# --- would_exceed_budget + projected math ---------------------------------


def test_would_exceed_true_when_batch_exceeds() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 9999)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=0,
    )
    assert report.would_exceed_budget
    assert report.verdict == "none_affordable"


def test_projected_remaining_after_full_acquisition() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 250), _cand("B", 250)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=0,
    )
    assert report.projected_remaining_after_affordable == 500


def test_cheapest_priciest_affordable_range() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 100), _cand("B", 300), _cand("C", 200)],
        budget_limit_usd_cents=1000,
        current_period_spend_usd_cents=0,
    )
    assert report.cheapest_affordable_price == 100
    assert report.priciest_affordable_price == 300


# --- validation -----------------------------------------------------------


def test_negative_budget_limit_rejected() -> None:
    with pytest.raises(BookAcquisitionBudgetError):
        plan_book_acquisition_budget(
            [_cand("A", 100)], budget_limit_usd_cents=-1, current_period_spend_usd_cents=0
        )


def test_negative_spend_rejected() -> None:
    with pytest.raises(BookAcquisitionBudgetError):
        plan_book_acquisition_budget(
            [_cand("A", 100)], budget_limit_usd_cents=1000, current_period_spend_usd_cents=-1
        )


def test_negative_price_rejected() -> None:
    with pytest.raises(BookAcquisitionBudgetError):
        plan_book_acquisition_budget(
            [_cand("A", -1)], budget_limit_usd_cents=1000, current_period_spend_usd_cents=0
        )


def test_empty_book_id_rejected() -> None:
    with pytest.raises(BookAcquisitionBudgetError):
        plan_book_acquisition_budget(
            [_cand("  ", 100)],
            budget_limit_usd_cents=1000,
            current_period_spend_usd_cents=0,
        )


# --- purity / immutability / determinism ----------------------------------


def test_report_is_frozen() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 100)], budget_limit_usd_cents=1000, current_period_spend_usd_cents=0
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.affordable_count = 99  # type: ignore[misc]


def test_deterministic_repeated_calls() -> None:
    cands = [_cand("A", 600, drm_free=True), _cand("B", 600, drm_free=False)]
    first = plan_book_acquisition_budget(
        cands, budget_limit_usd_cents=600, current_period_spend_usd_cents=0
    )
    second = plan_book_acquisition_budget(
        cands, budget_limit_usd_cents=600, current_period_spend_usd_cents=0
    )
    assert first == second


def test_authority_is_advisory() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 100)], budget_limit_usd_cents=1000, current_period_spend_usd_cents=0
    )
    assert report.authority == "advisory"


def test_partition_invariant_affordable_plus_deferred() -> None:
    report = plan_book_acquisition_budget(
        [_cand("A", 600), _cand("B", 400), _cand("C", 200)],
        budget_limit_usd_cents=500,
        current_period_spend_usd_cents=0,
    )
    assert report.affordable_count + report.deferred_count == 3


def test_all_free_distinct_from_batch_affordable() -> None:
    """Binding honesty: all_free (zero spend) never collapses with batch_affordable (real spend that fits)."""
    free = plan_book_acquisition_budget(
        [_cand("A", 0)], budget_limit_usd_cents=1000, current_period_spend_usd_cents=0
    )
    paid = plan_book_acquisition_budget(
        [_cand("A", 500)], budget_limit_usd_cents=1000, current_period_spend_usd_cents=0
    )
    assert free.verdict == "all_free"
    assert free.batch_total == 0
    assert paid.verdict == "batch_affordable"
    assert paid.batch_total == 500

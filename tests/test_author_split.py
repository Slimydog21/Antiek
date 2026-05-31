"""SPR-06 M3 — the versioned multi-author split policy.

Proves: equal_split sums to exactly 100% of the cents via the largest-remainder
primitive (incl. a 3-author and a 7-author case so the remainder distribution is
actually exercised); the policy is version-stamped; n<=0 is the empty (→
unattributed) case.
"""

from __future__ import annotations

import pytest

from substrate.ad_inventory.frame_attention import apportion_cents
from substrate.payouts.split import SPLIT_POLICY_VERSION, equal_split


def test_policy_is_version_stamped():
    assert isinstance(SPLIT_POLICY_VERSION, str) and SPLIT_POLICY_VERSION


def test_equal_split_weights_sum_to_one():
    for n in (1, 2, 3, 5, 7, 13, 200):
        weights = equal_split(n)
        assert len(weights) == n
        assert weights.keys() == {str(i) for i in range(n)}
        assert sum(weights.values()) == pytest.approx(1.0)


def test_equal_split_zero_or_negative_is_empty():
    # The ledger reads an empty split as "no attributable author" → unattributed,
    # rather than dividing by zero.
    assert equal_split(0) == {}
    assert equal_split(-3) == {}


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 11])
@pytest.mark.parametrize("total_cents", [0, 1, 7, 100, 101, 999, 1000, 12345])
def test_equal_split_apportions_to_exactly_total_cents(n, total_cents):
    """The conservation property at the money layer: an equal split, apportioned
    by the largest-remainder primitive, sums back to EXACTLY total_cents — no
    lost or invented cent — for every (author count, total) pair, including
    indivisible totals (e.g. 100 / 3, 101 / 7)."""
    weights = equal_split(n)
    split = apportion_cents(weights, total_cents)
    assert sum(split.values()) == total_cents
    # Every author gets a non-negative integer share.
    assert all(isinstance(c, int) and c >= 0 for c in split.values())


def test_three_author_indivisible_total_distributes_remainder():
    """100 cents / 3 authors = 34, 33, 33 (or a permutation) — the leftover cent
    is handed to exactly one author, never dropped, never duplicated."""
    split = apportion_cents(equal_split(3), 100)
    assert sum(split.values()) == 100
    assert sorted(split.values()) == [33, 33, 34]


def test_seven_author_indivisible_total_distributes_remainder():
    """101 cents / 7 authors: floor is 14 each (98), 3 leftover cents go to 3
    distinct authors → 15, 15, 15, 14, 14, 14, 14. Sums to 101 exactly."""
    split = apportion_cents(equal_split(7), 101)
    assert sum(split.values()) == 101
    assert sorted(split.values()) == [14, 14, 14, 14, 15, 15, 15]

"""REAL behavior test (positive control). Asserts the unit's OUTPUT — the actual
returned price for a member and a non-member. Inverting the members-only guard
in product.discount_price changes both prices, so this test MUST fail on the
mutation. The detector should report ``killed``."""

from __future__ import annotations

from product import discount_price


def test_member_gets_discount():
    assert discount_price(100.0, is_member=True) == 80.0


def test_non_member_pays_full():
    assert discount_price(100.0, is_member=False) == 100.0

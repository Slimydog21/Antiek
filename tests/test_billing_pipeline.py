"""Token-usage billing pipeline tests (master-spec §13.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from substrate.billing import (
    BillingAggregate,
    aggregate_period,
    enforce_free_tier_cap,
    project_tier_for_request,
    record_dispatch_for_billing,
)
from tools.stripe_connect.pricing import (
    FREE_TIER_MONTHLY_TOKEN_CAP,
    PricingTier,
)


def test_record_dispatch_applies_correct_margin():
    agg = BillingAggregate()
    record = record_dispatch_for_billing(
        agg,
        user_id="user-1",
        tier=PricingTier.PAID_PRIVATE,
        raw_token_cost_usd=Decimal("2.00"),
        token_count=10000,
    )
    assert record.margin_usd == Decimal("1.00")  # 50%
    assert record.billable_to_user_usd == Decimal("3.00")
    assert len(agg.records) == 1


def test_record_dispatch_public_10_percent_margin():
    agg = BillingAggregate()
    record = record_dispatch_for_billing(
        agg,
        user_id="user-1",
        tier=PricingTier.PAID_PUBLIC,
        raw_token_cost_usd=Decimal("1.00"),
        token_count=5000,
    )
    assert record.margin_usd == Decimal("0.10")
    assert record.billable_to_user_usd == Decimal("1.10")


def test_aggregate_period_sums_correctly():
    agg = BillingAggregate()
    for _ in range(3):
        record_dispatch_for_billing(
            agg, user_id="user-1", tier=PricingTier.PAID_PRIVATE,
            raw_token_cost_usd=Decimal("1.00"), token_count=1000,
        )
    record_dispatch_for_billing(
        agg, user_id="user-1", tier=PricingTier.PAID_PUBLIC,
        raw_token_cost_usd=Decimal("0.50"), token_count=500,
    )
    # All records this month.
    from datetime import datetime, timezone
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    summary = aggregate_period(agg, user_id="user-1", period=this_month)
    assert summary.record_count == 4
    assert summary.paid_private_token_cost_usd == Decimal("3.00")
    assert summary.paid_public_token_cost_usd == Decimal("0.50")
    assert summary.total_raw_usd == Decimal("3.50")
    # private margin = 3.00 * 0.50 = 1.50; public margin = 0.50 * 0.10 = 0.05
    assert summary.total_margin_usd == Decimal("1.55")


def test_free_tier_cap_under_limit_stays_free():
    verdict = project_tier_for_request(
        user_id="user-1",
        requested_tier=PricingTier.FREE_PUBLIC,
        free_tokens_consumed_this_period=1_000_000,
        projected_token_count=100_000,
    )
    assert verdict.effective_tier == PricingTier.FREE_PUBLIC
    assert verdict.cap_just_crossed is False


def test_free_tier_cap_crossed_converts_to_paid_public():
    """Per master-spec §13.5: at the cap, automatic conversion to
    paid public at 10% margin — NOT a friction wall."""
    verdict = project_tier_for_request(
        user_id="user-1",
        requested_tier=PricingTier.FREE_PUBLIC,
        free_tokens_consumed_this_period=FREE_TIER_MONTHLY_TOKEN_CAP - 100,
        projected_token_count=200,  # would exceed
    )
    assert verdict.effective_tier == PricingTier.PAID_PUBLIC
    assert verdict.cap_just_crossed is True
    assert verdict.free_tokens_remaining == 0


def test_paid_private_never_uses_free_cap():
    """PAID_PRIVATE requests never consume free-tier allowance."""
    verdict = enforce_free_tier_cap(
        user_id="user-1",
        requested_tier=PricingTier.PAID_PRIVATE,
        free_tokens_consumed_this_period=0,
        projected_token_count=100,
    )
    assert verdict.effective_tier == PricingTier.PAID_PRIVATE
    assert verdict.cap_just_crossed is False


def test_free_tokens_remaining_accurate():
    consumed = 1_500_000
    verdict = project_tier_for_request(
        user_id="user-1",
        requested_tier=PricingTier.FREE_PUBLIC,
        free_tokens_consumed_this_period=consumed,
        projected_token_count=100,
    )
    assert verdict.free_tokens_remaining == FREE_TIER_MONTHLY_TOKEN_CAP - consumed

"""User-level token-usage aggregation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from tools.stripe_connect.pricing import (
    MARGIN_RATES,
    PricingTier,
    apply_margin,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _billing_period_for(iso_ts: str) -> str:
    """YYYY-MM from an ISO 8601 timestamp."""
    return iso_ts[:7]


@dataclass(frozen=True)
class UsageRecord:
    """One billable token-usage event. Aggregated for monthly billing."""

    record_id: str
    user_id: str
    investigation_id: Optional[str]
    notebook_id: Optional[str]
    tier: PricingTier
    raw_token_cost_usd: Decimal
    margin_usd: Decimal
    billable_to_user_usd: Decimal
    token_count: int
    recorded_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class BillingPeriod:
    """One user-month billing aggregation."""

    user_id: str
    period: str  # YYYY-MM
    free_tokens_consumed: int
    paid_public_token_cost_usd: Decimal
    paid_public_margin_usd: Decimal
    paid_private_token_cost_usd: Decimal
    paid_private_margin_usd: Decimal
    total_raw_usd: Decimal
    total_margin_usd: Decimal
    total_billable_usd: Decimal
    record_count: int


@dataclass
class BillingAggregate:
    """Per-user aggregation state. Operator-side persistence lives in
    a billing table; this in-memory aggregate supports unit tests +
    on-the-fly user-month projection."""

    records: list[UsageRecord] = field(default_factory=list)

    def append(self, record: UsageRecord) -> None:
        self.records.append(record)


def record_dispatch_for_billing(
    aggregate: BillingAggregate,
    *,
    user_id: str,
    tier: PricingTier,
    raw_token_cost_usd: Decimal,
    token_count: int,
    investigation_id: Optional[str] = None,
    notebook_id: Optional[str] = None,
) -> UsageRecord:
    """Record one dispatch.call event for billing aggregation.

    The substrate's dispatch path emits dispatch.call events with
    `cost_usd` already populated. The billing pipeline subscribes to
    these events and calls this function with the user_id binding
    (which the dispatch event does NOT currently carry — Sprint 19
    follow-on wires the user binding through the dispatch context
    pack)."""
    margin = apply_margin(raw_token_cost_usd, tier)
    billable = raw_token_cost_usd + margin
    record = UsageRecord(
        record_id=f"usage-{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        investigation_id=investigation_id,
        notebook_id=notebook_id,
        tier=tier,
        raw_token_cost_usd=raw_token_cost_usd,
        margin_usd=margin,
        billable_to_user_usd=billable,
        token_count=token_count,
    )
    aggregate.append(record)
    return record


def aggregate_period(
    aggregate: BillingAggregate,
    *,
    user_id: str,
    period: str,
) -> BillingPeriod:
    """Aggregate the user's records for a billing period (YYYY-MM)."""
    matching = [
        r for r in aggregate.records
        if r.user_id == user_id and _billing_period_for(r.recorded_at) == period
    ]

    free_tokens = 0
    public_raw = Decimal("0.00")
    public_margin = Decimal("0.00")
    private_raw = Decimal("0.00")
    private_margin = Decimal("0.00")
    total_raw = Decimal("0.00")
    total_margin = Decimal("0.00")
    total_billable = Decimal("0.00")

    for r in matching:
        total_raw += r.raw_token_cost_usd
        total_margin += r.margin_usd
        total_billable += r.billable_to_user_usd
        if r.tier == PricingTier.FREE_PUBLIC:
            free_tokens += r.token_count
        elif r.tier == PricingTier.PAID_PUBLIC:
            public_raw += r.raw_token_cost_usd
            public_margin += r.margin_usd
        elif r.tier == PricingTier.PAID_PRIVATE:
            private_raw += r.raw_token_cost_usd
            private_margin += r.margin_usd

    return BillingPeriod(
        user_id=user_id,
        period=period,
        free_tokens_consumed=free_tokens,
        paid_public_token_cost_usd=public_raw,
        paid_public_margin_usd=public_margin,
        paid_private_token_cost_usd=private_raw,
        paid_private_margin_usd=private_margin,
        total_raw_usd=total_raw,
        total_margin_usd=total_margin,
        total_billable_usd=total_billable,
        record_count=len(matching),
    )

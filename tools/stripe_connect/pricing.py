"""Three-tier consumer pricing (master-spec §13.5).

Operator-decided pricing from voice notes 2026-05-17, verbatim:

  "I will charge people like OpenRouter by allowing people to set a
  budget for tokens used, and for private documents I will charge for
  token usage on such documents at a 50% margin. I guess I will
  charge users for public token consumption at a 10% margin, but will
  allow rev share of 70% to them on the ad placement; So this will
  incentivize people to consume to create IP on my platform."

Three tiers + developer surface, all pay-as-you-go on tokens:

1. **Free public tier** — DeepSeek-Flash inference up to 5M tokens/month.
   No per-token charge under the cap. Ads on. 70% of ad revenue routes
   to the contributing user (user-as-IP-holder, §13.9).

2. **Paid public consumption (above cap)** — 10% margin on raw token
   cost. Ads still on; creators still earn 70% rev-share on ad
   revenue from sessions consuming their content.

3. **Paid private use** — 50% managed-service margin on raw token cost.
   No ads. Content stays in the user's private partition. Surface E
   Brainstorming Workstation (§4.5) is where this happens most.

The OpenRouter analog the operator named is exact: users set a budget,
get billed for actual token consumption against that budget. NOT a
flat subscription.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PricingTier(str, Enum):
    """The four consumer billing buckets per master-spec §13.5."""

    FREE_PUBLIC = "free_public"
    PAID_PUBLIC = "paid_public"
    PAID_PRIVATE = "paid_private"
    DEVELOPER_API = "developer_api"


# Margin rates per master-spec §13.5 (operator-decided 2026-05-17).
# `private` carries the managed-service framing — "50% of inference
# cost in exchange for substrate value" (graph infra + attribution +
# voice/style + recursive note-taking + brainstorming workstation +
# two-graph privacy). Same number, different psychology.
MARGIN_RATES: dict[PricingTier, Decimal] = {
    PricingTier.FREE_PUBLIC: Decimal("0.00"),  # capped, no per-token charge
    PricingTier.PAID_PUBLIC: Decimal("0.10"),  # 10%
    PricingTier.PAID_PRIVATE: Decimal("0.50"),  # 50% managed-service
    PricingTier.DEVELOPER_API: Decimal("0.50"),  # mirror private for API queries
}


# Free-tier monthly token cap per master-spec §13.5 "the mechanism
# for resolving the public-tier unit-economics problem".
FREE_TIER_MONTHLY_TOKEN_CAP: int = 5_000_000

# Free-tier model — DeepSeek-Flash via OpenRouter per §13.5.
FREE_TIER_MODEL: str = "deepseek/deepseek-v4-flash"

# Creator ad rev-share per master-spec §13.5 verbatim.
CREATOR_AD_REV_SHARE: Decimal = Decimal("0.70")
PUBLISHER_AD_REV_SHARE: Decimal = Decimal("0.70")  # same architecture (§13.9)


@dataclass
class TokenUsageRecord:
    """A single billable token-usage event. Aggregated for the
    monthly billing cycle; settled via Stripe metered billing or the
    operator's chosen provider equivalent."""

    record_id: str
    user_id: str
    tier: PricingTier
    raw_token_cost_usd: Decimal  # what the underlying provider charged
    margin_usd: Decimal           # what Antiek adds on top
    billable_to_user_usd: Decimal  # raw + margin
    investigation_id: Optional[str]
    notebook_id: Optional[str]
    chunk_id: Optional[str]       # for attribution flow
    idempotency_key: str
    recorded_at: str = field(default_factory=_now_iso)


@dataclass
class BillingEvent:
    """Aggregate of billable usage for one user-month. The Stripe
    metered-billing record is emitted from a BillingEvent."""

    user_id: str
    billing_period: str  # YYYY-MM
    tier: PricingTier
    total_raw_token_cost_usd: Decimal
    total_margin_usd: Decimal
    total_billable_usd: Decimal
    record_count: int


def apply_margin(
    raw_token_cost_usd: Decimal,
    tier: PricingTier,
) -> Decimal:
    """Compute the Antiek margin for a raw provider cost at a given
    tier. Returns the margin amount in USD; the user-billable total
    is raw + margin.

    For FREE_PUBLIC under the monthly cap, returns 0 (no charge).
    Callers that have exceeded the cap should call with PAID_PUBLIC
    tier instead — this function does NOT track cap state."""
    rate = MARGIN_RATES[tier]
    return raw_token_cost_usd * rate


def record_token_usage(
    *,
    user_id: str,
    tier: PricingTier,
    raw_token_cost_usd: Decimal,
    investigation_id: Optional[str] = None,
    notebook_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
) -> TokenUsageRecord:
    """Record one token-usage event. Returns the TokenUsageRecord.

    Production callers wire this against an append-only event log;
    the substrate emits a dispatch.call event already, but billing
    requires the user-id binding which the dispatch event does not
    currently carry. The bind point lives at the dispatch.call →
    billing pipeline (Sprint 19 follow-on)."""
    margin = apply_margin(raw_token_cost_usd, tier)
    billable = raw_token_cost_usd + margin
    return TokenUsageRecord(
        record_id=f"usage-{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        tier=tier,
        raw_token_cost_usd=raw_token_cost_usd,
        margin_usd=margin,
        billable_to_user_usd=billable,
        investigation_id=investigation_id,
        notebook_id=notebook_id,
        chunk_id=chunk_id,
        idempotency_key=f"usage-{user_id}-{uuid.uuid4().hex[:8]}",
    )

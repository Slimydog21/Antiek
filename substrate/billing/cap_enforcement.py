"""Free-tier cap enforcement (master-spec §13.5)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from tools.stripe_connect.pricing import (
    FREE_TIER_MONTHLY_TOKEN_CAP,
    PricingTier,
)


@dataclass(frozen=True)
class CapEnforcementVerdict:
    """Decision on which tier a forthcoming dispatch should bill under.

    The free-tier cap converts free public consumption to paid public
    once the user crosses the monthly limit. The next call after the
    cap is reached automatically falls to PAID_PUBLIC; the user does
    NOT get a friction wall — the substrate keeps serving but starts
    charging."""

    effective_tier: PricingTier
    free_tokens_remaining: int
    cap_just_crossed: bool
    reason: str


def project_tier_for_request(
    *,
    user_id: str,
    requested_tier: PricingTier,
    free_tokens_consumed_this_period: int,
    projected_token_count: int,
) -> CapEnforcementVerdict:
    """Project which tier the dispatch should bill under given the
    user's current monthly free-tier consumption + the upcoming
    request's projected token count.

    Rules:
    - PAID_PRIVATE always bills as PAID_PRIVATE (no cap).
    - PAID_PUBLIC always bills as PAID_PUBLIC.
    - DEVELOPER_API always bills as DEVELOPER_API.
    - FREE_PUBLIC: if free_tokens_consumed + projected <= cap → FREE_PUBLIC;
      else PAID_PUBLIC (cap crossed; user converts to paid).
    """
    if requested_tier != PricingTier.FREE_PUBLIC:
        return CapEnforcementVerdict(
            effective_tier=requested_tier,
            free_tokens_remaining=max(
                0, FREE_TIER_MONTHLY_TOKEN_CAP - free_tokens_consumed_this_period,
            ),
            cap_just_crossed=False,
            reason=f"non-free-tier request: {requested_tier.value}",
        )

    remaining = max(
        0, FREE_TIER_MONTHLY_TOKEN_CAP - free_tokens_consumed_this_period,
    )
    if remaining >= projected_token_count:
        return CapEnforcementVerdict(
            effective_tier=PricingTier.FREE_PUBLIC,
            free_tokens_remaining=remaining,
            cap_just_crossed=False,
            reason=(
                f"under free cap: {projected_token_count} tokens "
                f"fits in {remaining} remaining"
            ),
        )

    # Free-tier cap would be crossed. Convert to PAID_PUBLIC.
    return CapEnforcementVerdict(
        effective_tier=PricingTier.PAID_PUBLIC,
        free_tokens_remaining=0,
        cap_just_crossed=True,
        reason=(
            f"free-tier cap crossed: {projected_token_count} tokens "
            f"would exceed {remaining} remaining; auto-converted to "
            f"paid_public (10% margin)"
        ),
    )


def enforce_free_tier_cap(
    *,
    user_id: str,
    requested_tier: PricingTier,
    free_tokens_consumed_this_period: int,
    projected_token_count: int,
) -> CapEnforcementVerdict:
    """Operator-decided pay-as-you-go cap-enforcement entry point.
    Same as project_tier_for_request; named for the caller's
    intent at the boundary."""
    return project_tier_for_request(
        user_id=user_id,
        requested_tier=requested_tier,
        free_tokens_consumed_this_period=free_tokens_consumed_this_period,
        projected_token_count=projected_token_count,
    )

"""Stripe Connect scaffold — Sprint 18 publisher payouts +
Sprint 19 three-tier consumer pricing (master-spec §9.5 + §13.5).

Per master-spec:
- Publisher escrow payouts route through Stripe Connect once the
  publisher transitions claimed (§9.10 + §9.5).
- Consumer pricing per §13.5: free public DeepSeek-Flash cap,
  paid public 10% margin, paid private 50% margin, developer
  surface usage-based. Pay-as-you-go on tokens with operator
  setting a budget OpenRouter-style — NOT a flat subscription.

This module is a SCAFFOLD. It does not call the Stripe SDK at runtime
because (a) the operator may want to swap providers (Lemon Squeezy
has different KYC properties); (b) the real Stripe Connect onboarding
needs the operator's lawyer involved per §15.9 binding gate. The
scaffold provides:

1. Type-safe wrappers for the operations Antiek's substrate needs to
   request from Stripe.
2. An idempotent operations log so the substrate can re-attempt money
   movement without double-charging.
3. A `MockStripeProvider` for tests; production wires
   `RealStripeProvider` via the `stripe` SDK once API keys land in
   the operator's env.
"""

from .accounts import (
    StripeAccountStatus,
    StripeConnectAccount,
    StripeOperationsLog,
    create_publisher_account,
    create_user_creator_account,
)
from .pricing import (
    BillingEvent,
    PricingTier,
    TokenUsageRecord,
    apply_margin,
    record_token_usage,
)
from .providers import MockStripeProvider, StripeProvider

__all__ = [
    "BillingEvent",
    "MockStripeProvider",
    "PricingTier",
    "StripeAccountStatus",
    "StripeConnectAccount",
    "StripeOperationsLog",
    "StripeProvider",
    "TokenUsageRecord",
    "apply_margin",
    "create_publisher_account",
    "create_user_creator_account",
    "record_token_usage",
]

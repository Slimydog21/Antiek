"""Token-usage telemetry pipeline (master-spec §13.5 + §13.8).

Binds `dispatch.call` events to user-level billing aggregation +
free-tier-cap enforcement. Per master-spec §13.5: operator-decided
pay-as-you-go pricing model — free public tier (DeepSeek-Flash up
to 5M tokens), paid public (10% margin), paid private (50% margin),
developer API (usage-based).

The pipeline:
1. Dispatch event fires with raw_token_cost_usd + user binding
2. Substrate aggregates per-user per-month + per-tier
3. Free-tier cap enforcement triggers automatic conversion to paid
   when the user crosses the cap
4. Monthly billing summary emits to Stripe Connect for collection
"""

from .aggregator import (
    BillingAggregate,
    BillingPeriod,
    UsageRecord,
    aggregate_period,
    record_dispatch_for_billing,
)
from .cap_enforcement import (
    CapEnforcementVerdict,
    enforce_free_tier_cap,
    project_tier_for_request,
)

__all__ = [
    "BillingAggregate",
    "BillingPeriod",
    "CapEnforcementVerdict",
    "UsageRecord",
    "aggregate_period",
    "enforce_free_tier_cap",
    "project_tier_for_request",
    "record_dispatch_for_billing",
]

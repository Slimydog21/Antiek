"""Revenue share — 30% platform / 70% IP-holder + mixed creator+publisher
proportional split + below-threshold rollover ledger.

Per master-spec §9.0.1 + §13.5 + §13.9 + §9.10 + §9.5:
- 30% platform / 70% IP-holders
- Of the 70%: creator 70% (user-as-IP-holder, §13.9), publisher
  70% on attribution-weighted basis if opted in (§9.10)
- Where a session pulls from BOTH a creator's public note and a
  publisher's licensed content, the proportional split avoids
  double-spend (Sprint 25+ mixed_attribution)
- §9.5 $10 minimum payout threshold; below-threshold rolls over with
  a 12-month ceiling, then forfeits with month-9 notice

This module is the substrate side; tools/stripe_connect/payouts.py
will route the actual money. Substrate-only; activation gated on
Sprint 23-24 anti-gaming pass.
"""

from .splits import (
    PLATFORM_CUT,
    IP_HOLDER_CUT,
    CREATOR_PAYOUT_RATIO,
    split_platform_vs_ip,
    apply_creator_ratio,
)
from .mixed_attribution import (
    MixedAttributionInput,
    MixedAttributionResult,
    split_mixed_attribution,
)
from .rollover import (
    MINIMUM_PAYOUT_USD_CENTS,
    ROLLOVER_CEILING_MONTHS,
    NOTICE_MONTH,
    RolloverLedger,
    RolloverEntry,
    accrue,
    settle_or_rollover,
    is_forfeitable,
)

__all__ = [
    "CREATOR_PAYOUT_RATIO",
    "IP_HOLDER_CUT",
    "MINIMUM_PAYOUT_USD_CENTS",
    "MixedAttributionInput",
    "MixedAttributionResult",
    "NOTICE_MONTH",
    "PLATFORM_CUT",
    "ROLLOVER_CEILING_MONTHS",
    "RolloverEntry",
    "RolloverLedger",
    "accrue",
    "apply_creator_ratio",
    "is_forfeitable",
    "settle_or_rollover",
    "split_mixed_attribution",
    "split_platform_vs_ip",
]

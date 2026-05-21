"""Ad inventory + attribution-flow-to-escrow (Sprint 23-24).

Per master-spec §9.4 ad inventory mechanism design:
- Phase 1: telemetry only (shipped Sprint 16)
- Phase 2: manual sponsor slot (Sprint 18-19, master §9.8)
- Phase 3: lead-gen / vertical ads (Sprint 23+, master §9.8 row 4)
- Phase 4: programmatic auction (Sprint 30+, only if scale warrants)

This module ships the substrate primitives:
- AttributionAlgorithm (A: equal split, B: confidence × tier, C:
  load-bearing) per §9.3
- Lead-gen ad inventory mechanism per §9.4 Option C
- Creator + publisher rev-share flow connecting attribution events
  to Stripe Connect transfers (master §13.9 + §9.10)
- Per-document payout-rate cap anti-gaming per §9.7
"""

from .ad_bidding import (
    AdImpression,
    AdInventoryItem,
    BiddingPolicy,
    LeadGenAdInventory,
    select_lead_gen_ad,
)
from .attribution import (
    AttributionAlgorithm,
    AttributionResult,
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
)
from .payout import (
    PayoutRouter,
    RevShareDecision,
    distribute_session_ad_revenue,
    enforce_per_document_daily_cap,
)

__all__ = [
    "AdImpression",
    "AdInventoryItem",
    "AttributionAlgorithm",
    "AttributionResult",
    "BiddingPolicy",
    "LeadGenAdInventory",
    "PayoutRouter",
    "RevShareDecision",
    "compute_attribution_option_a",
    "compute_attribution_option_b",
    "compute_attribution_option_c",
    "distribute_session_ad_revenue",
    "enforce_per_document_daily_cap",
    "select_lead_gen_ad",
]

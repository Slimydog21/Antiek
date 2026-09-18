"""Website Ads Rank 0 honesty envelope (no fake cents).

Single source of truth for the pre-revenue website monetization posture:

- Antiek-served creatives only (house → manual sponsor → lead-gen).
- No AppLovin MAX SDK on web (no web publisher SDK exists; doctrine REJECT).
- ``revenue_usd_cents`` stays 0 and ``price_status`` stays ``unpriced`` until
  Rank 0.1 pricing exists and Rank 0.2 legal gate has passed for the advertiser.
- Speak / contributor escrow is 70% of *settled* revenue only — never invented.

Cited by: docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md
Ranks: docs/specs/ad-v1-scalable-2026-08-12.md Rank 0–1.
"""

from __future__ import annotations

from typing import Any

DECISION_REF = (
    "docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md"
)
SPEC_REF = "docs/specs/ad-v1-scalable-2026-08-12.md"

# Platform / contributor split — master-spec §9.1. Applies only after
# settled pricing; never mint cents from this share alone.
SPEAK_CONTRIBUTOR_SHARE = 0.70
SPEAK_PLATFORM_SHARE = 0.30

FILL_LADDER: tuple[str, ...] = (
    "house",
    "manual_sponsor",
    "lead_gen",
)


def website_ads_honesty() -> dict[str, Any]:
    """Public honesty envelope for Trust Center + ``POST /api/ad/fills``.

    Pure / side-effect free. Callers embed this dict; they never invent
    revenue from it.
    """
    return {
        "surface": "website",
        "serving_model": "antiek_owned_creatives",
        "max_sdk_on_web": False,
        "fill_ladder": list(FILL_LADDER),
        "price_status_default": "unpriced",
        "revenue_usd_cents_until_pricing": 0,
        "pricing_gate": "rank_0_1_ad_pricing",
        "legal_gate": "rank_0_2_advertiser_legal_gate",
        "speak_contributor_share": SPEAK_CONTRIBUTOR_SHARE,
        "speak_platform_share": SPEAK_PLATFORM_SHARE,
        "money_model": "no_fake_cents_until_settled_pricing",
        "disbursement": "accrue_escrow_now_disburse_after_legal_review",
        "decision_ref": DECISION_REF,
        "spec_ref": SPEC_REF,
    }


def assert_unpriced_zero(revenue_usd_cents: int, price_status: str) -> None:
    """Invariant helper for tests / call sites still on Rank 0."""
    if price_status == "unpriced" and revenue_usd_cents != 0:
        raise ValueError(
            "unpriced fills must record revenue_usd_cents=0 "
            "(no fake cents before Rank 0.1)"
        )

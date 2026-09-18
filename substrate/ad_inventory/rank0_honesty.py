"""Website Ads Rank 0 / 0.1 honesty envelope (no fake cents).

Single source of truth for the website monetization posture:

- Antiek-served creatives only (house → manual sponsor → lead-gen).
- No AppLovin MAX SDK on web (no web publisher SDK exists; doctrine REJECT).
- ``revenue_usd_cents`` stays 0 and ``price_status`` stays ``unpriced`` until
  Rank 0.1 pricing authority + Rank 0.2 legal gate clear via
  ``settle_fill_decision`` (never via ``decide_fills``).
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
RANK01_DECISION_REF = (
    "docs/decisions/ads-rank01-pricing-settlement-gate-2026-09-18.md"
)

# Platform / contributor split — master-spec §9.1. Applies only after
# settled pricing; never mint cents from this share alone.
SPEAK_CONTRIBUTOR_SHARE = 0.70
SPEAK_PLATFORM_SHARE = 0.30

FILL_LADDER: tuple[str, ...] = (
    "house",
    "manual_sponsor",
    "lead_gen",
)

SETTLEMENT_REQUIRES: tuple[str, ...] = (
    "rank_0_1_pricing_authority_ref",
    "rank_0_2_legal_gate_passed",
    "revenue_usd_cents_gt_0",
    "not_house_only_fill",
)


class SettlementGateError(ValueError):
    """Attempted to settle without Rank 0.1 / 0.2 gates."""


def website_ads_honesty() -> dict[str, Any]:
    """Public honesty envelope for Trust Center + ``POST /api/ad/fills``.

    Pure / side-effect free. Callers embed this dict; they never invent
    revenue from it. ``settlement_open`` stays False until an operator
    actually settles a fill via the gated API — the envelope does not
    flip itself.
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
        "settlement_open": False,
        "settlement_path": "settle_fill_decision",
        "settlement_requires": list(SETTLEMENT_REQUIRES),
        "speak_contributor_share": SPEAK_CONTRIBUTOR_SHARE,
        "speak_platform_share": SPEAK_PLATFORM_SHARE,
        "money_model": "no_fake_cents_until_settled_pricing",
        "disbursement": "accrue_escrow_now_disburse_after_legal_review",
        "decision_ref": DECISION_REF,
        "spec_ref": SPEC_REF,
        "rank01_decision_ref": RANK01_DECISION_REF,
    }


def assert_unpriced_zero(revenue_usd_cents: int, price_status: str) -> None:
    """Invariant helper for tests / call sites still on Rank 0."""
    if price_status == "unpriced" and revenue_usd_cents != 0:
        raise ValueError(
            "unpriced fills must record revenue_usd_cents=0 "
            "(no fake cents before Rank 0.1)"
        )


def assert_settlement_allowed(
    *,
    revenue_usd_cents: int,
    legal_gate_passed: bool,
    pricing_authority_ref: str,
) -> None:
    """Deny settled pricing unless Rank 0.1 + 0.2 gates are explicit.

    Never invents cents — only validates that the caller may record the
    cents they already computed from a real authority.
    """
    if not legal_gate_passed:
        raise SettlementGateError(
            "settlement denied: legal_gate_passed must be True "
            "(Rank 0.2 / activate_advertiser invariant)"
        )
    ref = (pricing_authority_ref or "").strip()
    if not ref:
        raise SettlementGateError(
            "settlement denied: pricing_authority_ref required "
            "(Rank 0.1 — real budget / billing authority, not CPM ranking)"
        )
    if int(revenue_usd_cents) <= 0:
        raise SettlementGateError(
            "settlement denied: revenue_usd_cents must be > 0 "
            "(refusing to settle $0 as priced; house stays unpriced)"
        )


__all__ = [
    "DECISION_REF",
    "FILL_LADDER",
    "RANK01_DECISION_REF",
    "SETTLEMENT_REQUIRES",
    "SPEAK_CONTRIBUTOR_SHARE",
    "SPEAK_PLATFORM_SHARE",
    "SPEC_REF",
    "SettlementGateError",
    "assert_settlement_allowed",
    "assert_unpriced_zero",
    "website_ads_honesty",
]

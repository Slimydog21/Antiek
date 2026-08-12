"""Ad impressions + inventory-select API (Sprint 23-24 phase 1+2).

Two endpoints:

  POST /ad-impressions       — retired client-priced revenue path (410)
  GET  /ad-inventory/select  — invoke the targeted matcher; return chosen ad

This is the substrate's served-ad emission surface. The reading
surface calls ``/ad-inventory/select`` at page-render time to choose
an ad, then calls ``POST /ad-impressions`` when the ad is actually
served + viewed.

Live activation gates per master-spec §9.0 + §9.4:
  - No advertiser may serve unless ACTIVE in the advertisers table.
  - No payout decision routes if FraudVerdict is BLOCK (anti-gaming).
  - Below-§9.5 amounts route to rollover regardless of KYC.
  - At/above-§9.5 amounts gate on KYC=COMPLETED for the recipient.
"""

from __future__ import annotations

import duckdb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.ad_inventory import (
    AdInventoryItem,
    PageContext,
    TargetedInventoryItem,
    select_targeted_ad,
)

# ── Pydantic shapes ────────────────────────────────────────────────


class AdSelectRequest(BaseModel):
    """Page-side request for an ad. The reading surface passes
    page-level signals; substrate picks the best-targeted ad."""

    sector: str | None = None
    sub_sector: str | None = None
    audience_intents: tuple[str, ...] = ()
    flat_topics: tuple[str, ...] = ()


class AdSelectResponse(BaseModel):
    """Picked inventory item — None-equivalent shape if no match."""

    inventory_id: str | None
    advertiser_display_name: str | None
    cpm_usd: str | None
    creative_url: str | None
    landing_url: str | None


class AdImpressionRequest(BaseModel):
    """Record one served ad → attribution → rev-share decisions."""

    impression_id: str = Field(min_length=1, max_length=64)
    inventory_id: str = Field(min_length=1, max_length=64)
    page_id: str = Field(min_length=1, max_length=64)
    investigation_id: str | None = None
    revenue_usd_cents: int = Field(ge=0)
    # document_id → share map (decimal in [0, 1], sum ≤ 1)
    attribution_shares: dict[str, float]
    # document_id → (kind, recipient_ref, requires_escrow) tuple
    document_to_recipient: dict[
        str, tuple[str, str, bool]
    ] = Field(default_factory=dict)


class RevShareDecisionResponse(BaseModel):
    decision_id: str
    impression_id: str
    kind: str
    recipient_ref: str
    amount_usd_cents: int
    document_id: str | None
    requires_escrow: bool
    capped_to_daily_limit: bool


class AdImpressionResponse(BaseModel):
    impression_id: str
    decisions: list[RevShareDecisionResponse]


# ── Helpers ────────────────────────────────────────────────────────


def _refuse(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _load_serving_inventory(con) -> tuple[
    list[TargetedInventoryItem], list[AdInventoryItem],
]:
    """Load the operator-curated active inventory from the V6
    ``ad_inventory_items`` table. The split (targeted vs flat-fallback)
    mirrors ``select_targeted_ad``'s contract."""
    from substrate.ad_inventory.inventory_persistence import (
        load_serving_for_matcher,
    )

    return load_serving_for_matcher(con)


# ── Routes ─────────────────────────────────────────────────────────


def register_ad_impression_routes(app: FastAPI) -> None:
    """Mount the ad-impressions + inventory-select endpoints."""

    @app.post(
        "/ad-inventory/select",
        response_model=AdSelectResponse,
        tags=["ad-inventory"],
    )
    async def post_select_ad(req: AdSelectRequest) -> AdSelectResponse:
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            targeted, flat = _load_serving_inventory(con)
        finally:
            con.close()
        ctx = PageContext(
            sector=req.sector,
            sub_sector=req.sub_sector,
            audience_intents=tuple(req.audience_intents),
            flat_topics=tuple(req.flat_topics),
        )
        chosen = select_targeted_ad(
            context=ctx,
            targeted_inventory=targeted,
            flat_inventory_fallback=flat if flat else None,
        )
        if chosen is None:
            return AdSelectResponse(
                inventory_id=None, advertiser_display_name=None,
                cpm_usd=None, creative_url=None, landing_url=None,
            )
        return AdSelectResponse(
            inventory_id=chosen.inventory_id,
            advertiser_display_name=chosen.advertiser_display_name,
            cpm_usd=str(chosen.cpm_usd),
            creative_url=chosen.creative_url,
            landing_url=chosen.landing_url,
        )

    @app.post(
        "/ad-impressions",
        response_model=AdImpressionResponse,
        status_code=201,
        tags=["ad-inventory"],
    )
    async def post_impression(
        req: AdImpressionRequest,
    ) -> AdImpressionResponse:
        # Tombstoned: this legacy body lets a browser author both the price and
        # payout recipients.  Fill decisions are now server-owned and unpriced;
        # accepting this write would invent (or double-credit) money.
        _ = req
        raise HTTPException(
            status_code=410,
            detail="client_priced_ad_impressions_disabled",
        )


__all__ = [
    "AdImpressionRequest",
    "AdImpressionResponse",
    "AdSelectRequest",
    "AdSelectResponse",
    "RevShareDecisionResponse",
    "register_ad_impression_routes",
]

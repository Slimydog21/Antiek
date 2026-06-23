"""Ad impressions + inventory-select API (Sprint 23-24 phase 1+2).

Two endpoints:

  POST /ad-impressions       — record a served ad; emit RevShareDecisions
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

from fastapi import FastAPI, HTTPException
from runtime.db_lock import connect_read
from pydantic import BaseModel, Field

from substrate.ad_inventory import (
    AdInventoryItem,
    PageContext,
    PayoutRouter,
    TargetedInventoryItem,
    distribute_session_ad_revenue,
    select_targeted_ad,
)
from substrate.ad_inventory.payout import RevShareKind

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
        con = connect_read(db)
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
        # Validate attribution shares sum ≤ 1.0.
        total_share = sum(req.attribution_shares.values())
        if total_share > 1.0001:  # epsilon
            raise _refuse(
                422, "invalid_shares",
                f"attribution_shares sum to {total_share:.4f}; must be ≤ 1.0",
            )
        # Map the recipient-kind string into the enum.
        recipient_map: dict[str, tuple[RevShareKind, str, bool]] = {}
        for doc_id, (kind_str, recipient_ref, requires_escrow) in (
            req.document_to_recipient.items()
        ):
            try:
                kind = RevShareKind(kind_str)
            except ValueError:
                raise _refuse(
                    422, "invalid_kind",
                    f"unknown RevShareKind {kind_str!r}",
                )
            recipient_map[doc_id] = (kind, recipient_ref, bool(requires_escrow))

        router = PayoutRouter()
        decisions = distribute_session_ad_revenue(
            router,
            impression_id=req.impression_id,
            ad_revenue_usd_cents=req.revenue_usd_cents,
            attribution_shares=req.attribution_shares,
            document_to_recipient=recipient_map,
        )
        try:
            from substrate.observability.product_mirror import mirror_layer_event

            mirror_layer_event(
                "read",
                "ad_impression_recorded",
                impression_id=req.impression_id,
                revenue_usd_cents=req.revenue_usd_cents,
            )
        except Exception:
            pass
        return AdImpressionResponse(
            impression_id=req.impression_id,
            decisions=[
                RevShareDecisionResponse(
                    decision_id=d.decision_id,
                    impression_id=d.impression_id,
                    kind=d.kind.value,
                    recipient_ref=d.recipient_ref,
                    amount_usd_cents=d.amount_usd_cents,
                    document_id=d.document_id,
                    requires_escrow=d.requires_escrow,
                    capped_to_daily_limit=d.capped_to_daily_limit,
                )
                for d in decisions
            ],
        )


__all__ = [
    "AdImpressionRequest",
    "AdImpressionResponse",
    "AdSelectRequest",
    "AdSelectResponse",
    "RevShareDecisionResponse",
    "register_ad_impression_routes",
]

"""Operator advertiser-campaign API.

Backs ``apps/reading/src/modes/AdvertiserConsole`` with the existing
``substrate.advertisers`` store. This is the manual-sales operator surface:
GET/list, POST/create, and PATCH/status-update only. It does not invoice,
charge, serve, or activate advertiser self-service.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.advertisers import (
    Advertiser,
    AdvertiserCampaign,
    CampaignStatus,
    SqliteAdvertiserStore,
    create_advertiser,
    create_campaign,
    update_campaign_status,
)


class AdvertiserCampaignResponse(BaseModel):
    campaign_id: str
    advertiser_id: str
    advertiser_name: str
    sector: str
    sub_sector: str | None
    intent: str
    target_topics: tuple[str, ...]
    creative_headline: str
    creative_url: str
    daily_budget_cents: int
    status: str
    impressions: int
    clicks: int
    spend_cents: int
    created_at: str


class AdvertiserCampaignListResponse(BaseModel):
    campaigns: list[AdvertiserCampaignResponse]


class CreateAdvertiserCampaignRequest(BaseModel):
    advertiser_id: str | None = Field(default=None, min_length=1, max_length=128)
    advertiser_name: str = Field(min_length=1, max_length=200)
    contact_email: str = Field(min_length=3, max_length=200)
    sector: str = Field(min_length=1, max_length=120)
    sub_sector: str | None = Field(default=None, max_length=120)
    intent: str = Field(min_length=1, max_length=120)
    target_topics: tuple[str, ...] = ()
    creative_headline: str = Field(min_length=1, max_length=240)
    creative_url: str = Field(min_length=1, max_length=1000)
    daily_budget_cents: int = Field(ge=0)
    status: CampaignStatus = CampaignStatus.DRAFT
    legal_gate_passed: bool = False


class UpdateAdvertiserCampaignStatusRequest(BaseModel):
    status: CampaignStatus
    legal_gate_passed: bool = False


def _refuse(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _store_path() -> str:
    override = os.environ.get("ANTIEK_ADVERTISER_STORE_PATH", "").strip()
    if override:
        return override
    from substrate.graph import default_db_path, ensure_initialized

    duckdb_path = Path(default_db_path())
    ensure_initialized(str(duckdb_path))
    return str(duckdb_path.with_name("advertisers.sqlite"))


def _store() -> SqliteAdvertiserStore:
    return SqliteAdvertiserStore(_store_path())


def _campaign_response(
    store: SqliteAdvertiserStore,
    campaign: AdvertiserCampaign,
) -> AdvertiserCampaignResponse:
    advertiser = store.get_advertiser(campaign.advertiser_id)
    advertiser_name = (
        advertiser.display_name if advertiser is not None else campaign.advertiser_id
    )
    return AdvertiserCampaignResponse(
        campaign_id=campaign.campaign_id,
        advertiser_id=campaign.advertiser_id,
        advertiser_name=advertiser_name,
        sector=campaign.sector,
        sub_sector=campaign.sub_sector,
        intent=campaign.intent,
        target_topics=campaign.target_topics,
        creative_headline=campaign.creative_headline,
        creative_url=campaign.creative_url,
        daily_budget_cents=campaign.daily_budget_cents,
        status=campaign.status.value,
        impressions=campaign.impressions,
        clicks=campaign.clicks,
        spend_cents=campaign.spend_cents,
        created_at=campaign.created_at,
    )


def _ensure_advertiser(
    store: SqliteAdvertiserStore,
    req: CreateAdvertiserCampaignRequest,
) -> Advertiser:
    if req.advertiser_id:
        existing = store.get_advertiser(req.advertiser_id)
        if existing is not None:
            return existing
        advertiser = Advertiser(
            advertiser_id=req.advertiser_id,
            display_name=req.advertiser_name,
            sector=req.sector,
            contact_email=req.contact_email,
            stripe_customer_id=None,
        )
        store.upsert_advertiser(advertiser)
        return advertiser
    return create_advertiser(
        store,
        display_name=req.advertiser_name,
        sector=req.sector,
        contact_email=req.contact_email,
    )


def _require_legal_gate_for_active(
    status: CampaignStatus,
    *,
    legal_gate_passed: bool,
) -> None:
    if status == CampaignStatus.ACTIVE and not legal_gate_passed:
        raise _refuse(
            409,
            "legal_gate",
            "legal_gate_passed=true is required before a campaign becomes active.",
        )


def register_operator_advertiser_campaign_routes(app: FastAPI) -> None:
    """Mount the operator-only advertiser campaign CRUD routes."""

    @app.get(
        "/operator/advertiser-campaigns",
        response_model=AdvertiserCampaignListResponse,
        tags=["advertisers"],
    )
    async def list_operator_advertiser_campaigns(
        status: CampaignStatus | None = None,
    ) -> AdvertiserCampaignListResponse:
        store = _store()
        campaigns = store.list_campaigns()
        if status is not None:
            campaigns = [c for c in campaigns if c.status == status]
        campaigns.sort(key=lambda c: (c.created_at, c.campaign_id), reverse=True)
        return AdvertiserCampaignListResponse(
            campaigns=[_campaign_response(store, c) for c in campaigns],
        )

    @app.post(
        "/operator/advertiser-campaigns",
        response_model=AdvertiserCampaignResponse,
        status_code=201,
        tags=["advertisers"],
    )
    async def create_operator_advertiser_campaign(
        req: CreateAdvertiserCampaignRequest,
    ) -> AdvertiserCampaignResponse:
        _require_legal_gate_for_active(
            req.status,
            legal_gate_passed=req.legal_gate_passed,
        )
        store = _store()
        advertiser = _ensure_advertiser(store, req)
        try:
            campaign = create_campaign(
                store,
                advertiser_id=advertiser.advertiser_id,
                sector=req.sector,
                sub_sector=req.sub_sector,
                intent=req.intent,
                target_topics=tuple(req.target_topics),
                creative_headline=req.creative_headline,
                creative_url=req.creative_url,
                daily_budget_cents=req.daily_budget_cents,
                status=req.status,
            )
        except ValueError as exc:
            raise _refuse(400, "invalid_advertiser_campaign", str(exc)) from exc
        return _campaign_response(store, campaign)

    @app.patch(
        "/operator/advertiser-campaigns/{campaign_id}/status",
        response_model=AdvertiserCampaignResponse,
        tags=["advertisers"],
    )
    async def update_operator_advertiser_campaign_status(
        campaign_id: str,
        req: UpdateAdvertiserCampaignStatusRequest,
    ) -> AdvertiserCampaignResponse:
        _require_legal_gate_for_active(
            req.status,
            legal_gate_passed=req.legal_gate_passed,
        )
        store = _store()
        try:
            campaign = update_campaign_status(
                store,
                campaign_id=campaign_id,
                new_status=req.status,
            )
        except ValueError as exc:
            raise _refuse(404, "campaign_not_found", str(exc)) from exc
        return _campaign_response(store, campaign)


__all__ = [
    "AdvertiserCampaignListResponse",
    "AdvertiserCampaignResponse",
    "CreateAdvertiserCampaignRequest",
    "UpdateAdvertiserCampaignStatusRequest",
    "register_operator_advertiser_campaign_routes",
]

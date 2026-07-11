"""Registerable HTTP surface for marketplace HTML view + twin session."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_html_view_twin_session_compose import (
    MarketplaceHtmlViewTwinSessionComposeError,
    compose_marketplace_html_view_twin_session,
)

marketplace_html_view_twin_session_compose_router = APIRouter(
    prefix="/research/marketplace-html-view-twin-session",
    tags=["marketplace-html-view-twin-session-compose"],
)


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=128)
    purchase_html_projection_sha: str | None = Field(
        default=None, max_length=128
    )
    port_requested: bool = Field(strict=True)
    purchase_ack: bool = Field(strict=True)
    list_price_usd: float | None = Field(default=None, ge=0)
    approved_spend_usd: float | None = Field(default=None, ge=0)
    remaining_budget_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    view_requested: bool = Field(strict=True)
    twin_bound: bool | None = None
    twin_substrate_ready: bool | None = None
    claimed_format: str | None = Field(default=None, max_length=64)
    twin_findings: list[FindingBody] | None = None
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=False, strict=True)
    include_twin_feed: bool = Field(default=True, strict=True)


@marketplace_html_view_twin_session_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_html_view_twin_session(
            session_id=req.session_id,
            asset_id=req.asset_id,
            title=req.title,
            account_id=req.account_id,
            free_copy_available=req.free_copy_available,
            free_html_projection_sha=req.free_html_projection_sha,
            purchase_html_projection_sha=req.purchase_html_projection_sha,
            port_requested=req.port_requested,
            purchase_ack=req.purchase_ack,
            list_price_usd=req.list_price_usd,
            approved_spend_usd=req.approved_spend_usd,
            remaining_budget_usd=req.remaining_budget_usd,
            operator_ack=req.operator_ack,
            view_requested=req.view_requested,
            twin_bound=req.twin_bound,
            twin_substrate_ready=req.twin_substrate_ready,
            claimed_format=req.claimed_format,
            twin_findings=(
                [f.model_dump() for f in req.twin_findings]
                if req.twin_findings is not None
                else None
            ),
            existing_twin_asset_id=req.existing_twin_asset_id,
            mark_for_prompt_context=req.mark_for_prompt_context,
            include_twin_feed=req.include_twin_feed,
        )
    except MarketplaceHtmlViewTwinSessionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_html_view_twin_session_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(marketplace_html_view_twin_session_compose_router)


__all__ = [
    "marketplace_html_view_twin_session_compose_router",
    "register_marketplace_html_view_twin_session_compose_routes",
]

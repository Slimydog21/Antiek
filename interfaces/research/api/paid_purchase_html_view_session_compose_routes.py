"""Registerable HTTP surface for paid purchase HTML view session compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.paid_purchase_html_view_session_compose import (
    PaidPurchaseHtmlViewSessionComposeError,
    compose_paid_purchase_html_view_session,
)

paid_purchase_html_view_session_compose_router = APIRouter(
    prefix="/research/paid-purchase-html-view-session",
    tags=["paid-purchase-html-view-session-compose"],
)


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
    twin_bound: bool = Field(default=False, strict=True)
    twin_substrate_ready: bool | None = None
    claimed_format: str | None = Field(default=None, max_length=64)


@paid_purchase_html_view_session_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_paid_purchase_html_view_session(
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
        )
    except PaidPurchaseHtmlViewSessionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_paid_purchase_html_view_session_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(paid_purchase_html_view_session_compose_router)


__all__ = [
    "paid_purchase_html_view_session_compose_router",
    "register_paid_purchase_html_view_session_compose_routes",
]

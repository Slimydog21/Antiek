"""Registerable HTTP surface for marketplace paid purchase gate compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_paid_purchase_gate_compose import (
    MarketplacePaidPurchaseGateComposeError,
    compose_marketplace_paid_purchase_gate,
)

marketplace_paid_purchase_gate_compose_router = APIRouter(
    prefix="/research/marketplace-paid-purchase-gate",
    tags=["marketplace-paid-purchase-gate-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

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


@marketplace_paid_purchase_gate_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_paid_purchase_gate(
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
        )
    except MarketplacePaidPurchaseGateComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_paid_purchase_gate_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(marketplace_paid_purchase_gate_compose_router)


__all__ = [
    "marketplace_paid_purchase_gate_compose_router",
    "register_marketplace_paid_purchase_gate_compose_routes",
]

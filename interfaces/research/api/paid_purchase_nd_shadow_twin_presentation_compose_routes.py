"""Registerable HTTP surface for paid-purchase free-first + ND twin presentation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.nd_shadow_twin_presentation_competition_compose_routes import (
    NdShadowBody,
    TwinPresentationBody,
)
from substrate.paid_purchase_nd_shadow_twin_presentation_compose import (
    PaidPurchaseNdShadowTwinPresentationComposeError,
    compose_paid_purchase_nd_shadow_twin_presentation,
)

paid_purchase_nd_shadow_twin_presentation_compose_router = APIRouter(
    prefix="/research/paid-purchase-nd-shadow-twin-presentation",
    tags=["paid-purchase-nd-shadow-twin-presentation-compose"],
)


class PurchaseBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_html_projection_sha: str | None = Field(
        default=None, max_length=256
    )
    port_requested: bool = Field(strict=True)
    purchase_ack: bool = Field(strict=True)
    list_price_usd: float | None = Field(default=None, ge=0)
    approved_spend_usd: float | None = Field(default=None, ge=0)
    remaining_budget_usd: float | None = Field(default=None, ge=0)


class NdTwinBody(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    twin_presentation: TwinPresentationBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    purchase: PurchaseBody
    nd_twin: NdTwinBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@paid_purchase_nd_shadow_twin_presentation_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_paid_purchase_nd_shadow_twin_presentation(
            purchase=req.purchase.model_dump(),
            nd_twin=req.nd_twin.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except PaidPurchaseNdShadowTwinPresentationComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_paid_purchase_nd_shadow_twin_presentation_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        paid_purchase_nd_shadow_twin_presentation_compose_router
    )


__all__ = [
    "paid_purchase_nd_shadow_twin_presentation_compose_router",
    "register_paid_purchase_nd_shadow_twin_presentation_compose_routes",
]

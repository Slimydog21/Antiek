"""Registerable HTTP surface for marketplace free over settings ND twin presentation pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_add_model_nd_shadow_twin_presentation_compose_routes import (
    NdPackBody,
    SettingsBody,
)
from substrate.marketplace_free_settings_add_model_nd_shadow_twin_compose import (
    MarketplaceFreeSettingsAddModelNdShadowTwinComposeError,
    compose_marketplace_free_settings_add_model_nd_shadow_twin,
)

marketplace_free_settings_add_model_nd_shadow_twin_compose_router = APIRouter(
    prefix="/research/marketplace-free-settings-add-model-nd-shadow-twin",
    tags=["marketplace-free-settings-add-model-nd-shadow-twin-compose"],
)


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(default=None, max_length=256)
    list_price_usd: float | None = None
    approved_spend_usd: float | None = None
    remaining_budget_usd: float | None = None


class SettingsPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    nd_pack: NdPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    settings_pack: SettingsPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_free_settings_add_model_nd_shadow_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_settings_add_model_nd_shadow_twin(
            market=req.market.model_dump(),
            settings_pack=req.settings_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeSettingsAddModelNdShadowTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_settings_add_model_nd_shadow_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_settings_add_model_nd_shadow_twin_compose_router
    )


__all__ = [
    "marketplace_free_settings_add_model_nd_shadow_twin_compose_router",
    "register_marketplace_free_settings_add_model_nd_shadow_twin_compose_routes",
]

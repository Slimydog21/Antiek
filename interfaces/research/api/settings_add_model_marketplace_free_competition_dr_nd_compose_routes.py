"""Registerable HTTP surface for settings add-model + marketplace free competition DR ND."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.marketplace_free_competition_dr_nd_shadow_source_attach_compose_routes import (
    CompetitionPackBody,
    MarketBody,
)
from substrate.settings_add_model_marketplace_free_competition_dr_nd_compose import (
    SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError,
    compose_settings_add_model_marketplace_free_competition_dr_nd,
)

settings_add_model_marketplace_free_competition_dr_nd_compose_router = APIRouter(
    prefix="/research/settings-add-model-marketplace-free-competition-dr-nd",
    tags=["settings-add-model-marketplace-free-competition-dr-nd-compose"],
)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    tier: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=128)


class SettingsBody(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[ModelBody]
    pending_add_model_ids: list[str]
    action: Literal["preview", "propose_add"]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    selected_model_id: str | None = Field(default=None, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class MarketPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    competition_pack: CompetitionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    market_pack: MarketPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@settings_add_model_marketplace_free_competition_dr_nd_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_marketplace_free_competition_dr_nd(
            settings=req.settings.model_dump(),
            market_pack=req.market_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_marketplace_free_competition_dr_nd_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_add_model_marketplace_free_competition_dr_nd_compose_router
    )


__all__ = [
    "settings_add_model_marketplace_free_competition_dr_nd_compose_router",
    "register_settings_add_model_marketplace_free_competition_dr_nd_compose_routes",
]

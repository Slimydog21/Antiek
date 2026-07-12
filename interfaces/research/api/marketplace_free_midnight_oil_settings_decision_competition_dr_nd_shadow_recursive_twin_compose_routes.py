"""Registerable HTTP surface for marketplace free over MO settings decision pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes import (
    MoBody,
    SettingsPackBody,
)
from substrate.marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose import (
    MarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError,
    compose_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin,
)

marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router = APIRouter(
    prefix="/research/marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin",
    tags=["marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin-compose"],
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


class MoPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    settings_pack: SettingsPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    mo_pack: MoPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin(
            market=req.market.model_dump(),
            mo_pack=req.mo_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router
    )


__all__ = [
    "marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router",
    "register_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes",
]

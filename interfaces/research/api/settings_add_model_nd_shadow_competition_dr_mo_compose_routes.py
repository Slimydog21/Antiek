"""Registerable HTTP surface for settings add-model over ND shadow competition DR MO."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.nd_shadow_competition_dr_mo_unattended_rewrite_compose_routes import (
    CompetitionPackBody,
    NdShadowBody,
)
from substrate.settings_add_model_nd_shadow_competition_dr_mo_compose import (
    SettingsAddModelNdShadowCompetitionDrMoComposeError,
    compose_settings_add_model_nd_shadow_competition_dr_mo,
)

settings_add_model_nd_shadow_competition_dr_mo_compose_router = APIRouter(
    prefix="/research/settings-add-model-nd-shadow-competition-dr-mo",
    tags=["settings-add-model-nd-shadow-competition-dr-mo-compose"],
)


class InventoryModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=128)


class SettingsBody(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[InventoryModelBody]
    pending_add_model_ids: list[str]
    action: Literal["preview", "propose_add"]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    selected_model_id: str | None = Field(default=None, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class NdPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    competition_pack: CompetitionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    nd_pack: NdPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@settings_add_model_nd_shadow_competition_dr_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_nd_shadow_competition_dr_mo(
            settings=req.settings.model_dump(),
            nd_pack=req.nd_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsAddModelNdShadowCompetitionDrMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_nd_shadow_competition_dr_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_add_model_nd_shadow_competition_dr_mo_compose_router
    )


__all__ = [
    "settings_add_model_nd_shadow_competition_dr_mo_compose_router",
    "register_settings_add_model_nd_shadow_competition_dr_mo_compose_routes",
]

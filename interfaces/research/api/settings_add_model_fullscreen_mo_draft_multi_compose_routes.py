"""Registerable HTTP surface for settings add-model + fullscreen MO draft multi pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fullscreen_mo_price_ceiling_draft_multi_compose_routes import (
    FullscreenBody,
    MoPackBody,
)
from substrate.settings_add_model_fullscreen_mo_draft_multi_compose import (
    SettingsAddModelFullscreenMoDraftMultiComposeError,
    compose_settings_add_model_fullscreen_mo_draft_multi,
)

settings_add_model_fullscreen_mo_draft_multi_compose_router = APIRouter(
    prefix="/research/settings-add-model-fullscreen-mo-draft-multi",
    tags=["settings-add-model-fullscreen-mo-draft-multi-compose"],
)


class ModelRowBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    provider: str | None = Field(default=None, max_length=128)


class SettingsBody(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[ModelRowBody] = Field(min_length=1)
    pending_add_model_ids: list[str] = Field(default_factory=list)
    action: Literal["preview", "propose_add"]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    selected_model_id: str | None = Field(default=None, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class FullscreenMoBody(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    fullscreen_mo: FullscreenMoBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@settings_add_model_fullscreen_mo_draft_multi_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_fullscreen_mo_draft_multi(
            settings=req.settings.model_dump(),
            fullscreen_mo=req.fullscreen_mo.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsAddModelFullscreenMoDraftMultiComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_fullscreen_mo_draft_multi_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_add_model_fullscreen_mo_draft_multi_compose_router
    )


__all__ = [
    "settings_add_model_fullscreen_mo_draft_multi_compose_router",
    "register_settings_add_model_fullscreen_mo_draft_multi_compose_routes",
]

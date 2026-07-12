"""Registerable HTTP surface for settings add-model + draft fullscreen weekly ND."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes import (
    DraftGateBody,
    FullscreenPackBody,
)
from interfaces.research.api.settings_add_model_inventory_compose_routes import (
    ModelBody,
)
from substrate.settings_add_model_draft_fullscreen_weekly_nd_mo_compose import (
    SettingsAddModelDraftFullscreenWeeklyNdMoComposeError,
    compose_settings_add_model_draft_fullscreen_weekly_nd_mo,
)

settings_add_model_draft_fullscreen_weekly_nd_mo_compose_router = APIRouter(
    prefix="/research/settings-add-model-draft-fullscreen-weekly-nd-mo",
    tags=["settings-add-model-draft-fullscreen-weekly-nd-mo-compose"],
)


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


class ResearchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    fullscreen_pack: FullscreenPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    research_pack: ResearchPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@settings_add_model_draft_fullscreen_weekly_nd_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_draft_fullscreen_weekly_nd_mo(
            settings=req.settings.model_dump(),
            research_pack=req.research_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsAddModelDraftFullscreenWeeklyNdMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_add_model_draft_fullscreen_weekly_nd_mo_compose_router
    )


__all__ = [
    "settings_add_model_draft_fullscreen_weekly_nd_mo_compose_router",
    "register_settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes",
]

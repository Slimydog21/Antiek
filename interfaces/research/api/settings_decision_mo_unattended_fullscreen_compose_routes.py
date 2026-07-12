"""Registerable HTTP surface for settings decision + MO unattended fullscreen."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.mo_unattended_fullscreen_draft_collective_compose_routes import (
    FullscreenPackBody,
    MoBody,
)
from interfaces.research.api.settings_decision_tree_usage_bar_compose_routes import (
    ModelBody,
)
from substrate.settings_decision_mo_unattended_fullscreen_compose import (
    SettingsDecisionMoUnattendedFullscreenComposeError,
    compose_settings_decision_mo_unattended_fullscreen,
)

settings_decision_mo_unattended_fullscreen_compose_router = APIRouter(
    prefix="/research/settings-decision-mo-unattended-fullscreen",
    tags=["settings-decision-mo-unattended-fullscreen-compose"],
)


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None
    focus_task: str | None = Field(default=None, max_length=256)
    pending_add_model_ids: list[str] | None = None


class MoPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    fullscreen_pack: FullscreenPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    mo_pack: MoPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@settings_decision_mo_unattended_fullscreen_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_decision_mo_unattended_fullscreen(
            decision=req.decision.model_dump(),
            mo_pack=req.mo_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsDecisionMoUnattendedFullscreenComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_decision_mo_unattended_fullscreen_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_decision_mo_unattended_fullscreen_compose_router
    )


__all__ = [
    "settings_decision_mo_unattended_fullscreen_compose_router",
    "register_settings_decision_mo_unattended_fullscreen_compose_routes",
]

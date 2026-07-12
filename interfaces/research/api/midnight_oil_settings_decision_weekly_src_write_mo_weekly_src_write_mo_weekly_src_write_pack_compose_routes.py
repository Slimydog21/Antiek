"""Registerable HTTP surface for Midnight Oil over settings decision competition DR."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    CompetitionPackBody,
    SettingsBody,
)
from substrate.midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    MidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/midnight-oil-settings-decision-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["midnight-oil-settings-decision-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: int = Field(ge=1)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_ack: bool = Field(strict=True)
    stage: Literal["recommend_only", "approve_ceiling", "unattended_pack"]
    usd_per_hour: float | None = Field(default=None, ge=0)
    goal_intensity: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    below_recommend_override: bool | None = Field(default=None, strict=True)
    unattended_ack: bool | None = Field(default=None, strict=True)
    spend_consent: bool | None = Field(default=None, strict=True)


class SettingsPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    competition_pack: CompetitionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    settings_pack: SettingsPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            mo=req.mo.model_dump(),
            settings_pack=req.settings_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

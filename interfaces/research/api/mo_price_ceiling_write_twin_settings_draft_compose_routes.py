"""Registerable HTTP surface for MO price-ceiling + write twin settings pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.midnight_oil_price_ceiling_approval_compose_routes import (
    GoalBody,
)
from interfaces.research.api.write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes import (
    SettingsResearchBody,
    WriteBody,
)
from substrate.mo_price_ceiling_write_twin_settings_draft_compose import (
    MoPriceCeilingWriteTwinSettingsDraftComposeError,
    compose_mo_price_ceiling_write_twin_settings_draft,
)

mo_price_ceiling_write_twin_settings_draft_compose_router = APIRouter(
    prefix="/research/mo-price-ceiling-write-twin-settings-draft",
    tags=["mo-price-ceiling-write-twin-settings-draft-compose"],
)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: int = Field(ge=1, le=24 * 60)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_ack: bool = Field(strict=True)
    stage: Literal["recommend_only", "approve_ceiling", "unattended_pack"]
    usd_per_hour: float | None = Field(default=None, ge=0)
    goal_intensity: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    below_recommend_override: bool | None = Field(default=None, strict=True)
    unattended_ack: bool | None = Field(default=None, strict=True)
    spend_consent: bool | None = Field(default=None, strict=True)


class ResearchWriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    settings_research: SettingsResearchBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    research_write: ResearchWriteBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@mo_price_ceiling_write_twin_settings_draft_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_mo_price_ceiling_write_twin_settings_draft(
            mo=req.mo.model_dump(),
            research_write=req.research_write.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MoPriceCeilingWriteTwinSettingsDraftComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_mo_price_ceiling_write_twin_settings_draft_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(mo_price_ceiling_write_twin_settings_draft_compose_router)


__all__ = [
    "mo_price_ceiling_write_twin_settings_draft_compose_router",
    "register_mo_price_ceiling_write_twin_settings_draft_compose_routes",
]

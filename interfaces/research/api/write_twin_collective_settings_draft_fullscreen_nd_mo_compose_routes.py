"""Registerable HTTP surface for write twin collective + settings draft fullscreen ND."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_add_model_draft_fullscreen_weekly_nd_mo_compose_routes import (
    ResearchPackBody,
    SettingsBody,
)
from interfaces.research.api.write_mode_twin_collective_analysis_compose_routes import (
    SlotBody,
    TwinSliceBody,
)
from substrate.write_twin_collective_settings_draft_fullscreen_nd_mo_compose import (
    WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError,
    compose_write_twin_collective_settings_draft_fullscreen_nd_mo,
)

write_twin_collective_settings_draft_fullscreen_nd_mo_compose_router = APIRouter(
    prefix="/research/write-twin-collective-settings-draft-fullscreen-nd-mo",
    tags=["write-twin-collective-settings-draft-fullscreen-nd-mo-compose"],
)


class WriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_slices: list[TwinSliceBody] = Field(min_length=1)
    chase_slots: list[SlotBody] = Field(min_length=2)
    analysis_kind: Literal["draft_analysis", "full_analysis"]
    base_draft_html: str | None = Field(default=None, max_length=100000)
    extra_findings: list[str] | None = None
    require_both: bool | None = Field(default=None, strict=True)


class SettingsResearchBody(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    research_pack: ResearchPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    settings_research: SettingsResearchBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@write_twin_collective_settings_draft_fullscreen_nd_mo_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_write_twin_collective_settings_draft_fullscreen_nd_mo(
            write=req.write.model_dump(),
            settings_research=req.settings_research.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        write_twin_collective_settings_draft_fullscreen_nd_mo_compose_router
    )


__all__ = [
    "write_twin_collective_settings_draft_fullscreen_nd_mo_compose_router",
    "register_write_twin_collective_settings_draft_fullscreen_nd_mo_compose_routes",
]

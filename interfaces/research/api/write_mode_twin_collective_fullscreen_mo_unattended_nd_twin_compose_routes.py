"""Registerable HTTP surface for write twin collective + fullscreen MO unattended ND twin."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_routes import (
    FullscreenBody,
    MoPackBody,
)
from substrate.write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose import (
    WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinComposeError,
    compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin,
)

write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_router = APIRouter(
    prefix="/research/write-mode-twin-collective-fullscreen-mo-unattended-nd-twin",
    tags=["write-mode-twin-collective-fullscreen-mo-unattended-nd-twin-compose"],
)

AnalysisKind = Literal["draft_analysis", "full_analysis"]
ChaseStatus = Literal["completed"]


class TwinSliceBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(min_length=1)
    questions: list[str] = Field(default_factory=list)


class ChaseSlotBody(BaseModel):
    model_config = {"extra": "forbid"}

    slot_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: ChaseStatus
    findings: list[str] = Field(min_length=1)
    body: str | None = Field(default=None, max_length=8000)


class WriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_slices: list[TwinSliceBody] = Field(min_length=1)
    chase_slots: list[ChaseSlotBody] = Field(min_length=1)
    analysis_kind: AnalysisKind
    base_draft_html: str | None = Field(default=None, max_length=50000)
    extra_findings: list[str] | None = None
    require_both: bool | None = Field(default=None, strict=True)


class FullscreenPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    fullscreen_pack: FullscreenPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin(
            write=req.write.model_dump(),
            fullscreen_pack=req.fullscreen_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_router
    )


__all__ = [
    "write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_router",
    "register_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_routes",
]

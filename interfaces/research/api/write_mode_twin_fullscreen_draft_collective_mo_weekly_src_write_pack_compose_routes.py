"""Registerable HTTP surface for write twin collective over fullscreen draft-before-merge."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 5000:
    sys.setrecursionlimit(5000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_pack_compose_routes import (
    DraftPackBody,
    FullscreenBody,
)
from interfaces.research.api.write_mode_twin_collective_analysis_compose_routes import (
    SlotBody,
    TwinSliceBody,
)
from substrate.write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose import (
    WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWritePackComposeError,
    compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack,
)

write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_router = (
    APIRouter(
        prefix=(
            "/research/write-mode-twin-fullscreen-draft-collective-mo-weekly-src-write-pack"
        ),
        tags=[
            "write-mode-twin-fullscreen-draft-collective-mo-weekly-src-write-pack-compose"
        ],
    )
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


class FullscreenPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    draft_pack: DraftPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    fullscreen_pack: FullscreenPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = (
            compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack(
                write=req.write.model_dump(),
                fullscreen_pack=req.fullscreen_pack.model_dump(),
                operator_ack=req.operator_ack,
                require_both=req.require_both,
            )
        )
    except WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "WriteBody",
    "FullscreenPackBody",
    "write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_router",
    "register_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_routes",
]

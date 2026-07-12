"""Registerable HTTP surface for write twin collective over fullscreen draft-before-merge."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    DraftPackBody,
    FullscreenBody,
)
from interfaces.research.api.write_mode_twin_collective_analysis_compose_routes import (
    SlotBody,
    TwinSliceBody,
)
from substrate.write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = (
    APIRouter(
        prefix=(
            "/research/write-mode-twin-fullscreen-draft-collective-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack"
        ),
        tags=[
            "write-mode-twin-fullscreen-draft-collective-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"
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



def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + child pack_ready only."""
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "session_aligned": result.session_aligned,
        "parent_aligned": result.parent_aligned,
        "pack_ready": result.pack_ready,
        "draft_written": result.draft_written,
        "analysis_written": result.analysis_written,
        "merge_executed": result.merge_executed,
        "live_dispatched": result.live_dispatched,
        "live_execution_authorized": result.live_execution_authorized,
        "pack_dispatched": result.pack_dispatched,
        "record_persisted": result.record_persisted,
        "prompts_injected": result.prompts_injected,
        "production_router_verdict": result.production_router_verdict,
        "authority": result.authority,
        "write": {
            "pack_ready": result.write.pack_ready,
            "analysis_written": result.write.analysis_written,
            "draft_written": getattr(result.write, "draft_written", False),
        },
        "fullscreen_pack": {
            "pack_ready": result.fullscreen_pack.pack_ready,
            "merge_executed": result.fullscreen_pack.merge_executed,
            "draft_written": result.fullscreen_pack.draft_written,
            "production_router_verdict": result.fullscreen_pack.production_router_verdict,
        },
        "notes_count": len(result.notes),
    }


@write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = (
            compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
                write=req.write.model_dump(),
                fullscreen_pack=req.fullscreen_pack.model_dump(),
                operator_ack=req.operator_ack,
                require_both=req.require_both,
            )
        )
    except WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "WriteBody",
    "FullscreenPackBody",
    "write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

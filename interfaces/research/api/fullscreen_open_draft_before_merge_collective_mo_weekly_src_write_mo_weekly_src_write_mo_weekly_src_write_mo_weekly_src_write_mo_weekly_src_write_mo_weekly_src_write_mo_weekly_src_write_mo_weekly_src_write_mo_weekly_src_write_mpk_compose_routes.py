"""Registerable HTTP surface for fullscreen + draft-before-merge collective MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mw_mpk_compose_routes import (
    CollectivePackBody,
    DraftGateBody,
)
from interfaces.research.api.floating_fullscreen_open_compose_routes import (
    InstanceBody,
    TraySiblingBody,
)
from substrate.fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose import (
    FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpkComposeError,
    compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk,
)

fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_router = APIRouter(
    prefix="/research/fullscreen-open-draft-before-merge-collective-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mpk",
    tags=["fullscreen-open-draft-before-merge-collective-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mpk-compose"],
)


class FullscreenBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    existing_instance: InstanceBody | None = None
    highlight: str | None = Field(default=None, max_length=8000)
    prompt: str | None = Field(default=None, max_length=8000)
    gated: bool | None = Field(default=None, strict=True)
    tray_siblings: list[TraySiblingBody] | None = None


class DraftPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    collective_pack: CollectivePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    draft_pack: DraftPackBody
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
        "merge_executed": result.merge_executed,
        "live_dispatched": result.live_dispatched,
        "pack_dispatched": result.pack_dispatched,
        "analysis_written": result.analysis_written,
        "record_persisted": result.record_persisted,
        "prompts_injected": result.prompts_injected,
        "live_router_authorized": result.live_router_authorized,
        "secrets_stored": result.secrets_stored,
        "remote_index_queried": result.remote_index_queried,
        "pdf_primary": result.pdf_primary,
        "production_router_verdict": result.production_router_verdict,
        "authority": result.authority,
        "fullscreen": {
            "fullscreen_ready": result.fullscreen.fullscreen_ready,
        },
        "draft_pack": {
            "pack_ready": result.draft_pack.pack_ready,
            "draft_written": result.draft_pack.draft_written,
            "merge_executed": result.draft_pack.merge_executed,
            "production_router_verdict": result.draft_pack.production_router_verdict,
        },
        "notes_count": len(result.notes),
    }


@fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
            fullscreen=req.fullscreen.model_dump(),
            draft_pack=req.draft_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpkComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_router
    )


__all__ = [
    "DraftPackBody",
    "FullscreenBody",
    "fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_router",
    "register_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_routes",
]

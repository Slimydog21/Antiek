"""Registerable HTTP surface for recursive twin presentation over weekly source-attach write twin."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    SourcePackBody,
    WeeklyLearnBody,
)
from substrate.recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    RecursiveTwinPresentationWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = (
    APIRouter(
        prefix=(
            "/research/recursive-twin-presentation-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack"
        ),
        tags=[
            "recursive-twin-presentation-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"
        ],
    )
)


class TwinBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=100_000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = Field(default=None)


class PresentationBody(BaseModel):
    model_config = {"extra": "forbid"}

    view_mode: Literal["side_panel", "overlay", "fullscreen_twin", "inline"]
    open_requested: bool = Field(strict=True)
    merge_to_parent_preview: bool | None = Field(default=None, strict=True)
    presented_insights: list[str] | None = Field(default=None)
    presented_questions: list[str] | None = Field(default=None)


class WeeklyPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    source_pack: SourcePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    presentation: PresentationBody
    weekly_pack: WeeklyPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)



def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + child pack_ready only."""
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "session_aligned": result.session_aligned,
        "parent_aligned": result.parent_aligned,
        "pack_ready": result.pack_ready,
        "twin_written": result.twin_written,
        "prompts_injected": result.prompts_injected,
        "merge_executed": result.merge_executed,
        "backlog_mutated": result.backlog_mutated,
        "store_mutated": result.store_mutated,
        "suite_rewritten": result.suite_rewritten,
        "remote_fetched": result.remote_fetched,
        "pdf_primary": result.pdf_primary,
        "draft_written": result.draft_written,
        "live_dispatched": result.live_dispatched,
        "production_router_verdict": result.production_router_verdict,
        "authority": result.authority,
        "presentation": {
            "presentation_ready": result.presentation.presentation_ready,
            "view_mode": getattr(result.presentation, "view_mode", None),
        },
        "weekly_pack": {
            "pack_ready": result.weekly_pack.pack_ready,
            "learn_ready": getattr(result.weekly_pack, "learn_ready", False),
            "backlog_mutated": getattr(result.weekly_pack, "backlog_mutated", False),
            "production_router_verdict": result.weekly_pack.production_router_verdict,
        },
        "twin": {
            "twin_propose_ready": result.twin.twin_propose_ready,
            "twin_written": getattr(result.twin, "twin_written", False),
        },
        "notes_count": len(result.notes),
    }


@recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            twin=req.twin.model_dump(),
            presentation=req.presentation.model_dump(),
            weekly_pack=req.weekly_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinPresentationWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "TwinBody",
    "PresentationBody",
    "WeeklyPackBody",
    "recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

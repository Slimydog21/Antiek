"""Registerable HTTP surface for Antiek-bench weekly learn + source attach write twin."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    SourcesBody,
    WritePackBody,
)
from substrate.antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    AntiekBenchWeeklySrcWriteFsDraftMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/antiek-bench-weekly-src-write-fs-draft-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["antiek-bench-weekly-src-write-fs-draft-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class EventBody(BaseModel):
    model_config = {"extra": "forbid"}

    event_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    outcome: Literal["worked", "failed", "mixed", "unknown"]
    score: float | None = Field(default=None, ge=0, le=1)


class WeeklyLearnBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    events: list[EventBody]
    min_events_per_task: int | None = Field(default=None, ge=1)


class SourcePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    write_pack: WritePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    source_pack: SourcePackBody
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
        "learn_ready": result.learn_ready,
        "attach_ready": result.attach_ready,
        "backlog_mutated": result.backlog_mutated,
        "store_mutated": result.store_mutated,
        "suite_rewritten": result.suite_rewritten,
        "remote_fetched": result.remote_fetched,
        "pdf_view_authorized": result.pdf_view_authorized,
        "pdf_primary": result.pdf_primary,
        "draft_written": result.draft_written,
        "analysis_written": result.analysis_written,
        "twin_written": result.twin_written,
        "live_router_authorized": result.live_router_authorized,
        "secrets_stored": result.secrets_stored,
        "production_router_verdict": result.production_router_verdict,
        "authority": result.authority,
        "weekly_learn": {
            "learn_ready": result.weekly_learn.learn_ready,
            "week_id": result.weekly_learn.week_id,
            "backlog_mutated": getattr(result.weekly_learn, "backlog_mutated", False),
            "suite_rewritten": getattr(result.weekly_learn, "suite_rewritten", False),
        },
        "source_pack": {
            "pack_ready": result.source_pack.pack_ready,
            "attach_ready": getattr(result.source_pack, "attach_ready", False),
            "remote_fetched": result.source_pack.remote_fetched,
            "production_router_verdict": result.source_pack.production_router_verdict,
        },
        "notes_count": len(result.notes),
    }


@antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            weekly_learn=req.weekly_learn.model_dump(),
            source_pack=req.source_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except AntiekBenchWeeklySrcWriteFsDraftMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "WeeklyLearnBody",
    "SourcePackBody",
    "antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

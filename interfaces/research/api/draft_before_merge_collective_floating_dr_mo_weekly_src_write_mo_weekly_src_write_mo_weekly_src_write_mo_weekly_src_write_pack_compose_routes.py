"""Registerable HTTP surface for draft-before-merge + collective multiselect floating DR MO weekly src write."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    FloatingPackBody,
    MultiselectBody,
)
from substrate.draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    DraftBeforeMergeCollectiveFloatingDrMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = (
    APIRouter(
        prefix="/research/draft-before-merge-collective-floating-dr-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
        tags=[
            "draft-before-merge-collective-floating-dr-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"
        ],
    )
)

TrayStatus = Literal["proposed", "open", "completed", "closed"]


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: TrayStatus
    highlight: str | None = Field(default=None, max_length=4000)
    findings: list[str] | None = None


class DraftGateBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    sources: list[SourceBody] = Field(min_length=1)
    stage: Literal["draft_only", "promote_full_merge"]
    parent_excerpt: str | None = Field(default=None, max_length=50000)
    full_merge_ack: bool | None = Field(default=None, strict=True)


class CollectivePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiselectBody
    floating_pack: FloatingPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    collective_pack: CollectivePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = (
            compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
                draft_gate=req.draft_gate.model_dump(),
                collective_pack=req.collective_pack.model_dump(),
                operator_ack=req.operator_ack,
                require_both=req.require_both,
            )
        )
    except DraftBeforeMergeCollectiveFloatingDrMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

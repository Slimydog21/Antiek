"""Registerable HTTP surface for draft-before-merge + fullscreen weekly ND pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.floating_fullscreen_antiek_bench_weekly_nd_mo_compose_routes import (
    FullscreenBody,
    WeeklyNdBody,
)
from substrate.floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose import (
    FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError,
    compose_floating_draft_before_full_merge_fullscreen_weekly_nd_mo,
)

floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_router = APIRouter(
    prefix="/research/floating-draft-before-full-merge-fullscreen-weekly-nd-mo",
    tags=["floating-draft-before-full-merge-fullscreen-weekly-nd-mo-compose"],
)


class DraftSourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    highlight: str | None = Field(default=None, max_length=8000)
    findings: list[str] | None = None


class DraftGateBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    sources: list[DraftSourceBody] = Field(min_length=1)
    stage: Literal["draft_only", "promote_full_merge"]
    parent_excerpt: str | None = Field(default=None, max_length=50000)
    full_merge_ack: bool | None = Field(default=None, strict=True)


class FullscreenPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    weekly_nd: WeeklyNdBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    fullscreen_pack: FullscreenPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_draft_before_full_merge_fullscreen_weekly_nd_mo(
            draft_gate=req.draft_gate.model_dump(),
            fullscreen_pack=req.fullscreen_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_router
    )


__all__ = [
    "floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_router",
    "register_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_routes",
]

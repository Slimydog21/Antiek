"""Registerable HTTP surface for recursive twin presentation over weekly source-attach write twin."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_weekly_src_write_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    SourcePackBody,
    WeeklyLearnBody,
)
from substrate.recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    RecursiveTwinPresentationWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = (
    APIRouter(
        prefix=(
            "/research/recursive-twin-presentation-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack"
        ),
        tags=[
            "recursive-twin-presentation-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"
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


@recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            twin=req.twin.model_dump(),
            presentation=req.presentation.model_dump(),
            weekly_pack=req.weekly_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinPresentationWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "TwinBody",
    "PresentationBody",
    "WeeklyPackBody",
    "recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_recursive_twin_presentation_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

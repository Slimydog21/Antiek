"""Registerable HTTP surface for reading highlight float merge tray compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.reading_highlight_float_merge_tray_compose import (
    ReadingHighlightFloatMergeTrayComposeError,
    compose_reading_highlight_float_merge_tray,
)

reading_highlight_float_merge_tray_compose_router = APIRouter(
    prefix="/research/reading-highlight-float-merge-tray",
    tags=["reading-highlight-float-merge-tray-compose"],
)


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    view_mode: str | None = None
    highlight: str | None = None
    live_dispatched: Literal[False] = False
    merge_executed: Literal[False] = False


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    prompt: str | None = Field(default=None, max_length=4000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None
    existing_members: list[MemberBody] | None = None
    selected_instance_ids: list[str] | None = None
    surface_action: Literal[
        "spawn_only",
        "spawn_and_fullscreen",
        "spawn_and_draft_merge",
        "spawn_and_full_merge",
        "tray_collective",
        "tray_cohesive",
    ]
    operator_ack: bool = Field(strict=True)


@reading_highlight_float_merge_tray_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_reading_highlight_float_merge_tray(
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            gated=req.gated,
            would_exceed=req.would_exceed,
            operator_ack=req.operator_ack,
            prompt=req.prompt,
            preferred_view_mode=req.preferred_view_mode,
            operator_override=req.operator_override,
            selected_model_id=req.selected_model_id,
            source_families=req.source_families,
            existing_members=(
                [m.model_dump() for m in req.existing_members]
                if req.existing_members is not None
                else None
            ),
            selected_instance_ids=req.selected_instance_ids,
            surface_action=req.surface_action,
        )
    except ReadingHighlightFloatMergeTrayComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_reading_highlight_float_merge_tray_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(reading_highlight_float_merge_tray_compose_router)


__all__ = [
    "reading_highlight_float_merge_tray_compose_router",
    "register_reading_highlight_float_merge_tray_compose_routes",
]

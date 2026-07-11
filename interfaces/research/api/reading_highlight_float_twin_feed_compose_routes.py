"""Registerable HTTP surface for reading highlight float + twin feed compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.reading_highlight_float_twin_feed_compose import (
    ReadingHighlightFloatTwinFeedComposeError,
    compose_reading_highlight_float_twin_feed,
)

reading_highlight_float_twin_feed_compose_router = APIRouter(
    prefix="/research/reading-highlight-float-twin-feed",
    tags=["reading-highlight-float-twin-feed-compose"],
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


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    would_exceed: bool | None = None
    surface_action: Literal[
        "spawn_only",
        "spawn_and_fullscreen",
        "spawn_and_draft_merge",
        "spawn_and_full_merge",
        "tray_collective",
        "tray_cohesive",
    ]
    operator_ack: bool = Field(strict=True)
    prompt: str | None = Field(default=None, max_length=4000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    operator_override: bool = Field(default=False, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None
    existing_members: list[MemberBody] | None = None
    selected_instance_ids: list[str] | None = None
    twin_findings: list[FindingBody] | None = None
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=False, strict=True)
    include_twin_feed: bool = Field(default=True, strict=True)


@reading_highlight_float_twin_feed_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_reading_highlight_float_twin_feed(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            gated=req.gated,
            would_exceed=req.would_exceed,
            surface_action=req.surface_action,
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
            twin_findings=(
                [f.model_dump() for f in req.twin_findings]
                if req.twin_findings is not None
                else None
            ),
            existing_twin_asset_id=req.existing_twin_asset_id,
            mark_for_prompt_context=req.mark_for_prompt_context,
            include_twin_feed=req.include_twin_feed,
        )
    except ReadingHighlightFloatTwinFeedComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_reading_highlight_float_twin_feed_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(reading_highlight_float_twin_feed_compose_router)


__all__ = [
    "reading_highlight_float_twin_feed_compose_router",
    "register_reading_highlight_float_twin_feed_compose_routes",
]

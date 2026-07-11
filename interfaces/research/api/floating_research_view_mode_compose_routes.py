"""Registerable HTTP surface for floating research view-mode compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_deep_research import (
    FloatingDeepResearchError,
    FloatingDeepResearchInstance,
    mark_floating_completed,
    spawn_floating_from_highlight,
)
from substrate.floating_research_view_mode_compose import (
    FloatingResearchViewModeComposeError,
    compose_floating_research_view_mode,
)

floating_research_view_mode_compose_router = APIRouter(
    prefix="/research/floating-view-mode",
    tags=["floating-research-view-mode-compose"],
)


class InstanceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    prompt: str = Field(min_length=1, max_length=4000)
    view_mode: Literal["floating", "fullscreen", "merged_draft", "merged_full", "collective"]
    status: Literal["proposed", "open", "completed", "closed"]
    live_dispatched: Literal[False] = False
    merge_executed: Literal[False] = False
    notes: list[str] = Field(default_factory=list)
    authority: str = "operator_spawn_only"


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    instance: InstanceBody
    action: Literal[
        "float", "fullscreen", "propose_draft_merge", "propose_full_merge"
    ]
    operator_ack: bool | None = Field(default=None)


class SpawnAndComposeRequest(BaseModel):
    """Convenience: spawn from highlight then apply action (still pure)."""

    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    prompt: str | None = Field(default=None, max_length=4000)
    mark_completed: bool = Field(default=False, strict=True)
    action: Literal[
        "float", "fullscreen", "propose_draft_merge", "propose_full_merge"
    ]
    operator_ack: bool | None = Field(default=None)


def _instance_from_body(body: InstanceBody) -> FloatingDeepResearchInstance:
    if body.live_dispatched is not False or body.merge_executed is not False:
        raise FloatingResearchViewModeComposeError(
            "live_dispatched and merge_executed must be false"
        )
    return FloatingDeepResearchInstance(
        instance_id=body.instance_id,
        parent_asset_id=body.parent_asset_id,
        highlight=body.highlight,
        prompt=body.prompt,
        view_mode=body.view_mode,
        status=body.status,
        live_dispatched=False,
        merge_executed=False,
        notes=tuple(body.notes),
        authority=body.authority,
    )


@floating_research_view_mode_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        inst = _instance_from_body(req.instance)
        result = compose_floating_research_view_mode(
            instance=inst,
            action=req.action,
            operator_ack=req.operator_ack,
        )
    except (FloatingResearchViewModeComposeError, FloatingDeepResearchError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


@floating_research_view_mode_compose_router.post("/spawn-and-compose")
def post_spawn_and_compose(req: SpawnAndComposeRequest) -> dict[str, Any]:
    try:
        inst = spawn_floating_from_highlight(
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            gated=req.gated,
            prompt=req.prompt,
        )
        if req.mark_completed:
            inst = mark_floating_completed(inst)
        result = compose_floating_research_view_mode(
            instance=inst,
            action=req.action,
            operator_ack=req.operator_ack,
        )
    except (FloatingResearchViewModeComposeError, FloatingDeepResearchError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_research_view_mode_compose_routes(app: FastAPI) -> None:
    app.include_router(floating_research_view_mode_compose_router)


__all__ = [
    "floating_research_view_mode_compose_router",
    "register_floating_research_view_mode_compose_routes",
]

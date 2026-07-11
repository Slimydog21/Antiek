"""Registerable HTTP surface for floating deep research (pure intents)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_deep_research import (
    FloatingDeepResearchError,
    FloatingDeepResearchInstance,
    mark_floating_completed,
    propose_collective_pack,
    propose_draft_merge,
    propose_full_merge,
    set_floating_view_mode,
    spawn_floating_from_highlight,
)

floating_deep_research_router = APIRouter(
    prefix="/research/floating-deep-research",
    tags=["floating-deep-research"],
)


class SpawnRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    prompt: str | None = Field(default=None, max_length=4000)
    view_mode: Literal["floating", "fullscreen"] = "floating"


class InstanceBody(BaseModel):
    """Wire shape for an existing pure instance (no live flags inventable)."""

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
    authority: Literal["operator_spawn_only"] = "operator_spawn_only"


class ViewModeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    instance: InstanceBody
    view_mode: Literal["floating", "fullscreen"]


class InstanceOnlyRequest(BaseModel):
    model_config = {"extra": "forbid"}

    instance: InstanceBody


class FullMergeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    instance: InstanceBody
    operator_ack: bool = Field(strict=True)


class CollectiveRequest(BaseModel):
    model_config = {"extra": "forbid"}

    instances: list[InstanceBody] = Field(min_length=2)


def _to_instance(body: InstanceBody) -> FloatingDeepResearchInstance:
    if body.live_dispatched is not False:
        raise FloatingDeepResearchError("live_dispatched must be false")
    if body.merge_executed is not False:
        raise FloatingDeepResearchError("merge_executed must be false")
    if body.authority != "operator_spawn_only":
        raise FloatingDeepResearchError("authority must be operator_spawn_only")
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
        authority="operator_spawn_only",
    )


@floating_deep_research_router.post("/spawn")
def post_spawn(req: SpawnRequest) -> dict[str, Any]:
    try:
        inst = spawn_floating_from_highlight(
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            gated=req.gated,
            prompt=req.prompt,
            view_mode=req.view_mode,
        )
    except FloatingDeepResearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return inst.to_dict()


@floating_deep_research_router.post("/view-mode")
def post_view_mode(req: ViewModeRequest) -> dict[str, Any]:
    try:
        inst = set_floating_view_mode(_to_instance(req.instance), req.view_mode)
    except FloatingDeepResearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return inst.to_dict()


@floating_deep_research_router.post("/complete")
def post_complete(req: InstanceOnlyRequest) -> dict[str, Any]:
    try:
        inst = mark_floating_completed(_to_instance(req.instance))
    except FloatingDeepResearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return inst.to_dict()


@floating_deep_research_router.post("/draft-merge")
def post_draft_merge(req: InstanceOnlyRequest) -> dict[str, Any]:
    try:
        intent = propose_draft_merge(_to_instance(req.instance))
    except FloatingDeepResearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return intent.to_dict()


@floating_deep_research_router.post("/full-merge")
def post_full_merge(req: FullMergeRequest) -> dict[str, Any]:
    try:
        intent = propose_full_merge(
            _to_instance(req.instance),
            operator_ack=req.operator_ack,
        )
    except FloatingDeepResearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return intent.to_dict()


@floating_deep_research_router.post("/collective-pack")
def post_collective(req: CollectiveRequest) -> dict[str, Any]:
    try:
        intent = propose_collective_pack([_to_instance(i) for i in req.instances])
    except FloatingDeepResearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return intent.to_dict()


def register_floating_deep_research_routes(app: FastAPI) -> None:
    app.include_router(floating_deep_research_router)


__all__ = [
    "floating_deep_research_router",
    "register_floating_deep_research_routes",
]

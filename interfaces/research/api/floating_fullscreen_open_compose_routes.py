"""Registerable HTTP surface for floating fullscreen open compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_fullscreen_open_compose import (
    FloatingFullscreenOpenComposeError,
    compose_floating_fullscreen_open,
)

floating_fullscreen_open_compose_router = APIRouter(
    prefix="/research/floating-fullscreen-open",
    tags=["floating-fullscreen-open-compose"],
)


class InstanceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    prompt: str = Field(min_length=1, max_length=8000)
    view_mode: Literal[
        "floating", "fullscreen", "merged_draft", "merged_full", "collective"
    ] = "floating"
    status: Literal["proposed", "open", "completed", "closed"] = "open"
    live_dispatched: Literal[False] = False
    merge_executed: Literal[False] = False
    notes: list[str] = Field(default_factory=list)
    authority: str = "operator_spawn_only"


class TraySiblingBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    highlight: str | None = Field(default=None, max_length=8000)
    view_mode: str | None = Field(default=None, max_length=64)
    live_dispatched: Literal[False] | None = None
    merge_executed: Literal[False] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    operator_ack: bool = Field(strict=True)
    existing_instance: InstanceBody | None = None
    highlight: str | None = Field(default=None, max_length=8000)
    prompt: str | None = Field(default=None, max_length=8000)
    gated: bool | None = Field(default=None, strict=True)
    tray_siblings: list[TraySiblingBody] | None = None


@floating_fullscreen_open_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_fullscreen_open(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            operator_ack=req.operator_ack,
            existing_instance=(
                req.existing_instance.model_dump()
                if req.existing_instance is not None
                else None
            ),
            highlight=req.highlight,
            prompt=req.prompt,
            gated=req.gated,
            tray_siblings=(
                [s.model_dump() for s in req.tray_siblings]
                if req.tray_siblings is not None
                else None
            ),
        )
    except FloatingFullscreenOpenComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_fullscreen_open_compose_routes(app: FastAPI) -> None:
    app.include_router(floating_fullscreen_open_compose_router)


__all__ = [
    "floating_fullscreen_open_compose_router",
    "register_floating_fullscreen_open_compose_routes",
]

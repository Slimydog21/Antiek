"""Registerable HTTP surface for fullscreen + draft collective presented twins."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_collective_presented_twins_compose_routes import (
    CollectivePackBody,
    DraftGateBody,
)
from interfaces.research.api.floating_fullscreen_open_compose_routes import (
    InstanceBody,
    TraySiblingBody,
)
from substrate.fullscreen_draft_collective_presented_twins_compose import (
    FullscreenDraftCollectivePresentedTwinsComposeError,
    compose_fullscreen_draft_collective_presented_twins,
)

fullscreen_draft_collective_presented_twins_compose_router = APIRouter(
    prefix="/research/fullscreen-draft-collective-presented-twins",
    tags=["fullscreen-draft-collective-presented-twins-compose"],
)


class FullscreenBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    existing_instance: InstanceBody | None = None
    highlight: str | None = Field(default=None, max_length=8000)
    prompt: str | None = Field(default=None, max_length=8000)
    gated: bool | None = Field(default=None, strict=True)
    tray_siblings: list[TraySiblingBody] | None = None


class DraftCollectiveBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    collective_pack: CollectivePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    draft_collective: DraftCollectiveBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@fullscreen_draft_collective_presented_twins_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_fullscreen_draft_collective_presented_twins(
            fullscreen=req.fullscreen.model_dump(),
            draft_collective=req.draft_collective.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FullscreenDraftCollectivePresentedTwinsComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_fullscreen_draft_collective_presented_twins_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        fullscreen_draft_collective_presented_twins_compose_router
    )


__all__ = [
    "fullscreen_draft_collective_presented_twins_compose_router",
    "register_fullscreen_draft_collective_presented_twins_compose_routes",
]

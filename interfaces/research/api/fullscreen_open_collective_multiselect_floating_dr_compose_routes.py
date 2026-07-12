"""Registerable HTTP surface for fullscreen-open over collective multiselect floating DR."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.collective_multiselect_floating_dr_draft_before_merge_compose_routes import (
    FloatingDrPackBody,
    MultiselectBody,
)
from interfaces.research.api.floating_fullscreen_open_compose_routes import (
    InstanceBody,
    TraySiblingBody,
)
from substrate.fullscreen_open_collective_multiselect_floating_dr_compose import (
    FullscreenOpenCollectiveMultiselectFloatingDrComposeError,
    compose_fullscreen_open_collective_multiselect_floating_dr,
)

fullscreen_open_collective_multiselect_floating_dr_compose_router = APIRouter(
    prefix="/research/fullscreen-open-collective-multiselect-floating-dr",
    tags=["fullscreen-open-collective-multiselect-floating-dr-compose"],
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


class CollectivePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiselectBody
    floating_dr_pack: FloatingDrPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    collective_pack: CollectivePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@fullscreen_open_collective_multiselect_floating_dr_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_fullscreen_open_collective_multiselect_floating_dr(
            fullscreen=req.fullscreen.model_dump(),
            collective_pack=req.collective_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FullscreenOpenCollectiveMultiselectFloatingDrComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_fullscreen_open_collective_multiselect_floating_dr_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        fullscreen_open_collective_multiselect_floating_dr_compose_router
    )


__all__ = [
    "fullscreen_open_collective_multiselect_floating_dr_compose_router",
    "register_fullscreen_open_collective_multiselect_floating_dr_compose_routes",
]

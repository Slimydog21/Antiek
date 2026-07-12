"""Registerable HTTP surface for recursive twin presentation + write twin collective MO."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_routes import (
    FullscreenPackBody,
    WriteBody,
)
from substrate.recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose import (
    RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError,
    compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin,
)

recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_router = (
    APIRouter(
        prefix=(
            "/research/recursive-twin-presentation-write-twin-collective-fullscreen-mo-nd-twin"
        ),
        tags=[
            "recursive-twin-presentation-write-twin-collective-fullscreen-mo-nd-twin-compose"
        ],
    )
)

ViewMode = Literal["side_panel", "overlay", "fullscreen_twin", "inline"]


class TwinBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=50000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None


class PresentationBody(BaseModel):
    model_config = {"extra": "forbid"}

    view_mode: ViewMode
    open_requested: bool = Field(strict=True)
    merge_to_parent_preview: bool | None = Field(default=None, strict=True)
    presented_insights: list[str] | None = None
    presented_questions: list[str] | None = None


class WritePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    fullscreen_pack: FullscreenPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    presentation: PresentationBody
    write_pack: WritePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
            twin=req.twin.model_dump(),
            presentation=req.presentation.model_dump(),
            write_pack=req.write_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_router
    )


__all__ = [
    "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_router",
    "register_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_routes",
]

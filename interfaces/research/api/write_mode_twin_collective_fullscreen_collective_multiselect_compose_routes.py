"""Registerable HTTP surface for write twin collective over fullscreen collective multiselect."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fullscreen_open_collective_multiselect_floating_dr_compose_routes import (
    CollectivePackBody,
    FullscreenBody,
)
from interfaces.research.api.write_mode_twin_collective_analysis_compose_routes import (
    SlotBody,
    TwinSliceBody,
)
from substrate.write_mode_twin_collective_fullscreen_collective_multiselect_compose import (
    WriteModeTwinCollectiveFullscreenCollectiveMultiselectComposeError,
    compose_write_mode_twin_collective_fullscreen_collective_multiselect,
)

write_mode_twin_collective_fullscreen_collective_multiselect_compose_router = (
    APIRouter(
        prefix=(
            "/research/write-mode-twin-collective-fullscreen-collective-multiselect"
        ),
        tags=[
            "write-mode-twin-collective-fullscreen-collective-multiselect-compose"
        ],
    )
)


class WriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_slices: list[TwinSliceBody] = Field(min_length=1)
    chase_slots: list[SlotBody] = Field(min_length=2)
    analysis_kind: Literal["draft_analysis", "full_analysis"]
    base_draft_html: str | None = Field(default=None, max_length=100000)
    extra_findings: list[str] | None = None
    require_both: bool | None = Field(default=None, strict=True)


class FullscreenPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    collective_pack: CollectivePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    fullscreen_pack: FullscreenPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@write_mode_twin_collective_fullscreen_collective_multiselect_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = (
            compose_write_mode_twin_collective_fullscreen_collective_multiselect(
                write=req.write.model_dump(),
                fullscreen_pack=req.fullscreen_pack.model_dump(),
                operator_ack=req.operator_ack,
                require_both=req.require_both,
            )
        )
    except WriteModeTwinCollectiveFullscreenCollectiveMultiselectComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_mode_twin_collective_fullscreen_collective_multiselect_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        write_mode_twin_collective_fullscreen_collective_multiselect_compose_router
    )


__all__ = [
    "write_mode_twin_collective_fullscreen_collective_multiselect_compose_router",
    "register_write_mode_twin_collective_fullscreen_collective_multiselect_compose_routes",
]

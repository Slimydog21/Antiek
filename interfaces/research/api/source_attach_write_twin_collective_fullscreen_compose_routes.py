"""Registerable HTTP surface for HTML-native source attach over write twin collective fullscreen."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_source_attach_compose_routes import (
    SourceBody,
)
from interfaces.research.api.write_mode_twin_collective_fullscreen_collective_multiselect_compose_routes import (
    FullscreenPackBody,
    WriteBody,
)
from substrate.source_attach_write_twin_collective_fullscreen_compose import (
    SourceAttachWriteTwinCollectiveFullscreenComposeError,
    compose_source_attach_write_twin_collective_fullscreen,
)

source_attach_write_twin_collective_fullscreen_compose_router = APIRouter(
    prefix="/research/source-attach-write-twin-collective-fullscreen",
    tags=["source-attach-write-twin-collective-fullscreen-compose"],
)


class SourcesBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] = Field(min_length=1)
    sources: list[SourceBody]


class WritePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    fullscreen_pack: FullscreenPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    write_pack: WritePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@source_attach_write_twin_collective_fullscreen_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_attach_write_twin_collective_fullscreen(
            sources=req.sources.model_dump(),
            write_pack=req.write_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SourceAttachWriteTwinCollectiveFullscreenComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_attach_write_twin_collective_fullscreen_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        source_attach_write_twin_collective_fullscreen_compose_router
    )


__all__ = [
    "source_attach_write_twin_collective_fullscreen_compose_router",
    "register_source_attach_write_twin_collective_fullscreen_compose_routes",
]

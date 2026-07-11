"""Registerable HTTP surface for source publication registry (selection only)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.source_publication_registry import (
    SourcePublicationRegistryError,
    select_publication_sources,
)

source_publication_registry_router = APIRouter(
    prefix="/research/source-publication-registry",
    tags=["source-publication-registry"],
)


class CustomSourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    family: Literal["custom"] = "custom"
    label: str = Field(min_length=1, max_length=512)
    host: str | None = Field(default=None, max_length=512)
    enabled: bool = Field(strict=True)


class SelectRequest(BaseModel):
    model_config = {"extra": "forbid"}

    requested_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] = Field(min_length=1)
    custom_sources: list[CustomSourceBody] | None = None
    enabled_only: bool = Field(default=True, strict=True)


@source_publication_registry_router.post("/select")
def post_select(req: SelectRequest) -> dict[str, Any]:
    try:
        pack = select_publication_sources(
            requested_families=list(req.requested_families),
            custom_sources=(
                [c.model_dump() for c in req.custom_sources]
                if req.custom_sources is not None
                else None
            ),
            enabled_only=req.enabled_only,
        )
    except SourcePublicationRegistryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return pack.to_dict()


def register_source_publication_registry_routes(app: FastAPI) -> None:
    app.include_router(source_publication_registry_router)


__all__ = [
    "register_source_publication_registry_routes",
    "source_publication_registry_router",
]

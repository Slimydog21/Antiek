"""Registerable HTTP surface for deep-research source packs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_sources.source_pack import SourcePackError, build_source_pack

source_pack_router = APIRouter(
    prefix="/research/source-pack",
    tags=["source-pack"],
)


class SourcePackRequest(BaseModel):
    model_config = {"extra": "forbid"}

    selected: list[str] = Field(min_length=1)
    readiness_by_source: dict[str, dict[str, Any]] | None = None


@source_pack_router.post("/build")
def post_source_pack(req: SourcePackRequest) -> dict[str, Any]:
    try:
        pack = build_source_pack(req.selected, req.readiness_by_source)
    except SourcePackError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return pack.to_dict()


def register_source_pack_routes(app: FastAPI) -> None:
    app.include_router(source_pack_router)


__all__ = ["register_source_pack_routes", "source_pack_router"]

"""Registerable HTTP surface for twin intelligent search (pure substrate)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    search_twin_substrate,
)

recursive_twin_intelligent_search_router = APIRouter(
    prefix="/twins/intelligent-search",
    tags=["twin-intelligent-search"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, max_length=512)


class SearchRequest(BaseModel):
    model_config = {"extra": "forbid"}

    query: str = Field(min_length=1, max_length=2000)
    records: list[TwinRecordBody] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=500)


@recursive_twin_intelligent_search_router.post("/search")
def post_search(req: SearchRequest) -> dict[str, Any]:
    try:
        result = search_twin_substrate(
            query=req.query,
            records=[r.model_dump() for r in req.records],
            limit=req.limit,
        )
    except TwinIntelligentSearchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_intelligent_search_routes(app: FastAPI) -> None:
    app.include_router(recursive_twin_intelligent_search_router)


__all__ = [
    "recursive_twin_intelligent_search_router",
    "register_recursive_twin_intelligent_search_routes",
]

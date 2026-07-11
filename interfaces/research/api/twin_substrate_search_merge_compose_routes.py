"""Registerable HTTP surface for twin substrate search → merge compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_substrate_search_merge_compose import (
    TwinSubstrateSearchMergeComposeError,
    compose_twin_substrate_search_merge,
)

twin_substrate_search_merge_compose_router = APIRouter(
    prefix="/research/twin-substrate-search-merge",
    tags=["twin-substrate-search-merge-compose"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, max_length=512)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    pack_id: str = Field(min_length=1, max_length=256)
    search_query: str = Field(min_length=1, max_length=2000)
    twin_records: list[TwinRecordBody]
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1)
    min_parents_for_merge: int | None = Field(default=None, ge=2)


@twin_substrate_search_merge_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_substrate_search_merge(
            pack_id=req.pack_id,
            search_query=req.search_query,
            twin_records=[t.model_dump() for t in req.twin_records],
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            min_parents_for_merge=req.min_parents_for_merge,
        )
    except TwinSubstrateSearchMergeComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_substrate_search_merge_compose_routes(app: FastAPI) -> None:
    app.include_router(twin_substrate_search_merge_compose_router)


__all__ = [
    "twin_substrate_search_merge_compose_router",
    "register_twin_substrate_search_merge_compose_routes",
]

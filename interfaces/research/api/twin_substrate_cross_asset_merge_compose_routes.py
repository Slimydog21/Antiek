"""Registerable HTTP surface for twin substrate cross-asset merge compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_substrate_cross_asset_merge_compose import (
    TwinSubstrateCrossAssetMergeComposeError,
    compose_twin_substrate_cross_asset_merge,
)

twin_substrate_cross_asset_merge_compose_router = APIRouter(
    prefix="/research/twin-cross-asset-merge",
    tags=["twin-substrate-cross-asset-merge-compose"],
)


class SliceBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_asset_id: str | None = Field(default=None, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    pack_id: str = Field(min_length=1, max_length=256)
    slices: list[SliceBody] = Field(min_length=2)
    operator_ack: bool = Field(strict=True)


@twin_substrate_cross_asset_merge_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_substrate_cross_asset_merge(
            pack_id=req.pack_id,
            slices=[s.model_dump() for s in req.slices],
            operator_ack=req.operator_ack,
        )
    except TwinSubstrateCrossAssetMergeComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_substrate_cross_asset_merge_compose_routes(app: FastAPI) -> None:
    app.include_router(twin_substrate_cross_asset_merge_compose_router)


__all__ = [
    "twin_substrate_cross_asset_merge_compose_router",
    "register_twin_substrate_cross_asset_merge_compose_routes",
]

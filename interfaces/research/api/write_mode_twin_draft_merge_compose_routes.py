"""Registerable HTTP surface for write-mode twin draft merge compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.write_mode_twin_draft_merge_compose import (
    WriteModeTwinDraftMergeComposeError,
    compose_write_mode_twin_draft_merge,
)

write_mode_twin_draft_merge_compose_router = APIRouter(
    prefix="/research/write-twin-draft",
    tags=["write-mode-twin-draft-merge-compose"],
)


class SliceBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    draft_id: str = Field(min_length=1, max_length=256)
    base_draft_html: str | None = Field(default=None, max_length=500_000)
    slices: list[SliceBody] = Field(min_length=1)
    operator_ack: bool = Field(strict=True)


@write_mode_twin_draft_merge_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_write_mode_twin_draft_merge(
            draft_id=req.draft_id,
            base_draft_html=req.base_draft_html,
            slices=[s.model_dump() for s in req.slices],
            operator_ack=req.operator_ack,
        )
    except WriteModeTwinDraftMergeComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_mode_twin_draft_merge_compose_routes(app: FastAPI) -> None:
    app.include_router(write_mode_twin_draft_merge_compose_router)


__all__ = [
    "write_mode_twin_draft_merge_compose_router",
    "register_write_mode_twin_draft_merge_compose_routes",
]

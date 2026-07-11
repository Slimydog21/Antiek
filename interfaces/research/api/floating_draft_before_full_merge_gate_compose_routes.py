"""Registerable HTTP surface for floating draft-before-full-merge gate."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
)

floating_draft_before_full_merge_gate_compose_router = APIRouter(
    prefix="/research/floating-draft-before-full-merge-gate",
    tags=["floating-draft-before-full-merge-gate-compose"],
)


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    highlight: str | None = Field(default=None, max_length=8000)
    findings: list[str] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    sources: list[SourceBody] = Field(min_length=1)
    stage: Literal["draft_only", "promote_full_merge"]
    operator_ack: bool = Field(strict=True)
    parent_excerpt: str | None = Field(default=None, max_length=50000)
    full_merge_ack: bool | None = Field(default=None, strict=True)


@floating_draft_before_full_merge_gate_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_draft_before_full_merge_gate(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            sources=[s.model_dump() for s in req.sources],
            stage=req.stage,
            operator_ack=req.operator_ack,
            parent_excerpt=req.parent_excerpt,
            full_merge_ack=req.full_merge_ack,
        )
    except FloatingDraftBeforeFullMergeGateComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_draft_before_full_merge_gate_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(floating_draft_before_full_merge_gate_compose_router)


__all__ = [
    "floating_draft_before_full_merge_gate_compose_router",
    "register_floating_draft_before_full_merge_gate_compose_routes",
]

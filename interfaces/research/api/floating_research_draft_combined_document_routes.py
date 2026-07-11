"""Registerable HTTP surface for floating research provisional draft combine."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_research_draft_combined_document import (
    FloatingResearchDraftCombinedDocumentError,
    compose_floating_research_draft_combined_document,
)

floating_research_draft_combined_document_router = APIRouter(
    prefix="/research/floating-draft-combined",
    tags=["floating-research-draft-combined-document"],
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

    parent_asset_id: str = Field(min_length=1, max_length=256)
    parent_excerpt: str | None = Field(default=None, max_length=100_000)
    sources: list[SourceBody] = Field(min_length=1)
    operator_ack: bool = Field(strict=True)


@floating_research_draft_combined_document_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        draft = compose_floating_research_draft_combined_document(
            parent_asset_id=req.parent_asset_id,
            parent_excerpt=req.parent_excerpt,
            sources=[s.model_dump() for s in req.sources],
            operator_ack=req.operator_ack,
        )
    except FloatingResearchDraftCombinedDocumentError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return draft.to_dict()


def register_floating_research_draft_combined_document_routes(
    app: FastAPI,
) -> None:
    app.include_router(floating_research_draft_combined_document_router)


__all__ = [
    "floating_research_draft_combined_document_router",
    "register_floating_research_draft_combined_document_routes",
]

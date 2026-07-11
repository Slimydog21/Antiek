"""Registerable HTTP surface for source publication DR attach quality pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.source_publication_dr_attach_quality_compose import (
    SourcePublicationDrAttachQualityComposeError,
    compose_source_publication_dr_attach_quality,
)

source_publication_dr_attach_quality_compose_router = APIRouter(
    prefix="/research/source-publication-dr-attach-quality",
    tags=["source-publication-dr-attach-quality-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)
    html_fragment: str | None = Field(default=None, max_length=100000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)
    year: int | None = None
    authors: str | None = Field(default=None, max_length=2000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_ack: bool = Field(strict=True)
    citations: list[CitationBody] | None = None
    derive_citations_from_sources: bool = Field(default=True, strict=True)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)


@source_publication_dr_attach_quality_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_publication_dr_attach_quality(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            requested_families=list(req.requested_families),
            sources=[s.model_dump() for s in req.sources],
            quality_overall=req.quality_overall,
            would_exceed=req.would_exceed,
            operator_ack=req.operator_ack,
            citations=(
                [c.model_dump() for c in req.citations]
                if req.citations is not None
                else None
            ),
            derive_citations_from_sources=req.derive_citations_from_sources,
            quality_floor=req.quality_floor,
            operator_override=req.operator_override,
        )
    except SourcePublicationDrAttachQualityComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_publication_dr_attach_quality_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(source_publication_dr_attach_quality_compose_router)


__all__ = [
    "source_publication_dr_attach_quality_compose_router",
    "register_source_publication_dr_attach_quality_compose_routes",
]

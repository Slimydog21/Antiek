"""Registerable HTTP surface for deep research source citation pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.deep_research_source_citation_pack import (
    DeepResearchSourceCitationPackError,
    build_deep_research_source_citation_pack,
)

deep_research_source_citation_pack_router = APIRouter(
    prefix="/research/source-citation-pack",
    tags=["deep-research-source-citation-pack"],
)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: Literal["arxiv", "substack", "openalex", "web", "custom"]
    title: str = Field(min_length=1, max_length=4000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)
    year: int | None = Field(default=None, ge=1000, le=3000)
    authors: str | None = Field(default=None, max_length=2000)


class BuildRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    requested_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] = Field(min_length=1)
    citations: list[CitationBody] = Field(default_factory=list)
    filter_to_selected_families: bool = True


@deep_research_source_citation_pack_router.post("/build")
def post_build(req: BuildRequest) -> dict[str, Any]:
    try:
        pack = build_deep_research_source_citation_pack(
            session_id=req.session_id,
            requested_families=req.requested_families,
            citations=[c.model_dump() for c in req.citations],
            filter_to_selected_families=req.filter_to_selected_families,
        )
    except DeepResearchSourceCitationPackError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return pack.to_dict()


def register_deep_research_source_citation_pack_routes(app: FastAPI) -> None:
    app.include_router(deep_research_source_citation_pack_router)


__all__ = [
    "deep_research_source_citation_pack_router",
    "register_deep_research_source_citation_pack_routes",
]

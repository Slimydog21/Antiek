"""Registerable HTTP surface for reading↔research HTML parity compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.reading_research_html_parity_compose import (
    ReadingResearchHtmlParityComposeError,
    compose_reading_research_html_parity,
)

reading_research_html_parity_compose_router = APIRouter(
    prefix="/assets/reading-research-html-parity",
    tags=["reading-research-html-parity-compose"],
)


class ModeAssetBody(BaseModel):
    model_config = {"extra": "forbid"}

    asset_id: str = Field(min_length=1, max_length=256)
    asset_kind: Literal["book", "research", "twin", "analysis", "paper", "other"]
    source_format: Literal["html", "pdf", "epub", "markdown", "unknown"]
    html_projection_sha: str | None = Field(default=None, max_length=128)
    prefer_html: bool = True
    allow_pdf_secondary: bool = True


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    reading: ModeAssetBody
    research: ModeAssetBody


@reading_research_html_parity_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        snap = compose_reading_research_html_parity(
            reading=req.reading.model_dump(),
            research=req.research.model_dump(),
        )
    except ReadingResearchHtmlParityComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return snap.to_dict()


def register_reading_research_html_parity_compose_routes(app: FastAPI) -> None:
    app.include_router(reading_research_html_parity_compose_router)


__all__ = [
    "reading_research_html_parity_compose_router",
    "register_reading_research_html_parity_compose_routes",
]

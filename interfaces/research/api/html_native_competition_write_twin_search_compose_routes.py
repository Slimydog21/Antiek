"""Registerable HTTP surface for HTML-native competition write twin search."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.html_native_competition_write_twin_search_compose import (
    HtmlNativeCompetitionWriteTwinSearchComposeError,
    compose_html_native_competition_write_twin_search,
)

html_native_competition_write_twin_search_compose_router = APIRouter(
    prefix="/research/html-native-competition-write-twin-search",
    tags=["html-native-competition-write-twin-search-compose"],
)

Area = Literal[
    "source_acquisition",
    "citation_grounding",
    "multi_agent_orchestration",
    "budget_controls",
    "html_native_reading",
    "model_routing",
    "evaluation_harness",
    "unattended_swarm",
]
Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    competitor: str = Field(min_length=1, max_length=256)
    area: Area
    decision_summary: str = Field(min_length=1, max_length=4000)
    antiek_status: Literal["ahead", "parity", "behind", "unknown"]
    residual: str | None = Field(default=None, max_length=4000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)


class CompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody] = Field(min_length=1)
    requested_families: list[Family] = Field(min_length=1)
    citations: list[CitationBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    search_query: str = Field(min_length=1, max_length=2000)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    require_no_behind_gaps: bool = Field(default=False, strict=True)
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    require_both_with_write: bool = Field(default=True, strict=True)
    require_both_with_search: bool = Field(default=True, strict=True)


class ModeBody(BaseModel):
    model_config = {"extra": "forbid"}

    asset_id: str = Field(min_length=1, max_length=256)
    asset_kind: Literal[
        "book", "research", "twin", "analysis", "paper", "other"
    ]
    source_format: Literal["html", "pdf", "epub", "markdown", "unknown"]
    html_projection_sha: str | None = Field(default=None, max_length=128)
    prefer_html: bool = Field(default=True, strict=True)
    allow_pdf_secondary: bool = Field(default=False, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=128)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    operator_ack: bool = Field(strict=True)
    competition: CompetitionBody
    twin_substrate_ready: bool | None = Field(default=None, strict=True)
    claimed_format: str | None = Field(default=None, max_length=64)
    reading: ModeBody | None = None
    research: ModeBody | None = None
    require_both: bool = Field(default=True, strict=True)


@html_native_competition_write_twin_search_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_competition_write_twin_search(
            session_id=req.session_id,
            asset_id=req.asset_id,
            html_projection_sha=req.html_projection_sha,
            view_requested=req.view_requested,
            twin_bound=req.twin_bound,
            operator_ack=req.operator_ack,
            competition=req.competition.model_dump(),
            twin_substrate_ready=req.twin_substrate_ready,
            claimed_format=req.claimed_format,
            reading=req.reading.model_dump() if req.reading else None,
            research=req.research.model_dump() if req.research else None,
            require_both=req.require_both,
        )
    except HtmlNativeCompetitionWriteTwinSearchComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_competition_write_twin_search_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        html_native_competition_write_twin_search_compose_router
    )


__all__ = [
    "html_native_competition_write_twin_search_compose_router",
    "register_html_native_competition_write_twin_search_compose_routes",
]

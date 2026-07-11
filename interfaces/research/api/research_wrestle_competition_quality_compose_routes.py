"""Registerable HTTP surface for research wrestle + competition quality compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_wrestle_competition_quality_compose import (
    ResearchWrestleCompetitionQualityComposeError,
    compose_research_wrestle_competition_quality,
)

research_wrestle_competition_quality_compose_router = APIRouter(
    prefix="/research/wrestle-competition-quality",
    tags=["research-wrestle-competition-quality-compose"],
)

DecisionArea = Literal[
    "source_acquisition",
    "citation_grounding",
    "multi_agent_orchestration",
    "budget_controls",
    "html_native_reading",
    "model_routing",
    "evaluation_harness",
    "unattended_swarm",
]
GapStatus = Literal["ahead", "parity", "behind", "unknown"]
CitationFamily = Literal["arxiv", "substack", "openalex", "web", "custom"]


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    competitor: str = Field(min_length=1, max_length=256)
    area: DecisionArea
    decision_summary: str = Field(min_length=1, max_length=4000)
    antiek_status: GapStatus
    residual: str | None = Field(default=None, max_length=2000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: CitationFamily
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=256)
    url: str | None = Field(default=None, max_length=2000)
    year: int | None = None
    authors: str | None = Field(default=None, max_length=2000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    floating_instance_count: int = Field(ge=0)
    completed_floating_count: int = Field(ge=0)
    twin_insight_count: int = Field(ge=0)
    twin_question_count: int = Field(ge=0)
    open_question_count: int = Field(ge=0)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    competitor_decisions: list[DecisionBody]
    focus_areas: list[DecisionArea] | None = None
    requested_families: list[CitationFamily] = Field(min_length=1)
    citations: list[CitationBody]
    filter_to_selected_families: bool = Field(default=True, strict=True)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    require_no_behind_gaps: bool = Field(default=False, strict=True)
    operator_ack: bool = Field(strict=True)


@research_wrestle_competition_quality_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_research_wrestle_competition_quality(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            floating_instance_count=req.floating_instance_count,
            completed_floating_count=req.completed_floating_count,
            twin_insight_count=req.twin_insight_count,
            twin_question_count=req.twin_question_count,
            open_question_count=req.open_question_count,
            preferred_view_mode=req.preferred_view_mode,
            competitor_decisions=[d.model_dump() for d in req.competitor_decisions],
            focus_areas=req.focus_areas,
            requested_families=list(req.requested_families),
            citations=[c.model_dump() for c in req.citations],
            filter_to_selected_families=req.filter_to_selected_families,
            quality_overall=req.quality_overall,
            quality_floor=req.quality_floor,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            require_no_behind_gaps=req.require_no_behind_gaps,
            operator_ack=req.operator_ack,
        )
    except ResearchWrestleCompetitionQualityComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_research_wrestle_competition_quality_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(research_wrestle_competition_quality_compose_router)


__all__ = [
    "research_wrestle_competition_quality_compose_router",
    "register_research_wrestle_competition_quality_compose_routes",
]

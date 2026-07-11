"""Registerable HTTP surface for competition DR quality + source pack compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)

competition_dr_quality_source_pack_compose_router = APIRouter(
    prefix="/research/competition-dr-quality-source-pack",
    tags=["competition-dr-quality-source-pack-compose"],
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
    competitor_decisions: list[DecisionBody]
    focus_areas: list[DecisionArea] | None = None
    requested_families: list[CitationFamily] = Field(min_length=1)
    citations: list[CitationBody]
    filter_to_selected_families: bool = Field(default=True, strict=True)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    operator_ack: bool = Field(strict=True)
    require_no_behind_gaps: bool = Field(default=False, strict=True)


@competition_dr_quality_source_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_quality_source_pack(
            session_id=req.session_id,
            competitor_decisions=[d.model_dump() for d in req.competitor_decisions],
            focus_areas=req.focus_areas,
            requested_families=list(req.requested_families),
            citations=[c.model_dump() for c in req.citations],
            filter_to_selected_families=req.filter_to_selected_families,
            quality_overall=req.quality_overall,
            quality_floor=req.quality_floor,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            operator_ack=req.operator_ack,
            require_no_behind_gaps=req.require_no_behind_gaps,
        )
    except CompetitionDrQualitySourcePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_quality_source_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(competition_dr_quality_source_pack_compose_router)


__all__ = [
    "competition_dr_quality_source_pack_compose_router",
    "register_competition_dr_quality_source_pack_compose_routes",
]

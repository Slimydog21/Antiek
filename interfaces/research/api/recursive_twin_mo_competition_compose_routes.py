"""Registerable HTTP surface for recursive twin + MO competition pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.recursive_twin_mo_competition_compose import (
    RecursiveTwinMoCompetitionComposeError,
    compose_recursive_twin_mo_competition,
)

recursive_twin_mo_competition_compose_router = APIRouter(
    prefix="/research/recursive-twin-mo-competition",
    tags=["recursive-twin-mo-competition-compose"],
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


class MoGoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: int = Field(ge=1, le=24 * 60)
    goals: list[MoGoalBody] = Field(min_length=1)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)
    usd_per_hour: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)


class ModelOptionBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelOptionBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)


class CompDecisionBody(BaseModel):
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
    competitor_decisions: list[CompDecisionBody] = Field(min_length=1)
    requested_families: list[Family] = Field(min_length=1)
    citations: list[CitationBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    search_query: str = Field(min_length=1, max_length=2000)


class CompetitionViewBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=128)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    competition: CompetitionBody
    claimed_format: str | None = Field(default=None, max_length=64)


class ResearchBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    competition_view: CompetitionViewBody


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    mo: MoBody
    research: ResearchBody
    operator_ack: bool = Field(strict=True)
    source_excerpt: str | None = Field(default=None, max_length=100000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None
    require_both_with_twin: bool = Field(default=True, strict=True)


@recursive_twin_mo_competition_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_mo_competition(
            parent_asset_id=req.parent_asset_id,
            mo=req.mo.model_dump(),
            research=req.research.model_dump(),
            operator_ack=req.operator_ack,
            source_excerpt=req.source_excerpt,
            existing_twin_asset_id=req.existing_twin_asset_id,
            focus_questions=req.focus_questions,
            require_both_with_twin=req.require_both_with_twin,
        )
    except RecursiveTwinMoCompetitionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_mo_competition_compose_routes(app: FastAPI) -> None:
    app.include_router(recursive_twin_mo_competition_compose_router)


__all__ = [
    "recursive_twin_mo_competition_compose_router",
    "register_recursive_twin_mo_competition_compose_routes",
]

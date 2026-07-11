"""Registerable HTTP surface for competition quality + interrogation loop."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.competition_quality_interrogation_loop_compose import (
    CompetitionQualityInterrogationLoopComposeError,
    compose_competition_quality_interrogation_loop,
)

competition_quality_interrogation_loop_compose_router = APIRouter(
    prefix="/research/competition-quality-interrogation-loop",
    tags=["competition-quality-interrogation-loop-compose"],
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
Status = Literal["ahead", "parity", "behind", "unknown"]
Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    competitor: str = Field(min_length=1, max_length=256)
    area: Area
    decision_summary: str = Field(min_length=1, max_length=4000)
    antiek_status: Status
    residual: str | None = Field(default=None, max_length=2000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)


class QuestionBody(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    priority: int | None = None


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class RecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal["insight", "question", "data", "claim"]
    body: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = Field(default=None, max_length=256)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody]
    requested_families: list[Family] = Field(min_length=1)
    citations: list[CitationBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    questions: list[QuestionBody] = Field(min_length=1)
    chase_mode: Literal[
        "single_question", "swarm_fanout", "collective_merge_after"
    ]
    user_prompt: str = Field(min_length=1, max_length=8000)
    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    require_no_behind_gaps: bool | None = Field(default=None, strict=True)
    prior_records: list[RecordBody] | None = None
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    operator_override: bool | None = Field(default=None, strict=True)
    source_families: list[Family] | None = None
    focus_task: str | None = Field(default=None, max_length=256)


@competition_quality_interrogation_loop_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_quality_interrogation_loop(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            competitor_decisions=[d.model_dump() for d in req.competitor_decisions],
            requested_families=list(req.requested_families),
            citations=[c.model_dump() for c in req.citations],
            quality_overall=req.quality_overall,
            would_exceed=req.would_exceed,
            questions=[q.model_dump() for q in req.questions],
            chase_mode=req.chase_mode,
            user_prompt=req.user_prompt,
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            operator_ack=req.operator_ack,
            quality_floor=req.quality_floor,
            require_no_behind_gaps=req.require_no_behind_gaps,
            prior_records=(
                [r.model_dump() for r in req.prior_records]
                if req.prior_records is not None
                else None
            ),
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            operator_override=req.operator_override,
            source_families=req.source_families,
            focus_task=req.focus_task,
        )
    except CompetitionQualityInterrogationLoopComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_quality_interrogation_loop_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(competition_quality_interrogation_loop_compose_router)


__all__ = [
    "competition_quality_interrogation_loop_compose_router",
    "register_competition_quality_interrogation_loop_compose_routes",
]

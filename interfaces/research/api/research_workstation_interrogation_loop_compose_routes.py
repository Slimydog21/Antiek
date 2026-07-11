"""Registerable HTTP surface for research workstation interrogation loop."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_workstation_interrogation_loop_compose import (
    ResearchWorkstationInterrogationLoopComposeError,
    compose_research_workstation_interrogation_loop,
)

research_workstation_interrogation_loop_compose_router = APIRouter(
    prefix="/research/workstation-interrogation-loop",
    tags=["research-workstation-interrogation-loop-compose"],
)


class QuestionBody(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    priority: int | None = None


class RecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal["insight", "question", "data", "claim"]
    body: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = Field(default=None, max_length=256)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
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
    prior_records: list[RecordBody] | None = None
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    would_exceed: bool | None = None
    operator_override: bool | None = Field(default=None, strict=True)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None
    mark_for_twin_record: bool | None = Field(default=None, strict=True)
    focus_task: str | None = Field(default=None, max_length=256)


@research_workstation_interrogation_loop_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_research_workstation_interrogation_loop(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            questions=[q.model_dump() for q in req.questions],
            chase_mode=req.chase_mode,
            user_prompt=req.user_prompt,
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            operator_ack=req.operator_ack,
            prior_records=(
                [r.model_dump() for r in req.prior_records]
                if req.prior_records is not None
                else None
            ),
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            source_families=req.source_families,
            mark_for_twin_record=req.mark_for_twin_record,
            focus_task=req.focus_task,
        )
    except ResearchWorkstationInterrogationLoopComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_research_workstation_interrogation_loop_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(research_workstation_interrogation_loop_compose_router)


__all__ = [
    "research_workstation_interrogation_loop_compose_router",
    "register_research_workstation_interrogation_loop_compose_routes",
]

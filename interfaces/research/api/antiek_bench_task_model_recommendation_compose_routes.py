"""Registerable HTTP surface for Antiek-bench task model recommendation."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.antiek_bench_task_model_recommendation_compose import (
    AntiekBenchTaskModelRecommendationComposeError,
    compose_antiek_bench_task_model_recommendation,
)

antiek_bench_task_model_recommendation_compose_router = APIRouter(
    prefix="/research/antiek-bench-task-model-recommendation",
    tags=["antiek-bench-task-model-recommendation-compose"],
)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class EventBody(BaseModel):
    model_config = {"extra": "forbid"}

    event_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=256)
    outcome: Literal["worked", "failed", "mixed", "unknown"]
    score: float | None = Field(default=None, ge=0, le=1)


class TaskSeedBody(BaseModel):
    model_config = {"extra": "forbid"}

    task: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    focus_task: str = Field(min_length=1, max_length=256)
    events: list[EventBody]
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    selected_model_id: str | None = Field(default=None, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    existing_tasks: list[str] | None = None
    proposed_new_tasks: list[TaskSeedBody] | None = None
    min_events_per_task: int | None = Field(default=None, ge=1)
    min_events_for_recommendation: int | None = Field(default=None, ge=1)


@antiek_bench_task_model_recommendation_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_task_model_recommendation(
            week_id=req.week_id,
            focus_task=req.focus_task,
            events=[e.model_dump() for e in req.events],
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            operator_ack=req.operator_ack,
            selected_model_id=req.selected_model_id,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            existing_tasks=req.existing_tasks,
            proposed_new_tasks=(
                [t.model_dump() for t in req.proposed_new_tasks]
                if req.proposed_new_tasks is not None
                else None
            ),
            min_events_per_task=req.min_events_per_task,
            min_events_for_recommendation=req.min_events_for_recommendation,
        )
    except AntiekBenchTaskModelRecommendationComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_task_model_recommendation_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(antiek_bench_task_model_recommendation_compose_router)


__all__ = [
    "antiek_bench_task_model_recommendation_compose_router",
    "register_antiek_bench_task_model_recommendation_compose_routes",
]

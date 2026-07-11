"""Registerable HTTP surface for NotDiamond + bench decision shadow pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.notdiamond_bench_decision_shadow_compose import (
    NotDiamondBenchDecisionShadowComposeError,
    compose_notdiamond_bench_decision_shadow,
)

notdiamond_bench_decision_shadow_compose_router = APIRouter(
    prefix="/research/notdiamond-bench-decision-shadow",
    tags=["notdiamond-bench-decision-shadow-compose"],
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


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    focus_task: str = Field(min_length=1, max_length=256)
    events: list[EventBody]
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    nd_recommended_model_id: str | None = Field(default=None, max_length=256)
    kill_switch_on: bool = Field(strict=True)
    operator_ack: bool = Field(strict=True)
    selected_model_id: str | None = Field(default=None, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    existing_tasks: list[str] | None = None
    nd_confidence: float | None = Field(default=None, ge=0, le=1)
    min_events_for_recommendation: int | None = Field(default=None, ge=1)


@notdiamond_bench_decision_shadow_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_notdiamond_bench_decision_shadow(
            week_id=req.week_id,
            focus_task=req.focus_task,
            events=[e.model_dump() for e in req.events],
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            nd_recommended_model_id=req.nd_recommended_model_id,
            kill_switch_on=req.kill_switch_on,
            operator_ack=req.operator_ack,
            selected_model_id=req.selected_model_id,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            existing_tasks=req.existing_tasks,
            nd_confidence=req.nd_confidence,
            min_events_for_recommendation=req.min_events_for_recommendation,
        )
    except NotDiamondBenchDecisionShadowComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_notdiamond_bench_decision_shadow_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(notdiamond_bench_decision_shadow_compose_router)


__all__ = [
    "notdiamond_bench_decision_shadow_compose_router",
    "register_notdiamond_bench_decision_shadow_compose_routes",
]

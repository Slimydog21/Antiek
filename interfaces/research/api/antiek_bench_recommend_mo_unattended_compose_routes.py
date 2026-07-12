"""Registerable HTTP surface for Antiek-bench recommend + MO unattended."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.mo_unattended_source_attach_model_decision_compose_routes import (
    MoBody,
    ResearchPackBody,
)
from substrate.antiek_bench_recommend_mo_unattended_compose import (
    AntiekBenchRecommendMoUnattendedComposeError,
    compose_antiek_bench_recommend_mo_unattended,
)

antiek_bench_recommend_mo_unattended_compose_router = APIRouter(
    prefix="/research/antiek-bench-recommend-mo-unattended",
    tags=["antiek-bench-recommend-mo-unattended-compose"],
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


class BenchBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    focus_task: str = Field(min_length=1, max_length=256)
    events: list[EventBody]
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    selected_model_id: str | None = Field(default=None, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    existing_tasks: list[str] | None = None
    proposed_new_tasks: list[TaskSeedBody] | None = None
    min_events_per_task: int | None = Field(default=None, ge=1)
    min_events_for_recommendation: int | None = Field(default=None, ge=1)


class MoPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    research_pack: ResearchPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    bench: BenchBody
    mo_pack: MoPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@antiek_bench_recommend_mo_unattended_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_recommend_mo_unattended(
            bench=req.bench.model_dump(),
            mo_pack=req.mo_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except AntiekBenchRecommendMoUnattendedComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_recommend_mo_unattended_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(antiek_bench_recommend_mo_unattended_compose_router)


__all__ = [
    "antiek_bench_recommend_mo_unattended_compose_router",
    "register_antiek_bench_recommend_mo_unattended_compose_routes",
]

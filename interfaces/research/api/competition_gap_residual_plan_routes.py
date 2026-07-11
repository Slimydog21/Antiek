"""Registerable HTTP surface for competition gap residual plans."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.competition_gap_residual_plan import (
    CompetitionGapResidualPlanError,
    build_competition_gap_residual_plan,
)

competition_gap_residual_plan_router = APIRouter(
    prefix="/research/competition-gap-residual-plan",
    tags=["competition-gap-residual-plan"],
)


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    competitor: str = Field(min_length=1, max_length=256)
    area: Literal[
        "source_acquisition",
        "citation_grounding",
        "multi_agent_orchestration",
        "budget_controls",
        "html_native_reading",
        "model_routing",
        "evaluation_harness",
        "unattended_swarm",
    ]
    decision_summary: str = Field(min_length=1, max_length=4000)
    antiek_status: Literal["ahead", "parity", "behind", "unknown"]
    residual: str | None = Field(default=None, max_length=2000)


class BuildRequest(BaseModel):
    model_config = {"extra": "forbid"}

    decisions: list[DecisionBody] = Field(default_factory=list)
    max_items: int | None = Field(default=None, gt=0)


@competition_gap_residual_plan_router.post("/build")
def post_build(req: BuildRequest) -> dict[str, Any]:
    try:
        plan = build_competition_gap_residual_plan(
            decisions=[d.model_dump() for d in req.decisions],
            max_items=req.max_items,
        )
    except CompetitionGapResidualPlanError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return plan.to_dict()


def register_competition_gap_residual_plan_routes(app: FastAPI) -> None:
    app.include_router(competition_gap_residual_plan_router)


__all__ = [
    "competition_gap_residual_plan_router",
    "register_competition_gap_residual_plan_routes",
]

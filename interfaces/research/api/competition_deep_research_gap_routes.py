"""Registerable HTTP surface for competition deep research gap matrix."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.competition_deep_research_gap import (
    CompetitionDeepResearchGapError,
    build_competition_deep_research_gap,
)

competition_deep_research_gap_router = APIRouter(
    prefix="/research/competition-gap",
    tags=["competition-deep-research-gap"],
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
    focus_areas: list[
        Literal[
            "source_acquisition",
            "citation_grounding",
            "multi_agent_orchestration",
            "budget_controls",
            "html_native_reading",
            "model_routing",
            "evaluation_harness",
            "unattended_swarm",
        ]
    ] | None = None


@competition_deep_research_gap_router.post("/build")
def post_build(req: BuildRequest) -> dict[str, Any]:
    try:
        matrix = build_competition_deep_research_gap(
            decisions=[d.model_dump() for d in req.decisions],
            focus_areas=req.focus_areas,
        )
    except CompetitionDeepResearchGapError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return matrix.to_dict()


def register_competition_deep_research_gap_routes(app: FastAPI) -> None:
    app.include_router(competition_deep_research_gap_router)


__all__ = [
    "competition_deep_research_gap_router",
    "register_competition_deep_research_gap_routes",
]

"""Registerable HTTP surface for research launch readiness (advisory)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_launch_readiness import (
    ResearchLaunchReadinessError,
    evaluate_research_launch_readiness,
)

research_launch_readiness_router = APIRouter(
    prefix="/research/launch-readiness",
    tags=["research-launch-readiness"],
)


class EvaluateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    source_family_count: int = Field(ge=0)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float = Field(default=0.5, ge=0, le=1)
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)


@research_launch_readiness_router.post("/evaluate")
def post_evaluate(req: EvaluateRequest) -> dict[str, Any]:
    try:
        decision = evaluate_research_launch_readiness(
            session_id=req.session_id,
            source_family_count=req.source_family_count,
            quality_overall=req.quality_overall,
            quality_floor=req.quality_floor,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
        )
    except ResearchLaunchReadinessError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_research_launch_readiness_routes(app: FastAPI) -> None:
    app.include_router(research_launch_readiness_router)


__all__ = [
    "register_research_launch_readiness_routes",
    "research_launch_readiness_router",
]

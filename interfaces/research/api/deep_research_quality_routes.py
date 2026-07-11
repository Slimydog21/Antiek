"""Registerable HTTP surface for deep research quality rubric (advisory)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.deep_research_quality import (
    DeepResearchQualityError,
    evaluate_deep_research_quality,
)

deep_research_quality_router = APIRouter(
    prefix="/research/quality-rubric",
    tags=["deep-research-quality"],
)


class DimensionBody(BaseModel):
    model_config = {"extra": "forbid"}

    dimension: Literal[
        "citation_density",
        "source_diversity",
        "claim_grounding",
        "counterargument_coverage",
        "intellectual_honesty",
        "recursive_questions",
        "actionability",
    ]
    score: float | None = Field(default=None, ge=0, le=1)
    note: str | None = Field(default=None, max_length=2000)


class EvaluateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    research_id: str = Field(min_length=1, max_length=256)
    dimensions: list[DimensionBody] = Field(default_factory=list)
    require_all_dimensions: bool = Field(default=False, strict=True)


@deep_research_quality_router.post("/evaluate")
def post_evaluate(req: EvaluateRequest) -> dict[str, Any]:
    try:
        report = evaluate_deep_research_quality(
            research_id=req.research_id,
            dimensions=[d.model_dump() for d in req.dimensions],
            require_all_dimensions=req.require_all_dimensions,
        )
    except DeepResearchQualityError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return report.to_dict()


def register_deep_research_quality_routes(app: FastAPI) -> None:
    app.include_router(deep_research_quality_router)


__all__ = [
    "deep_research_quality_router",
    "register_deep_research_quality_routes",
]

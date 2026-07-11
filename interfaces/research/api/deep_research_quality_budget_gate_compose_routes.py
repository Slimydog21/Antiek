"""Registerable HTTP surface for deep research quality budget gate compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.deep_research_quality_budget_gate_compose import (
    DeepResearchQualityBudgetGateComposeError,
    compose_deep_research_quality_budget_gate,
)

deep_research_quality_budget_gate_compose_router = APIRouter(
    prefix="/research/dr-quality-budget-gate",
    tags=["deep-research-quality-budget-gate-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    quality_overall: float | None = None
    quality_floor: float | None = None
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    citation_pack_ready: bool | None = None
    operator_ack: bool = Field(strict=True)


@deep_research_quality_budget_gate_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_deep_research_quality_budget_gate(
            session_id=req.session_id,
            quality_overall=req.quality_overall,
            quality_floor=req.quality_floor,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            citation_pack_ready=req.citation_pack_ready,
            operator_ack=req.operator_ack,
        )
    except DeepResearchQualityBudgetGateComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_deep_research_quality_budget_gate_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(deep_research_quality_budget_gate_compose_router)


__all__ = [
    "deep_research_quality_budget_gate_compose_router",
    "register_deep_research_quality_budget_gate_compose_routes",
]

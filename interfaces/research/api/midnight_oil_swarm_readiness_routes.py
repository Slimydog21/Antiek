"""Registerable HTTP surface for Midnight Oil swarm readiness (advisory)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_swarm_readiness import (
    MidnightOilSwarmReadinessError,
    evaluate_midnight_oil_swarm_readiness,
)

midnight_oil_swarm_readiness_router = APIRouter(
    prefix="/midnight-oil/swarm-readiness",
    tags=["midnight-oil-swarm-readiness"],
)


class EvaluateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: float = Field(gt=0)
    goal_count: int = Field(ge=0)
    price_ceiling_usd: float | None = Field(default=None, ge=0)
    recommended_ceiling_usd: float | None = Field(default=None, ge=0)
    brief_dispatch_ready: bool = Field(strict=True)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)


@midnight_oil_swarm_readiness_router.post("/evaluate")
def post_evaluate(req: EvaluateRequest) -> dict[str, Any]:
    try:
        decision = evaluate_midnight_oil_swarm_readiness(
            operator_id=req.operator_id,
            work_minutes=req.work_minutes,
            goal_count=req.goal_count,
            price_ceiling_usd=req.price_ceiling_usd,
            recommended_ceiling_usd=req.recommended_ceiling_usd,
            brief_dispatch_ready=req.brief_dispatch_ready,
            unattended_ack=req.unattended_ack,
            spend_consent=req.spend_consent,
        )
    except MidnightOilSwarmReadinessError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_midnight_oil_swarm_readiness_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_swarm_readiness_router)


__all__ = [
    "midnight_oil_swarm_readiness_router",
    "register_midnight_oil_swarm_readiness_routes",
]

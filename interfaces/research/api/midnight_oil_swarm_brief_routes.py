"""Registerable HTTP surface for Midnight Oil swarm brief."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_swarm_brief import (
    MidnightOilSwarmBriefError,
    build_midnight_oil_swarm_brief,
)

midnight_oil_swarm_brief_router = APIRouter(
    prefix="/midnight-oil/swarm-brief",
    tags=["midnight-oil-swarm-brief"],
)


class SwarmGoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=4000)
    priority: float = Field(gt=0)


class SwarmBriefRequest(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: float = Field(gt=0)
    goals: list[SwarmGoalBody] = Field(min_length=1)
    price_ceiling_usd: float | None = Field(default=None, ge=0)
    recommended_ceiling_usd: float | None = Field(default=None, ge=0)
    operator_approved: bool = Field(strict=True)


@midnight_oil_swarm_brief_router.post("/build")
def post_build(req: SwarmBriefRequest) -> dict[str, Any]:
    try:
        brief = build_midnight_oil_swarm_brief(
            operator_id=req.operator_id,
            work_minutes=req.work_minutes,
            goals=[g.model_dump() for g in req.goals],
            price_ceiling_usd=req.price_ceiling_usd,
            recommended_ceiling_usd=req.recommended_ceiling_usd,
            operator_approved=req.operator_approved,
        )
    except MidnightOilSwarmBriefError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return brief.to_dict()


def register_midnight_oil_swarm_brief_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_swarm_brief_router)


__all__ = [
    "midnight_oil_swarm_brief_router",
    "register_midnight_oil_swarm_brief_routes",
]

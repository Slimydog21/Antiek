"""Registerable HTTP surface for MO entry → swarm readiness compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_entry_to_swarm_readiness_compose import (
    MidnightOilEntryToSwarmReadinessComposeError,
    compose_midnight_oil_entry_to_swarm_readiness,
)

midnight_oil_entry_to_swarm_readiness_compose_router = APIRouter(
    prefix="/research/midnight-oil-entry-readiness",
    tags=["midnight-oil-entry-to-swarm-readiness-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: float = Field(gt=0)
    goals: list[GoalBody] = Field(min_length=1)
    usd_per_hour: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    brief_dispatch_ready: bool = Field(strict=True)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)


@midnight_oil_entry_to_swarm_readiness_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_midnight_oil_entry_to_swarm_readiness(
            operator_id=req.operator_id,
            work_minutes=req.work_minutes,
            goals=[g.model_dump() for g in req.goals],
            usd_per_hour=req.usd_per_hour,
            approved_ceiling_usd=req.approved_ceiling_usd,
            operator_ack=req.operator_ack,
            brief_dispatch_ready=req.brief_dispatch_ready,
            unattended_ack=req.unattended_ack,
            spend_consent=req.spend_consent,
        )
    except MidnightOilEntryToSwarmReadinessComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_midnight_oil_entry_to_swarm_readiness_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(midnight_oil_entry_to_swarm_readiness_compose_router)


__all__ = [
    "midnight_oil_entry_to_swarm_readiness_compose_router",
    "register_midnight_oil_entry_to_swarm_readiness_compose_routes",
]

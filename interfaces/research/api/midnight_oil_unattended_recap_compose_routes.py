"""Registerable HTTP surface for Midnight Oil unattended recap compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_unattended_recap_compose import (
    MidnightOilUnattendedRecapComposeError,
    compose_midnight_oil_unattended_recap,
)

midnight_oil_unattended_recap_compose_router = APIRouter(
    prefix="/research/midnight-oil-recap",
    tags=["midnight-oil-unattended-recap-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)
    status: Literal["pending", "in_progress", "done", "blocked", "skipped"]
    notes: str | None = Field(default=None, max_length=8000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    run_id: str = Field(min_length=1, max_length=256)
    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes_planned: float = Field(gt=0)
    work_minutes_actual: float | None = Field(default=None, ge=0)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_usd: float | None = Field(default=None, ge=0)
    spend_usd: float | None = Field(default=None, ge=0)
    artifact_ids: list[str] | None = None
    operator_ack: bool = Field(strict=True)


@midnight_oil_unattended_recap_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_midnight_oil_unattended_recap(
            run_id=req.run_id,
            operator_id=req.operator_id,
            work_minutes_planned=req.work_minutes_planned,
            work_minutes_actual=req.work_minutes_actual,
            goals=[g.model_dump() for g in req.goals],
            price_ceiling_usd=req.price_ceiling_usd,
            spend_usd=req.spend_usd,
            operator_ack=req.operator_ack,
            artifact_ids=req.artifact_ids,
        )
    except MidnightOilUnattendedRecapComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_midnight_oil_unattended_recap_compose_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_unattended_recap_compose_router)


__all__ = [
    "midnight_oil_unattended_recap_compose_router",
    "register_midnight_oil_unattended_recap_compose_routes",
]

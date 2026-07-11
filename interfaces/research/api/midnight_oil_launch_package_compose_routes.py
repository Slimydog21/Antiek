"""Registerable HTTP surface for Midnight Oil launch package compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_launch_package_compose import (
    MidnightOilLaunchPackageComposeError,
    compose_midnight_oil_launch_package,
)

midnight_oil_launch_package_compose_router = APIRouter(
    prefix="/midnight-oil/launch-package",
    tags=["midnight-oil-launch-package-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    statement: str = Field(min_length=1, max_length=4000)
    priority: float = Field(gt=0)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: float = Field(gt=0)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_usd: float | None = Field(default=None, ge=0)
    recommended_ceiling_usd: float | None = Field(default=None, ge=0)
    usd_per_hour: float | None = Field(default=None, ge=0)
    operator_approved: bool = Field(strict=True)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)


@midnight_oil_launch_package_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        package = compose_midnight_oil_launch_package(
            operator_id=req.operator_id,
            work_minutes=req.work_minutes,
            goals=[g.model_dump() for g in req.goals],
            price_ceiling_usd=req.price_ceiling_usd,
            recommended_ceiling_usd=req.recommended_ceiling_usd,
            usd_per_hour=req.usd_per_hour,
            operator_approved=req.operator_approved,
            unattended_ack=req.unattended_ack,
            spend_consent=req.spend_consent,
        )
    except MidnightOilLaunchPackageComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return package.to_dict()


def register_midnight_oil_launch_package_compose_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_launch_package_compose_router)


__all__ = [
    "midnight_oil_launch_package_compose_router",
    "register_midnight_oil_launch_package_compose_routes",
]

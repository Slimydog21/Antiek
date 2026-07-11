"""Registerable HTTP surface for MO price-ceiling approval compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_price_ceiling_approval_compose import (
    MidnightOilPriceCeilingApprovalComposeError,
    compose_midnight_oil_price_ceiling_approval,
)

midnight_oil_price_ceiling_approval_compose_router = APIRouter(
    prefix="/research/midnight-oil-price-ceiling-approval",
    tags=["midnight-oil-price-ceiling-approval-compose"],
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
    price_ceiling_ack: bool = Field(strict=True)
    operator_ack: bool = Field(strict=True)
    stage: Literal["recommend_only", "approve_ceiling", "unattended_pack"]
    usd_per_hour: float | None = Field(default=None, ge=0)
    goal_intensity: float | None = Field(default=None, gt=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    below_recommend_override: bool | None = Field(default=None, strict=True)
    unattended_ack: bool | None = Field(default=None, strict=True)
    spend_consent: bool | None = Field(default=None, strict=True)


@midnight_oil_price_ceiling_approval_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_midnight_oil_price_ceiling_approval(
            operator_id=req.operator_id,
            work_minutes=req.work_minutes,
            goals=[g.model_dump() for g in req.goals],
            price_ceiling_ack=req.price_ceiling_ack,
            operator_ack=req.operator_ack,
            stage=req.stage,
            usd_per_hour=req.usd_per_hour,
            goal_intensity=req.goal_intensity,
            approved_ceiling_usd=req.approved_ceiling_usd,
            below_recommend_override=req.below_recommend_override,
            unattended_ack=req.unattended_ack,
            spend_consent=req.spend_consent,
        )
    except MidnightOilPriceCeilingApprovalComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_midnight_oil_price_ceiling_approval_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(midnight_oil_price_ceiling_approval_compose_router)


__all__ = [
    "midnight_oil_price_ceiling_approval_compose_router",
    "register_midnight_oil_price_ceiling_approval_compose_routes",
]

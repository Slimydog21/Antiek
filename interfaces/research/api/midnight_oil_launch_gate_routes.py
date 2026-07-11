"""Registerable HTTP surface for unattended launch gate evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil.unattended_launch_gate import (
    LaunchGateError,
    evaluate_unattended_launch_gate,
)

midnight_oil_launch_gate_router = APIRouter(
    prefix="/midnight-oil/unattended",
    tags=["midnight-oil-launch-gate"],
)


class LaunchGateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    operator_approved: bool = Field(strict=True)
    consent_receipt_id: str | None = None
    duration_minutes: int = Field(strict=True)
    goals: list[str] = Field(min_length=1)
    approved_ceiling_cents: int = Field(strict=True)
    recommended_ceiling_cents: int | None = Field(default=None, strict=True)


@midnight_oil_launch_gate_router.post("/launch-gate")
def post_launch_gate(req: LaunchGateRequest) -> dict[str, Any]:
    try:
        decision = evaluate_unattended_launch_gate(
            operator_approved=req.operator_approved,
            consent_receipt_id=req.consent_receipt_id,
            duration_minutes=req.duration_minutes,
            goals=req.goals,
            approved_ceiling_cents=req.approved_ceiling_cents,
            recommended_ceiling_cents=req.recommended_ceiling_cents,
        )
    except LaunchGateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_midnight_oil_launch_gate_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_launch_gate_router)


__all__ = [
    "midnight_oil_launch_gate_router",
    "register_midnight_oil_launch_gate_routes",
]

"""Registerable HTTP surface for Midnight Oil unattended brief validation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil.unattended_brief import (
    UnattendedBriefError,
    build_unattended_brief,
)

midnight_oil_unattended_router = APIRouter(
    prefix="/midnight-oil/unattended",
    tags=["midnight-oil-unattended"],
)


class UnattendedBriefRequest(BaseModel):
    model_config = {"extra": "forbid"}

    duration_minutes: int = Field(strict=True)
    goals: list[str] = Field(min_length=1)
    approved_ceiling_cents: int = Field(strict=True)
    recommended_ceiling_cents: int | None = Field(default=None, strict=True)


@midnight_oil_unattended_router.post("/brief")
def post_unattended_brief(req: UnattendedBriefRequest) -> dict[str, Any]:
    try:
        brief = build_unattended_brief(
            duration_minutes=req.duration_minutes,
            goals=req.goals,
            approved_ceiling_cents=req.approved_ceiling_cents,
            recommended_ceiling_cents=req.recommended_ceiling_cents,
        )
    except UnattendedBriefError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return brief.to_dict()


def register_midnight_oil_unattended_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_unattended_router)


__all__ = [
    "midnight_oil_unattended_router",
    "register_midnight_oil_unattended_routes",
]

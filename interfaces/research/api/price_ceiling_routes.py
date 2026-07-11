"""HTTP surface for Midnight Oil price-ceiling recommendation (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil.price_ceiling_recommend import (
    PriceCeilingError,
    recommend_price_ceiling,
)

price_ceiling_router = APIRouter(
    prefix="/midnight-oil/price-ceiling",
    tags=["midnight-oil-price-ceiling"],
)


class PriceCeilingRequest(BaseModel):
    hours: float
    goals: list[str] | int = Field(default_factory=list)
    usd_per_hour_low: float = 1.0
    usd_per_hour_high: float = 5.0
    usd_per_goal: float = 0.5
    contingency_fraction: float = 0.15


@price_ceiling_router.post("/recommend")
def recommend(req: PriceCeilingRequest) -> dict[str, Any]:
    """Advisory ceiling only — never reserves or spends."""
    try:
        rec = recommend_price_ceiling(
            hours=req.hours,
            goals=req.goals,
            usd_per_hour_low=req.usd_per_hour_low,
            usd_per_hour_high=req.usd_per_hour_high,
            usd_per_goal=req.usd_per_goal,
            contingency_fraction=req.contingency_fraction,
        )
    except PriceCeilingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return rec.to_dict()


def register_price_ceiling_routes(app: FastAPI) -> None:
    app.include_router(price_ceiling_router)


__all__ = [
    "PriceCeilingRequest",
    "price_ceiling_router",
    "register_price_ceiling_routes",
    "recommend",
]

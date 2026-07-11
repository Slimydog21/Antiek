"""HTTP surface for usage bar + prompt projection (registerable)."""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from substrate.model_decision.usage_bar import (
    compute_usage_bar,
    project_prompt_against_bar,
    prompt_projection_to_dict,
    usage_bar_to_dict,
)

model_usage_bar_router = APIRouter(
    prefix="/settings/usage-bar",
    tags=["model-usage-bar"],
)


def _reject_nonfinite(v: float | None) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("must be a finite number or null")
    if not math.isfinite(float(v)):
        raise ValueError("must be finite (NaN/Inf rejected)")
    return float(v)


class UsageBarRequest(BaseModel):
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    spend_basis: str = "reserved_estimate"
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)

    @field_validator(
        "daily_cap_usd",
        "spent_usd",
        "projected_cost_usd_low",
        "projected_cost_usd_high",
        mode="before",
    )
    @classmethod
    def _finite(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and v.strip().lower() in {"nan", "inf", "+inf", "-inf", "infinity", "-infinity"}:
            raise ValueError("must be finite (NaN/Inf rejected)")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return _reject_nonfinite(float(v))
        return v


@model_usage_bar_router.post("/project")
def project_usage(req: UsageBarRequest) -> dict[str, Any]:
    """Return usage bar + optional prompt projection. No spend, no dispatch."""
    try:
        bar = compute_usage_bar(
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            spend_basis=req.spend_basis,
        )
        body: dict[str, Any] = {"usage_bar": usage_bar_to_dict(bar)}
        if (
            req.projected_cost_usd_low is not None
            or req.projected_cost_usd_high is not None
        ):
            proj = project_prompt_against_bar(
                bar,
                projected_cost_usd_low=req.projected_cost_usd_low,
                projected_cost_usd_high=req.projected_cost_usd_high,
            )
            body["prompt_projection"] = prompt_projection_to_dict(proj)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return body


def register_model_usage_bar_routes(app: FastAPI) -> None:
    app.include_router(model_usage_bar_router)


__all__ = [
    "UsageBarRequest",
    "model_usage_bar_router",
    "project_usage",
    "register_model_usage_bar_routes",
]

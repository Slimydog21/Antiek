"""HTTP surface for usage bar + prompt projection (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

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


class UsageBarRequest(BaseModel):
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    spend_basis: str = "reserved_estimate"
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)


@model_usage_bar_router.post("/project")
def project_usage(req: UsageBarRequest) -> dict[str, Any]:
    """Return usage bar + optional prompt projection. No spend, no dispatch."""
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
    return body


def register_model_usage_bar_routes(app: FastAPI) -> None:
    app.include_router(model_usage_bar_router)


__all__ = [
    "UsageBarRequest",
    "model_usage_bar_router",
    "project_usage",
    "register_model_usage_bar_routes",
]

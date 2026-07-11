"""Registerable HTTP surface for settings decision tree usage bar compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)

settings_decision_tree_usage_bar_compose_router = APIRouter(
    prefix="/research/settings-decision-tree-usage-bar",
    tags=["settings-decision-tree-usage-bar-compose"],
)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    tier: str | None = None
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None
    pending_add_model_ids: list[str] | None = None
    operator_ack: bool = Field(strict=True)


@settings_decision_tree_usage_bar_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_decision_tree_usage_bar(
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            pending_add_model_ids=req.pending_add_model_ids,
            operator_ack=req.operator_ack,
        )
    except SettingsDecisionTreeUsageBarComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_decision_tree_usage_bar_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(settings_decision_tree_usage_bar_compose_router)


__all__ = [
    "settings_decision_tree_usage_bar_compose_router",
    "register_settings_decision_tree_usage_bar_compose_routes",
]

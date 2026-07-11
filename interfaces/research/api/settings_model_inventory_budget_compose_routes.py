"""Registerable HTTP surface for settings model inventory budget compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.settings_model_inventory_budget_compose import (
    SettingsModelInventoryBudgetComposeError,
    compose_settings_model_inventory_budget,
)

settings_model_inventory_budget_compose_router = APIRouter(
    prefix="/research/settings-model-inventory-budget",
    tags=["settings-model-inventory-budget-compose"],
)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    tier: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=64)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[ModelBody]
    pending_add_model_ids: list[str] | None = None
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    selected_model_id: str | None = Field(default=None, max_length=128)


@settings_model_inventory_budget_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_model_inventory_budget(
            models=[m.model_dump() for m in req.models],
            pending_add_model_ids=req.pending_add_model_ids,
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            selected_model_id=req.selected_model_id,
        )
    except SettingsModelInventoryBudgetComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_model_inventory_budget_compose_routes(app: FastAPI) -> None:
    app.include_router(settings_model_inventory_budget_compose_router)


__all__ = [
    "settings_model_inventory_budget_compose_router",
    "register_settings_model_inventory_budget_compose_routes",
]

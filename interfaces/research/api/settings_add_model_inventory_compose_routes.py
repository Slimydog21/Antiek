"""Registerable HTTP surface for settings add-model inventory compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
)

settings_add_model_inventory_compose_router = APIRouter(
    prefix="/research/settings-add-model-inventory",
    tags=["settings-add-model-inventory-compose"],
)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    tier: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=128)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[ModelBody]
    pending_add_model_ids: list[str]
    action: Literal["preview", "propose_add"]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


@settings_add_model_inventory_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_inventory(
            models=[m.model_dump() for m in req.models],
            pending_add_model_ids=req.pending_add_model_ids,
            action=req.action,
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            operator_ack=req.operator_ack,
            selected_model_id=req.selected_model_id,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
        )
    except SettingsAddModelInventoryComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_inventory_compose_routes(app: FastAPI) -> None:
    app.include_router(settings_add_model_inventory_compose_router)


__all__ = [
    "settings_add_model_inventory_compose_router",
    "register_settings_add_model_inventory_compose_routes",
]

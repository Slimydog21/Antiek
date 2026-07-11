"""Registerable HTTP surface for settings model driver tab compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.settings_model_driver_tab_compose import (
    SettingsModelDriverTabComposeError,
    compose_settings_model_driver_tab,
)

settings_model_driver_tab_compose_router = APIRouter(
    prefix="/settings/model-driver-tab",
    tags=["settings-model-driver-tab-compose"],
)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class BenchBestBody(BaseModel):
    model_config = {"extra": "forbid"}

    task: str = Field(min_length=1, max_length=256)
    best_model_id: str = Field(min_length=1, max_length=256)
    score: float | None = Field(default=None, ge=0, le=1)


class NdShadowBody(BaseModel):
    model_config = {"extra": "forbid"}

    recommended_model_id: str = Field(min_length=1, max_length=256)
    kill_switch_on: bool = Field(strict=True)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None)
    spent_usd: float | None = Field(default=None)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    bench_bests: list[BenchBestBody] | None = None
    focus_task: str | None = Field(default=None, max_length=256)
    nd_shadow: NdShadowBody | None = None
    pending_add_model_ids: list[str] | None = None


@settings_model_driver_tab_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        snap = compose_settings_model_driver_tab(
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            bench_bests=(
                [b.model_dump() for b in req.bench_bests]
                if req.bench_bests is not None
                else None
            ),
            focus_task=req.focus_task,
            nd_shadow=req.nd_shadow.model_dump() if req.nd_shadow else None,
            pending_add_model_ids=req.pending_add_model_ids,
        )
    except SettingsModelDriverTabComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return snap.to_dict()


def register_settings_model_driver_tab_compose_routes(app: FastAPI) -> None:
    app.include_router(settings_model_driver_tab_compose_router)


__all__ = [
    "settings_model_driver_tab_compose_router",
    "register_settings_model_driver_tab_compose_routes",
]

"""Registerable HTTP surface for settings add-model bench ND shadow compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.settings_add_model_bench_nd_shadow_compose import (
    SettingsAddModelBenchNdShadowComposeError,
    compose_settings_add_model_bench_nd_shadow,
)

settings_add_model_bench_nd_shadow_compose_router = APIRouter(
    prefix="/research/settings-add-model-bench-nd-shadow",
    tags=["settings-add-model-bench-nd-shadow-compose"],
)


class InventoryModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=128)


class DecisionModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class EventBody(BaseModel):
    model_config = {"extra": "forbid"}

    event_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    outcome: Literal["worked", "failed", "partial", "unknown"]
    score: float | None = Field(default=None, ge=0, le=1)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[InventoryModelBody]
    pending_add_model_ids: list[str]
    action: Literal["preview", "propose_add"]
    week_id: str = Field(min_length=1, max_length=64)
    focus_task: str = Field(min_length=1, max_length=256)
    events: list[EventBody]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    nd_recommended_model_id: str | None = Field(default=None, max_length=128)
    kill_switch_on: bool = Field(strict=True)
    decision_models: list[DecisionModelBody] | None = None
    selected_model_id: str | None = Field(default=None, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    existing_tasks: list[str] | None = None
    nd_confidence: float | None = Field(default=None, ge=0, le=1)
    min_events_for_recommendation: int | None = Field(default=None, ge=1)
    require_both: bool = Field(default=True, strict=True)


@settings_add_model_bench_nd_shadow_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_bench_nd_shadow(
            models=[m.model_dump() for m in req.models],
            pending_add_model_ids=req.pending_add_model_ids,
            action=req.action,
            week_id=req.week_id,
            focus_task=req.focus_task,
            events=[e.model_dump() for e in req.events],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            operator_ack=req.operator_ack,
            nd_recommended_model_id=req.nd_recommended_model_id,
            kill_switch_on=req.kill_switch_on,
            decision_models=(
                [m.model_dump() for m in req.decision_models]
                if req.decision_models is not None
                else None
            ),
            selected_model_id=req.selected_model_id,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            existing_tasks=req.existing_tasks,
            nd_confidence=req.nd_confidence,
            min_events_for_recommendation=req.min_events_for_recommendation,
            require_both=req.require_both,
        )
    except SettingsAddModelBenchNdShadowComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_bench_nd_shadow_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(settings_add_model_bench_nd_shadow_compose_router)


__all__ = [
    "settings_add_model_bench_nd_shadow_compose_router",
    "register_settings_add_model_bench_nd_shadow_compose_routes",
]

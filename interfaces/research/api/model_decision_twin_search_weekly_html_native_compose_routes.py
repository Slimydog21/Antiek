"""Registerable HTTP surface for model decision + twin search weekly HTML-native."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.twin_search_antiek_bench_weekly_html_native_compose_routes import (
    TwinSearchRecordBody,
    WeeklyHtmlBody,
)
from substrate.model_decision_twin_search_weekly_html_native_compose import (
    ModelDecisionTwinSearchWeeklyHtmlNativeComposeError,
    compose_model_decision_twin_search_weekly_html_native,
)

model_decision_twin_search_weekly_html_native_compose_router = APIRouter(
    prefix="/research/model-decision-twin-search-weekly-html-native",
    tags=["model-decision-twin-search-weekly-html-native-compose"],
)


class ModelOptionBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelOptionBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    focus_task: str | None = Field(default=None, max_length=256)
    pending_add_model_ids: list[str] | None = None


class TwinSearchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2048)
    twin_records: list[TwinSearchRecordBody]
    weekly_html: WeeklyHtmlBody
    search_limit: int | None = Field(default=None, ge=1, le=500)
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    twin_search_pack: TwinSearchPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)
    block_on_budget_exceed: bool = Field(default=True, strict=True)


@model_decision_twin_search_weekly_html_native_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_model_decision_twin_search_weekly_html_native(
            decision=req.decision.model_dump(),
            twin_search_pack=req.twin_search_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
            block_on_budget_exceed=req.block_on_budget_exceed,
        )
    except ModelDecisionTwinSearchWeeklyHtmlNativeComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_model_decision_twin_search_weekly_html_native_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        model_decision_twin_search_weekly_html_native_compose_router
    )


__all__ = [
    "model_decision_twin_search_weekly_html_native_compose_router",
    "register_model_decision_twin_search_weekly_html_native_compose_routes",
]

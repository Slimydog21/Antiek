"""Registerable HTTP surface for model decision over twin search HTML-native marketplace MO weekly src write."""

from __future__ import annotations

import sys

# Nested residual Pydantic body graphs exceed default recursion depth.
if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_decision_tree_usage_bar_compose_routes import (
    ModelBody,
)
from interfaces.research.api.twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    HtmlPackBody,
    TwinRecordBody,
)
from substrate.model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    ModelDecisionTwinSearchHtmlNativeMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/model-decision-twin-search-html-native-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["model-decision-twin-search-html-native-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None
    focus_task: str | None = Field(default=None, max_length=256)
    pending_add_model_ids: list[str] | None = None


class TwinSearchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2000)
    twin_records: list[TwinRecordBody]
    html_pack: HtmlPackBody
    search_limit: int | None = Field(default=None, ge=1, le=1000)
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    twin_search_pack: TwinSearchPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)
    block_on_budget_exceed: bool = Field(default=True, strict=True)


@model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            decision=req.decision.model_dump(),
            twin_search_pack=req.twin_search_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
            block_on_budget_exceed=req.block_on_budget_exceed,
        )
    except ModelDecisionTwinSearchHtmlNativeMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]

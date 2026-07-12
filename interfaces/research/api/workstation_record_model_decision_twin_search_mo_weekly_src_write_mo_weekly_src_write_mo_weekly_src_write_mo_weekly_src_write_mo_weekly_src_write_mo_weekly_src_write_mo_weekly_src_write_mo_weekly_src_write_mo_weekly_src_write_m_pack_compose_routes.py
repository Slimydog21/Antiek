"""Registerable HTTP surface for workstation records over model decision twin search MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mw_pack_compose_routes import (
    DecisionBody,
    TwinSearchPackBody,
)
from substrate.workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose import (
    WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError,
    compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack,
)

workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_router = APIRouter(
    prefix="/research/workstation-record-model-decision-twin-search-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-m-pack",
    tags=["workstation-record-model-decision-twin-search-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class RecordItemBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal["insight", "question", "highlight", "finding", "open_thread"]
    text: str = Field(min_length=1, max_length=10000)
    asset_id: str | None = Field(default=None, max_length=256)
    weight: float | None = Field(default=None, ge=0, le=1)


class DecisionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    twin_search_pack: TwinSearchPackBody
    require_both: bool | None = Field(default=None, strict=True)
    block_on_budget_exceed: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    items: list[RecordItemBody]
    decision_pack: DecisionPackBody
    operator_ack: bool = Field(strict=True)
    max_context_lines: int | None = Field(default=None, ge=1, le=10000)
    require_both: bool = Field(default=True, strict=True)



def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + pack_ready only."""
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "session_aligned": result.session_aligned,
        "pack_ready": result.pack_ready,
        "records": {
            "item_count": result.records.item_count,
            "pack_ready": result.records.pack_ready,
        },
        "decision_pack": {
            "pack_ready": result.decision_pack.pack_ready,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
        },
        "record_persisted": False,
        "prompts_injected": False,
        "live_router_authorized": False,
        "secrets_stored": False,
        "live_meter_read": False,
        "remote_index_queried": False,
        "twin_written": False,
        "purchase_executed": False,
        "hosted": False,
        "pdf_view_authorized": False,
        "pdf_primary": False,
        "live_execution_authorized": False,
        "charge_executed": False,
        "inventory_mutated": False,
        "live_dispatch_authorized": False,
        "remote_fetched": False,
        "backlog_mutated": False,
        "store_mutated": False,
        "suite_rewritten": False,
        "merge_executed": False,
        "draft_written": False,
        "analysis_written": False,
        "live_dispatched": False,
        "pack_dispatched": False,
        "production_router_verdict": "REJECT",
        "authority": result.authority,
    }


@workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack(
            session_id=req.session_id,
            items=[i.model_dump() for i in req.items],
            decision_pack=req.decision_pack.model_dump(),
            operator_ack=req.operator_ack,
            max_context_lines=req.max_context_lines,
            require_both=req.require_both,
        )
    except WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_router
    )


__all__ = [
    "workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_router",
    "register_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_routes",
]

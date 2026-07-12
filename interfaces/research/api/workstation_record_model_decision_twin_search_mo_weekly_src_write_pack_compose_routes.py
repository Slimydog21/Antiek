"""Registerable HTTP surface for workstation records over model decision twin search MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 5000:
    sys.setrecursionlimit(5000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.model_decision_twin_search_html_native_mo_weekly_src_write_pack_compose_routes import (
    DecisionBody,
    TwinSearchPackBody,
)
from substrate.workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose import (
    WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWritePackComposeError,
    compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_pack,
)

workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/workstation-record-model-decision-twin-search-mo-weekly-src-write-pack",
    tags=["workstation-record-model-decision-twin-search-mo-weekly-src-write-pack-compose"],
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


@workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_pack(
            session_id=req.session_id,
            items=[i.model_dump() for i in req.items],
            decision_pack=req.decision_pack.model_dump(),
            operator_ack=req.operator_ack,
            max_context_lines=req.max_context_lines,
            require_both=req.require_both,
        )
    except WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose_router",
    "register_workstation_record_model_decision_twin_search_mo_weekly_src_write_pack_compose_routes",
]

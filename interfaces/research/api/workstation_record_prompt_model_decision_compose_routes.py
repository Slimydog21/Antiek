"""Registerable HTTP surface for workstation record→prompt→model decision."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.workstation_record_prompt_model_decision_compose import (
    WorkstationRecordPromptModelDecisionComposeError,
    compose_workstation_record_prompt_model_decision,
)

workstation_record_prompt_model_decision_compose_router = APIRouter(
    prefix="/research/workstation-record-prompt-model-decision",
    tags=["workstation-record-prompt-model-decision-compose"],
)


class RecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal["insight", "question", "data", "claim"]
    body: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = Field(default=None, max_length=256)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=128)
    tier: str | None = None
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    records: list[RecordBody] = Field(min_length=1)
    user_prompt: str = Field(min_length=1, max_length=16000)
    placement: Literal["prefix", "suffix"] | None = None
    max_context_lines: int | None = Field(default=None, ge=1)
    selected_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    focus_task: str | None = Field(default=None, max_length=128)
    operator_ack: bool = Field(strict=True)


@workstation_record_prompt_model_decision_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_workstation_record_prompt_model_decision(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            records=[r.model_dump() for r in req.records],
            user_prompt=req.user_prompt,
            placement=req.placement,
            max_context_lines=req.max_context_lines,
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            focus_task=req.focus_task,
            operator_ack=req.operator_ack,
        )
    except WorkstationRecordPromptModelDecisionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_workstation_record_prompt_model_decision_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(workstation_record_prompt_model_decision_compose_router)


__all__ = [
    "workstation_record_prompt_model_decision_compose_router",
    "register_workstation_record_prompt_model_decision_compose_routes",
]

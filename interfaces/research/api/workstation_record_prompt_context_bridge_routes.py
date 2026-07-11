"""Registerable HTTP surface for workstation record → prompt context bridge."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.workstation_record_prompt_context_bridge import (
    WorkstationRecordPromptContextBridgeError,
    bridge_workstation_record_prompt_context,
)

workstation_record_prompt_context_bridge_router = APIRouter(
    prefix="/research/record-prompt-context",
    tags=["workstation-record-prompt-context-bridge"],
)


class ItemBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal[
        "insight", "question", "highlight", "finding", "open_thread"
    ]
    text: str = Field(min_length=1, max_length=8000)
    asset_id: str | None = Field(default=None, max_length=256)
    weight: float | None = Field(default=None, ge=0, le=1)


class ModelOptionBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = None
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class ModelDecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelOptionBody] = Field(min_length=1)
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class BridgeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    user_prompt: str = Field(min_length=1, max_length=100_000)
    items: list[ItemBody] | None = None
    max_context_lines: int | None = Field(default=None, gt=0)
    placement: Literal["prefix", "suffix"] = "prefix"
    model_decision: ModelDecisionBody | None = None


@workstation_record_prompt_context_bridge_router.post("/bridge")
def post_bridge(req: BridgeRequest) -> dict[str, Any]:
    try:
        env = bridge_workstation_record_prompt_context(
            session_id=req.session_id,
            user_prompt=req.user_prompt,
            items=(
                [i.model_dump() for i in req.items]
                if req.items is not None
                else []
            ),
            max_context_lines=req.max_context_lines,
            placement=req.placement,
            model_decision=(
                req.model_decision.model_dump()
                if req.model_decision is not None
                else None
            ),
        )
    except WorkstationRecordPromptContextBridgeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return env.to_dict()


def register_workstation_record_prompt_context_bridge_routes(
    app: FastAPI,
) -> None:
    app.include_router(workstation_record_prompt_context_bridge_router)


__all__ = [
    "workstation_record_prompt_context_bridge_router",
    "register_workstation_record_prompt_context_bridge_routes",
]

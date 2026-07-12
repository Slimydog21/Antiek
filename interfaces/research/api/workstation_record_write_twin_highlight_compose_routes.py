"""Registerable HTTP surface for workstation record→prompt + write twin highlight."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.write_twin_collective_highlight_float_twin_search_compose_routes import (
    HighlightPackBody,
    WriteBody,
)
from substrate.workstation_record_write_twin_highlight_compose import (
    WorkstationRecordWriteTwinHighlightComposeError,
    compose_workstation_record_write_twin_highlight,
)

workstation_record_write_twin_highlight_compose_router = APIRouter(
    prefix="/research/workstation-record-write-twin-highlight",
    tags=["workstation-record-write-twin-highlight-compose"],
)


class RecordItemBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = Field(default=None, max_length=512)


class ModelOptionBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class RecordPromptBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    records: list[RecordItemBody] = Field(min_length=1)
    user_prompt: str = Field(min_length=1, max_length=8000)
    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelOptionBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class WritePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    highlight_pack: HighlightPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    record_prompt: RecordPromptBody
    write_pack: WritePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@workstation_record_write_twin_highlight_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_workstation_record_write_twin_highlight(
            record_prompt=req.record_prompt.model_dump(),
            write_pack=req.write_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except WorkstationRecordWriteTwinHighlightComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_workstation_record_write_twin_highlight_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(workstation_record_write_twin_highlight_compose_router)


__all__ = [
    "workstation_record_write_twin_highlight_compose_router",
    "register_workstation_record_write_twin_highlight_compose_routes",
]

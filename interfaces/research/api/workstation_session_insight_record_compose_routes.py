"""Registerable HTTP surface for workstation session insight record compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.workstation_session_insight_record_compose import (
    WorkstationSessionInsightRecordComposeError,
    compose_workstation_session_insight_record,
)

workstation_session_insight_record_compose_router = APIRouter(
    prefix="/research/session-insight-record",
    tags=["workstation-session-insight-record-compose"],
)


class RecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal["insight", "question", "data", "claim"]
    body: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = Field(default=None, max_length=256)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    records: list[RecordBody] = Field(min_length=1)
    operator_ack: bool = Field(strict=True)
    mark_for_prompt_context: bool = Field(default=False, strict=True)


@workstation_session_insight_record_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_workstation_session_insight_record(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            records=[r.model_dump() for r in req.records],
            operator_ack=req.operator_ack,
            mark_for_prompt_context=req.mark_for_prompt_context,
        )
    except WorkstationSessionInsightRecordComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_workstation_session_insight_record_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(workstation_session_insight_record_compose_router)


__all__ = [
    "workstation_session_insight_record_compose_router",
    "register_workstation_session_insight_record_compose_routes",
]

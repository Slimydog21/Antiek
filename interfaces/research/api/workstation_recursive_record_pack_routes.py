"""Registerable HTTP surface for workstation recursive record pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.workstation_recursive_record_pack import (
    WorkstationRecursiveRecordPackError,
    compose_workstation_recursive_record_pack,
)

workstation_recursive_record_pack_router = APIRouter(
    prefix="/research/workstation-record-pack",
    tags=["workstation-recursive-record-pack"],
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


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    items: list[ItemBody] = Field(default_factory=list)
    max_context_lines: int | None = Field(default=None, gt=0)


@workstation_recursive_record_pack_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        pack = compose_workstation_recursive_record_pack(
            session_id=req.session_id,
            items=[i.model_dump() for i in req.items],
            max_context_lines=req.max_context_lines,
        )
    except WorkstationRecursiveRecordPackError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return pack.to_dict()


def register_workstation_recursive_record_pack_routes(app: FastAPI) -> None:
    app.include_router(workstation_recursive_record_pack_router)


__all__ = [
    "workstation_recursive_record_pack_router",
    "register_workstation_recursive_record_pack_routes",
]

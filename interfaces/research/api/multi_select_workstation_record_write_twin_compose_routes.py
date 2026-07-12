"""Registerable HTTP surface for multi-select + workstation record write twin pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.workstation_record_write_twin_highlight_compose_routes import (
    RecordPromptBody,
    WritePackBody,
)
from substrate.multi_select_workstation_record_write_twin_compose import (
    MultiSelectWorkstationRecordWriteTwinComposeError,
    compose_multi_select_workstation_record_write_twin,
)

multi_select_workstation_record_write_twin_compose_router = APIRouter(
    prefix="/research/multi-select-workstation-record-write-twin",
    tags=["multi-select-workstation-record-write-twin-compose"],
)

TrayStatus = Literal["proposed", "open", "completed", "closed"]
PackMode = Literal["cohesive_prompt", "collective_pack", "cohesive_plus_analysis"]


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: TrayStatus
    highlight: str | None = Field(default=None, max_length=4000)
    prior_prompt: str | None = Field(default=None, max_length=8000)
    context: list[str] | None = None
    findings: list[str] | None = None


class MultiSelectBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=2)
    selected_instance_ids: list[str] = Field(min_length=2)
    pack_mode: PackMode
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    extra_context: list[str] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    extra_findings: list[str] | None = None


class RecordWriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_prompt: RecordPromptBody
    write_pack: WritePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiSelectBody
    record_write: RecordWriteBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@multi_select_workstation_record_write_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_multi_select_workstation_record_write_twin(
            multiselect=req.multiselect.model_dump(),
            record_write=req.record_write.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MultiSelectWorkstationRecordWriteTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_multi_select_workstation_record_write_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(multi_select_workstation_record_write_twin_compose_router)


__all__ = [
    "multi_select_workstation_record_write_twin_compose_router",
    "register_multi_select_workstation_record_write_twin_compose_routes",
]

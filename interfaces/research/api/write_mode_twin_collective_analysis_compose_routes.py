"""Registerable HTTP surface for write-mode twin + collective analysis."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)

write_mode_twin_collective_analysis_compose_router = APIRouter(
    prefix="/research/write-mode-twin-collective-analysis",
    tags=["write-mode-twin-collective-analysis-compose"],
)


class TwinSliceBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class SlotBody(BaseModel):
    model_config = {"extra": "forbid"}

    slot_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    findings: list[str] | None = None
    body: str | None = Field(default=None, max_length=8000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_slices: list[TwinSliceBody] = Field(min_length=1)
    chase_slots: list[SlotBody] = Field(min_length=2)
    analysis_kind: Literal["draft_analysis", "full_analysis"]
    operator_ack: bool = Field(strict=True)
    base_draft_html: str | None = Field(default=None, max_length=100000)
    extra_findings: list[str] | None = None
    require_both: bool = Field(default=True, strict=True)


@write_mode_twin_collective_analysis_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_write_mode_twin_collective_analysis(
            session_id=req.session_id,
            draft_id=req.draft_id,
            parent_asset_id=req.parent_asset_id,
            twin_slices=[s.model_dump() for s in req.twin_slices],
            chase_slots=[s.model_dump() for s in req.chase_slots],
            analysis_kind=req.analysis_kind,
            operator_ack=req.operator_ack,
            base_draft_html=req.base_draft_html,
            extra_findings=req.extra_findings,
            require_both=req.require_both,
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_mode_twin_collective_analysis_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(write_mode_twin_collective_analysis_compose_router)


__all__ = [
    "write_mode_twin_collective_analysis_compose_router",
    "register_write_mode_twin_collective_analysis_compose_routes",
]

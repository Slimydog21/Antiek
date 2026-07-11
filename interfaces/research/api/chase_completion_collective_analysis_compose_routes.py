"""Registerable HTTP surface for chase completion collective analysis compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.chase_completion_collective_analysis_compose import (
    ChaseCompletionCollectiveAnalysisComposeError,
    compose_chase_completion_collective_analysis,
)

chase_completion_collective_analysis_compose_router = APIRouter(
    prefix="/research/chase-completion-analysis",
    tags=["chase-completion-collective-analysis-compose"],
)


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
    parent_asset_id: str = Field(min_length=1, max_length=256)
    slots: list[SlotBody] = Field(min_length=2)
    kind: Literal["draft_analysis", "full_analysis"]
    operator_ack: bool = Field(strict=True)
    extra_findings: list[str] | None = None


@chase_completion_collective_analysis_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_chase_completion_collective_analysis(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            slots=[s.model_dump() for s in req.slots],
            kind=req.kind,
            operator_ack=req.operator_ack,
            extra_findings=req.extra_findings,
        )
    except ChaseCompletionCollectiveAnalysisComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_chase_completion_collective_analysis_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(chase_completion_collective_analysis_compose_router)


__all__ = [
    "chase_completion_collective_analysis_compose_router",
    "register_chase_completion_collective_analysis_compose_routes",
]

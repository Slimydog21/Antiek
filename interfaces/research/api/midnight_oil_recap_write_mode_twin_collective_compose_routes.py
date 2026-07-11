"""Registerable HTTP surface for MO recap → write twin collective compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_recap_write_mode_twin_collective_compose import (
    MidnightOilRecapWriteModeTwinCollectiveComposeError,
    compose_midnight_oil_recap_write_mode_twin_collective,
)

midnight_oil_recap_write_mode_twin_collective_compose_router = APIRouter(
    prefix="/research/midnight-oil-recap-write-mode-twin-collective",
    tags=["midnight-oil-recap-write-mode-twin-collective-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)
    status: Literal["pending", "in_progress", "done", "blocked", "skipped"]
    notes: str | None = Field(default=None, max_length=8000)


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

    run_id: str = Field(min_length=1, max_length=256)
    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes_planned: float = Field(gt=0)
    work_minutes_actual: float | None = Field(default=None, ge=0)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_usd: float | None = Field(default=None, ge=0)
    spend_usd: float | None = Field(default=None, ge=0)
    artifact_ids: list[str] | None = None
    operator_ack: bool = Field(strict=True)
    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    twin_slices: list[TwinSliceBody] | None = None
    chase_slots: list[SlotBody] | None = None
    base_draft_html: str | None = Field(default=None, max_length=100000)
    extra_findings: list[str] | None = None
    require_both: bool = Field(default=True, strict=True)


@midnight_oil_recap_write_mode_twin_collective_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_midnight_oil_recap_write_mode_twin_collective(
            run_id=req.run_id,
            operator_id=req.operator_id,
            work_minutes_planned=req.work_minutes_planned,
            work_minutes_actual=req.work_minutes_actual,
            goals=[g.model_dump() for g in req.goals],
            price_ceiling_usd=req.price_ceiling_usd,
            spend_usd=req.spend_usd,
            artifact_ids=req.artifact_ids,
            operator_ack=req.operator_ack,
            session_id=req.session_id,
            draft_id=req.draft_id,
            parent_asset_id=req.parent_asset_id,
            analysis_kind=req.analysis_kind,
            twin_slices=(
                [s.model_dump() for s in req.twin_slices]
                if req.twin_slices is not None
                else None
            ),
            chase_slots=(
                [s.model_dump() for s in req.chase_slots]
                if req.chase_slots is not None
                else None
            ),
            base_draft_html=req.base_draft_html,
            extra_findings=req.extra_findings,
            require_both=req.require_both,
        )
    except MidnightOilRecapWriteModeTwinCollectiveComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_midnight_oil_recap_write_mode_twin_collective_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        midnight_oil_recap_write_mode_twin_collective_compose_router
    )


__all__ = [
    "midnight_oil_recap_write_mode_twin_collective_compose_router",
    "register_midnight_oil_recap_write_mode_twin_collective_compose_routes",
]

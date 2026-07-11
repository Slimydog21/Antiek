"""Registerable HTTP surface for chase → twin → analysis loop compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.chase_twin_analysis_loop_compose import (
    ChaseTwinAnalysisLoopComposeError,
    compose_chase_twin_analysis_loop,
)

chase_twin_analysis_loop_compose_router = APIRouter(
    prefix="/research/chase-twin-analysis-loop",
    tags=["chase-twin-analysis-loop-compose"],
)


class QuestionBody(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    priority: int | None = None


class SlotBody(BaseModel):
    model_config = {"extra": "forbid"}

    slot_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    findings: list[str] | None = None
    body: str | None = Field(default=None, max_length=8000)


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    questions: list[QuestionBody] = Field(min_length=1)
    chase_mode: Literal[
        "single_question", "swarm_fanout", "collective_merge_after"
    ]
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None
    completed_slots: list[SlotBody]
    twin_findings: list[FindingBody] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"]
    analysis_excerpt: str | None = Field(default=None, max_length=8000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=False, strict=True)
    operator_ack: bool = Field(strict=True)


@chase_twin_analysis_loop_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_chase_twin_analysis_loop(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            questions=[q.model_dump() for q in req.questions],
            chase_mode=req.chase_mode,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            selected_model_id=req.selected_model_id,
            source_families=req.source_families,
            completed_slots=[s.model_dump() for s in req.completed_slots],
            twin_findings=(
                [f.model_dump() for f in req.twin_findings]
                if req.twin_findings is not None
                else None
            ),
            analysis_kind=req.analysis_kind,
            analysis_excerpt=req.analysis_excerpt,
            existing_twin_asset_id=req.existing_twin_asset_id,
            mark_for_prompt_context=req.mark_for_prompt_context,
            operator_ack=req.operator_ack,
        )
    except ChaseTwinAnalysisLoopComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_chase_twin_analysis_loop_compose_routes(app: FastAPI) -> None:
    app.include_router(chase_twin_analysis_loop_compose_router)


__all__ = [
    "chase_twin_analysis_loop_compose_router",
    "register_chase_twin_analysis_loop_compose_routes",
]

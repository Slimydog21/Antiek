"""Registerable HTTP surface for research interrogation subagent chase compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_interrogation_subagent_chase_compose import (
    ResearchInterrogationSubagentChaseComposeError,
    compose_research_interrogation_subagent_chase,
)

research_interrogation_subagent_chase_compose_router = APIRouter(
    prefix="/research/interrogation-subagent-chase",
    tags=["research-interrogation-subagent-chase-compose"],
)


class QuestionBody(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    priority: int | None = None


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
    mark_for_twin_record: bool = Field(default=False, strict=True)
    operator_ack: bool = Field(strict=True)


@research_interrogation_subagent_chase_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_research_interrogation_subagent_chase(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            questions=[q.model_dump() for q in req.questions],
            chase_mode=req.chase_mode,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            selected_model_id=req.selected_model_id,
            source_families=req.source_families,
            mark_for_twin_record=req.mark_for_twin_record,
            operator_ack=req.operator_ack,
        )
    except ResearchInterrogationSubagentChaseComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_research_interrogation_subagent_chase_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(research_interrogation_subagent_chase_compose_router)


__all__ = [
    "research_interrogation_subagent_chase_compose_router",
    "register_research_interrogation_subagent_chase_compose_routes",
]

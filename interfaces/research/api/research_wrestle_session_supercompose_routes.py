"""Registerable HTTP surface for research wrestle session super-compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_wrestle_session_supercompose import (
    ResearchWrestleSessionSupercomposeError,
    compose_research_wrestle_session,
)

research_wrestle_session_supercompose_router = APIRouter(
    prefix="/research/wrestle-session",
    tags=["research-wrestle-session-supercompose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    floating_instance_count: int = Field(ge=0)
    completed_floating_count: int = Field(ge=0)
    twin_insight_count: int = Field(ge=0)
    twin_question_count: int = Field(ge=0)
    open_question_count: int = Field(ge=0)
    source_family_count: int = Field(ge=0)
    citation_pack_ready: bool = Field(strict=True)
    quality_overall: float | None = Field(default=None)
    quality_floor: float | None = Field(default=None)
    would_exceed: bool | None = Field(default=None)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    operator_override: bool = Field(default=False, strict=True)


@research_wrestle_session_supercompose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_research_wrestle_session(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            floating_instance_count=req.floating_instance_count,
            completed_floating_count=req.completed_floating_count,
            twin_insight_count=req.twin_insight_count,
            twin_question_count=req.twin_question_count,
            open_question_count=req.open_question_count,
            source_family_count=req.source_family_count,
            citation_pack_ready=req.citation_pack_ready,
            quality_overall=req.quality_overall,
            quality_floor=req.quality_floor,
            would_exceed=req.would_exceed,
            preferred_view_mode=req.preferred_view_mode,
            operator_override=req.operator_override,
        )
    except ResearchWrestleSessionSupercomposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_research_wrestle_session_supercompose_routes(app: FastAPI) -> None:
    app.include_router(research_wrestle_session_supercompose_router)


__all__ = [
    "research_wrestle_session_supercompose_router",
    "register_research_wrestle_session_supercompose_routes",
]

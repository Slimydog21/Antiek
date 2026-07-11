"""Registerable HTTP surface for research workstation full-loop super-compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_workstation_full_loop_supercompose import (
    ResearchWorkstationFullLoopSupercomposeError,
    compose_research_workstation_full_loop,
)

research_workstation_full_loop_supercompose_router = APIRouter(
    prefix="/research/full-loop",
    tags=["research-workstation-full-loop-supercompose"],
)


class WrestleBody(BaseModel):
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
    quality_overall: float | None = None
    quality_floor: float | None = None
    would_exceed: bool | None = None
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    operator_override: bool = Field(default=False, strict=True)


class SourceAttachBody(BaseModel):
    model_config = {"extra": "forbid"}

    attach_ready: bool = Field(strict=True)
    remote_fetched: Literal[False] = False
    source_count: int = Field(ge=0)


class ViewModeBody(BaseModel):
    model_config = {"extra": "forbid"}

    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    floating_instance_count: int = Field(ge=0)


class BudgetBody(BaseModel):
    model_config = {"extra": "forbid"}

    would_exceed: bool | None = None
    selected_model_id: str | None = Field(default=None, max_length=128)
    operator_override: bool | None = Field(default=None)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    wrestle: WrestleBody
    source_attach: SourceAttachBody
    view_mode: ViewModeBody
    budget: BudgetBody


@research_workstation_full_loop_supercompose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_research_workstation_full_loop(
            wrestle=req.wrestle.model_dump(),
            source_attach=req.source_attach.model_dump(),
            view_mode=req.view_mode.model_dump(),
            budget=req.budget.model_dump(),
        )
    except ResearchWorkstationFullLoopSupercomposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_research_workstation_full_loop_supercompose_routes(
    app: FastAPI,
) -> None:
    app.include_router(research_workstation_full_loop_supercompose_router)


__all__ = [
    "research_workstation_full_loop_supercompose_router",
    "register_research_workstation_full_loop_supercompose_routes",
]

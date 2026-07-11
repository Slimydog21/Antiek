"""Registerable HTTP surface for research workstation session compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.research_workstation_session_compose import (
    ResearchWorkstationSessionComposeError,
    compose_research_workstation_session,
)

research_workstation_session_compose_router = APIRouter(
    prefix="/research/workstation-session",
    tags=["research-workstation-session-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    floating_instance_count: int = Field(ge=0)
    twin_bound: bool = Field(strict=True)
    source_family_count: int = Field(ge=0)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    cohesive_pack_ready: bool | None = Field(default=None)
    operator_override: bool | None = Field(default=None)


@research_workstation_session_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        snap = compose_research_workstation_session(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            floating_instance_count=req.floating_instance_count,
            twin_bound=req.twin_bound,
            source_family_count=req.source_family_count,
            quality_overall=req.quality_overall,
            quality_floor=req.quality_floor,
            would_exceed=req.would_exceed,
            cohesive_pack_ready=req.cohesive_pack_ready,
            operator_override=req.operator_override,
        )
    except ResearchWorkstationSessionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return snap.to_dict()


def register_research_workstation_session_compose_routes(app: FastAPI) -> None:
    app.include_router(research_workstation_session_compose_router)


__all__ = [
    "research_workstation_session_compose_router",
    "register_research_workstation_session_compose_routes",
]

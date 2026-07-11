"""Registerable HTTP surface for floating multi-select collective cohesive compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)

floating_multi_select_collective_cohesive_compose_router = APIRouter(
    prefix="/research/floating-multi-select-collective-cohesive",
    tags=["floating-multi-select-collective-cohesive-compose"],
)


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    highlight: str | None = Field(default=None, max_length=8000)
    prior_prompt: str | None = Field(default=None, max_length=8000)
    context: list[str] | None = None
    findings: list[str] | None = None
    live_dispatched: Literal[False] | None = None
    merge_executed: Literal[False] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=2)
    selected_instance_ids: list[str] = Field(min_length=2)
    pack_mode: Literal[
        "cohesive_prompt", "collective_pack", "cohesive_plus_analysis"
    ]
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    operator_ack: bool = Field(strict=True)
    extra_context: list[str] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    extra_findings: list[str] | None = None


@floating_multi_select_collective_cohesive_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_multi_select_collective_cohesive(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            members=[m.model_dump() for m in req.members],
            selected_instance_ids=req.selected_instance_ids,
            pack_mode=req.pack_mode,
            cohesive_prompt=req.cohesive_prompt,
            operator_ack=req.operator_ack,
            extra_context=req.extra_context,
            analysis_kind=req.analysis_kind,
            extra_findings=req.extra_findings,
        )
    except FloatingMultiSelectCollectiveCohesiveComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_multi_select_collective_cohesive_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        floating_multi_select_collective_cohesive_compose_router
    )


__all__ = [
    "floating_multi_select_collective_cohesive_compose_router",
    "register_floating_multi_select_collective_cohesive_compose_routes",
]

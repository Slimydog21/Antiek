"""Registerable HTTP surface for collective floating cohesive prompt packs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.collective_floating_cohesive_prompt import (
    CollectiveFloatingCohesivePromptError,
    build_collective_floating_cohesive_prompt,
)

collective_floating_cohesive_prompt_router = APIRouter(
    prefix="/research/collective-cohesive-prompt",
    tags=["collective-floating-cohesive-prompt"],
)


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    highlight: str | None = Field(default=None, max_length=4000)
    prior_prompt: str | None = Field(default=None, max_length=4000)
    context: list[str] | None = None


class BuildRequest(BaseModel):
    model_config = {"extra": "forbid"}

    members: list[MemberBody] = Field(min_length=2)
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    operator_ack: bool = Field(strict=True)
    extra_context: list[str] | None = None


@collective_floating_cohesive_prompt_router.post("/build")
def post_build(req: BuildRequest) -> dict[str, Any]:
    try:
        intent = build_collective_floating_cohesive_prompt(
            [m.model_dump() for m in req.members],
            cohesive_prompt=req.cohesive_prompt,
            operator_ack=req.operator_ack,
            extra_context=req.extra_context,
        )
    except CollectiveFloatingCohesivePromptError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return intent.to_dict()


def register_collective_floating_cohesive_prompt_routes(app: FastAPI) -> None:
    app.include_router(collective_floating_cohesive_prompt_router)


__all__ = [
    "collective_floating_cohesive_prompt_router",
    "register_collective_floating_cohesive_prompt_routes",
]

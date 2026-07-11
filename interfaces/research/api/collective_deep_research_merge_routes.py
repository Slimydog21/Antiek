"""Registerable HTTP surface for collective analysis merge intents."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.collective_deep_research_merge import (
    CollectiveAnalysisMergeError,
    propose_collective_analysis_merge,
)

collective_deep_research_merge_router = APIRouter(
    prefix="/research/collective-analysis",
    tags=["collective-deep-research-merge"],
)


class InstanceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["completed", "open", "proposed", "closed"]
    findings: list[str] | None = None


class MergeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    instances: list[InstanceBody] = Field(min_length=2)
    kind: Literal["draft_analysis", "full_analysis"]
    operator_ack: bool = Field(strict=True)
    extra_findings: list[str] | None = None


@collective_deep_research_merge_router.post("/merge")
def post_merge(req: MergeRequest) -> dict[str, Any]:
    try:
        intent = propose_collective_analysis_merge(
            [i.model_dump() for i in req.instances],
            kind=req.kind,
            operator_ack=req.operator_ack,
            extra_findings=req.extra_findings,
        )
    except CollectiveAnalysisMergeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return intent.to_dict()


def register_collective_deep_research_merge_routes(app: FastAPI) -> None:
    app.include_router(collective_deep_research_merge_router)


__all__ = [
    "collective_deep_research_merge_router",
    "register_collective_deep_research_merge_routes",
]

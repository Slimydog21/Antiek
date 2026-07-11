"""Registerable HTTP surface for twin chase analysis feed compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)

twin_chase_analysis_feed_compose_router = APIRouter(
    prefix="/research/twin-chase-analysis-feed",
    tags=["twin-chase-analysis-feed-compose"],
)


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    findings: list[FindingBody] = Field(min_length=1)
    analysis_excerpt: str | None = Field(default=None, max_length=8000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=False, strict=True)
    operator_ack: bool = Field(strict=True)


@twin_chase_analysis_feed_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_chase_analysis_feed(
            parent_asset_id=req.parent_asset_id,
            session_id=req.session_id,
            findings=[f.model_dump() for f in req.findings],
            analysis_excerpt=req.analysis_excerpt,
            existing_twin_asset_id=req.existing_twin_asset_id,
            mark_for_prompt_context=req.mark_for_prompt_context,
            operator_ack=req.operator_ack,
        )
    except TwinChaseAnalysisFeedComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_chase_analysis_feed_compose_routes(app: FastAPI) -> None:
    app.include_router(twin_chase_analysis_feed_compose_router)


__all__ = [
    "twin_chase_analysis_feed_compose_router",
    "register_twin_chase_analysis_feed_compose_routes",
]

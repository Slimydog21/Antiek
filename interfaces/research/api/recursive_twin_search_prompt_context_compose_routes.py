"""Registerable HTTP surface for recursive twin search prompt context pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.recursive_twin_search_prompt_context_compose import (
    RecursiveTwinSearchPromptContextComposeError,
    compose_recursive_twin_search_prompt_context,
)

recursive_twin_search_prompt_context_compose_router = APIRouter(
    prefix="/research/recursive-twin-search-prompt-context",
    tags=["recursive-twin-search-prompt-context-compose"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, max_length=512)


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=50000)
    twin_records: list[TwinRecordBody]
    search_query: str = Field(min_length=1, max_length=2000)
    user_prompt: str = Field(min_length=1, max_length=8000)
    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None
    search_limit: int | None = Field(default=None, ge=1)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


@recursive_twin_search_prompt_context_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_search_prompt_context(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            source_excerpt=req.source_excerpt,
            twin_records=[t.model_dump() for t in req.twin_records],
            search_query=req.search_query,
            user_prompt=req.user_prompt,
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            operator_ack=req.operator_ack,
            existing_twin_asset_id=req.existing_twin_asset_id,
            focus_questions=req.focus_questions,
            search_limit=req.search_limit,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
        )
    except RecursiveTwinSearchPromptContextComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_search_prompt_context_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(recursive_twin_search_prompt_context_compose_router)


__all__ = [
    "recursive_twin_search_prompt_context_compose_router",
    "register_recursive_twin_search_prompt_context_compose_routes",
]

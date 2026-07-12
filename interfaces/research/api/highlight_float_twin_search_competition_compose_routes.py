"""Registerable HTTP surface for highlight float → twin search competition pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_routes import (
    CompetitionPackBody,
    TwinRecordBody,
)
from substrate.highlight_float_twin_search_competition_compose import (
    HighlightFloatTwinSearchCompetitionComposeError,
    compose_highlight_float_twin_search_competition,
)

highlight_float_twin_search_competition_compose_router = APIRouter(
    prefix="/research/highlight-float-twin-search-competition",
    tags=["highlight-float-twin-search-competition-compose"],
)

SourceFamily = Literal["arxiv", "substack", "openalex", "web", "custom"]


class HighlightBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    would_exceed: bool | None = Field(default=None, strict=True)
    prompt: str | None = Field(default=None, max_length=8000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    operator_override: bool | None = Field(default=None, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=256)
    source_families: list[SourceFamily] | None = None


class TwinSearchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    competition_pack: CompetitionPackBody
    search_query: str | None = Field(default=None, max_length=2000)
    extra_twin_records: list[TwinRecordBody] | None = None
    search_limit: int | None = Field(default=None, ge=1, le=500)
    min_parents_for_merge: int | None = Field(default=None, ge=1, le=100)
    search_pack_id: str | None = Field(default=None, max_length=256)
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    highlight: HighlightBody
    twin_search_pack: TwinSearchPackBody
    operator_ack: bool = Field(strict=True)
    seed_search_from_highlight: bool = Field(default=True, strict=True)
    require_both: bool = Field(default=True, strict=True)


@highlight_float_twin_search_competition_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_highlight_float_twin_search_competition(
            highlight=req.highlight.model_dump(),
            twin_search_pack=req.twin_search_pack.model_dump(),
            operator_ack=req.operator_ack,
            seed_search_from_highlight=req.seed_search_from_highlight,
            require_both=req.require_both,
        )
    except HighlightFloatTwinSearchCompetitionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_highlight_float_twin_search_competition_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(highlight_float_twin_search_competition_compose_router)


__all__ = [
    "highlight_float_twin_search_competition_compose_router",
    "register_highlight_float_twin_search_competition_compose_routes",
]

"""Registerable HTTP surface for twin search over competition DR ND weekly pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_nd_shadow_weekly_marketplace_compose_routes import (
    CompetitionBody,
    NdWeeklyBody,
)
from substrate.twin_search_competition_dr_nd_shadow_weekly_marketplace_compose import (
    TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError,
    compose_twin_search_competition_dr_nd_shadow_weekly_marketplace,
)

twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_router = APIRouter(
    prefix="/research/twin-search-competition-dr-nd-shadow-weekly-marketplace",
    tags=["twin-search-competition-dr-nd-shadow-weekly-marketplace-compose"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, max_length=512)


class CompetitionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_weekly: NdWeeklyBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition_pack: CompetitionPackBody
    search_query: str = Field(min_length=1, max_length=2000)
    operator_ack: bool = Field(strict=True)
    extra_twin_records: list[TwinRecordBody] | None = None
    search_limit: int | None = Field(default=None, ge=1, le=500)
    min_parents_for_merge: int | None = Field(default=None, ge=1, le=100)
    search_pack_id: str | None = Field(default=None, max_length=256)
    require_both: bool = Field(default=True, strict=True)


@twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_search_competition_dr_nd_shadow_weekly_marketplace(
            competition_pack=req.competition_pack.model_dump(),
            search_query=req.search_query,
            operator_ack=req.operator_ack,
            extra_twin_records=(
                [r.model_dump() for r in req.extra_twin_records]
                if req.extra_twin_records is not None
                else None
            ),
            search_limit=req.search_limit,
            min_parents_for_merge=req.min_parents_for_merge,
            search_pack_id=req.search_pack_id,
            require_both=req.require_both,
        )
    except TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_router
    )


__all__ = [
    "twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_router",
    "register_twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_routes",
]

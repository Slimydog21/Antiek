"""Registerable HTTP surface for competition DR + ND shadow weekly marketplace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_quality_source_pack_compose_routes import (
    CitationBody,
    DecisionBody,
)
from interfaces.research.api.nd_shadow_antiek_bench_weekly_marketplace_compose_routes import (
    NdShadowBody,
    WeeklyMarketBody,
)
from substrate.competition_dr_nd_shadow_weekly_marketplace_compose import (
    CompetitionDrNdShadowWeeklyMarketplaceComposeError,
    compose_competition_dr_nd_shadow_weekly_marketplace,
)

competition_dr_nd_shadow_weekly_marketplace_compose_router = APIRouter(
    prefix="/research/competition-dr-nd-shadow-weekly-marketplace",
    tags=["competition-dr-nd-shadow-weekly-marketplace-compose"],
)


class CompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody]
    requested_families: list[str] = Field(min_length=1)
    citations: list[CitationBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = Field(default=None, strict=True)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)
    require_no_behind_gaps: bool | None = Field(default=None, strict=True)
    filter_to_selected_families: bool | None = Field(
        default=None, strict=True
    )


class NdWeeklyBody(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    weekly_market: WeeklyMarketBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_weekly: NdWeeklyBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@competition_dr_nd_shadow_weekly_marketplace_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_nd_shadow_weekly_marketplace(
            competition=req.competition.model_dump(),
            nd_weekly=req.nd_weekly.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrNdShadowWeeklyMarketplaceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_nd_shadow_weekly_marketplace_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_nd_shadow_weekly_marketplace_compose_router
    )


__all__ = [
    "competition_dr_nd_shadow_weekly_marketplace_compose_router",
    "register_competition_dr_nd_shadow_weekly_marketplace_compose_routes",
]

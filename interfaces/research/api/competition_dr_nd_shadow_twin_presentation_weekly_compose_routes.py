"""Registerable HTTP surface for competition DR over ND shadow twin presentation weekly."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_quality_source_pack_compose_routes import (
    CitationBody,
    DecisionArea,
    DecisionBody,
    CitationFamily,
)
from interfaces.research.api.nd_shadow_recursive_twin_presentation_weekly_source_attach_compose_routes import (
    NdShadowBody,
    TwinPresentationBody,
)
from substrate.competition_dr_nd_shadow_twin_presentation_weekly_compose import (
    CompetitionDrNdShadowTwinPresentationWeeklyComposeError,
    compose_competition_dr_nd_shadow_twin_presentation_weekly,
)

competition_dr_nd_shadow_twin_presentation_weekly_compose_router = APIRouter(
    prefix="/research/competition-dr-nd-shadow-twin-presentation-weekly",
    tags=["competition-dr-nd-shadow-twin-presentation-weekly-compose"],
)


class CompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody]
    focus_areas: list[DecisionArea] | None = None
    requested_families: list[CitationFamily] = Field(min_length=1)
    citations: list[CitationBody]
    filter_to_selected_families: bool | None = Field(default=None, strict=True)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_override: bool | None = Field(default=None, strict=True)
    require_no_behind_gaps: bool | None = Field(default=None, strict=True)


class NdPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    twin_presentation: TwinPresentationBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_pack: NdPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@competition_dr_nd_shadow_twin_presentation_weekly_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_nd_shadow_twin_presentation_weekly(
            competition=req.competition.model_dump(),
            nd_pack=req.nd_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrNdShadowTwinPresentationWeeklyComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_nd_shadow_twin_presentation_weekly_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_nd_shadow_twin_presentation_weekly_compose_router
    )


__all__ = [
    "competition_dr_nd_shadow_twin_presentation_weekly_compose_router",
    "register_competition_dr_nd_shadow_twin_presentation_weekly_compose_routes",
]

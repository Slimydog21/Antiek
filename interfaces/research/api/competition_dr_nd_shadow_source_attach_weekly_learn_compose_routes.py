"""Registerable HTTP surface for competition DR + ND shadow source-attach weekly learn."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.nd_shadow_source_attach_weekly_learn_twin_presentation_compose_routes import (
    NdShadowBody,
    SourcePackBody,
)
from substrate.competition_dr_nd_shadow_source_attach_weekly_learn_compose import (
    CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError,
    compose_competition_dr_nd_shadow_source_attach_weekly_learn,
)

competition_dr_nd_shadow_source_attach_weekly_learn_compose_router = APIRouter(
    prefix="/research/competition-dr-nd-shadow-source-attach-weekly-learn",
    tags=["competition-dr-nd-shadow-source-attach-weekly-learn-compose"],
)

DecisionArea = Literal[
    "source_acquisition",
    "citation_grounding",
    "multi_agent_orchestration",
    "budget_controls",
    "html_native_reading",
    "model_routing",
    "evaluation_harness",
    "unattended_swarm",
]
GapStatus = Literal["ahead", "parity", "behind", "unknown"]
CitationFamily = Literal["arxiv", "substack", "openalex", "web", "custom"]


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    competitor: str = Field(min_length=1, max_length=256)
    area: DecisionArea
    decision_summary: str = Field(min_length=1, max_length=4000)
    antiek_status: GapStatus
    residual: str | None = Field(default=None, max_length=2000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: CitationFamily
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=256)
    url: str | None = Field(default=None, max_length=2000)
    year: int | None = None
    authors: str | None = Field(default=None, max_length=2000)


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
    source_pack: SourcePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_pack: NdPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@competition_dr_nd_shadow_source_attach_weekly_learn_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_nd_shadow_source_attach_weekly_learn(
            competition=req.competition.model_dump(),
            nd_pack=req.nd_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_nd_shadow_source_attach_weekly_learn_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_nd_shadow_source_attach_weekly_learn_compose_router
    )


__all__ = [
    "competition_dr_nd_shadow_source_attach_weekly_learn_compose_router",
    "register_competition_dr_nd_shadow_source_attach_weekly_learn_compose_routes",
]

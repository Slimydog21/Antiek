"""Registerable HTTP surface for competition DR + MO unattended source-attach rewrite."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.mo_unattended_source_attach_antiek_bench_rewrite_compose_routes import (
    MoBody,
    ResearchPackBody,
)
from substrate.competition_dr_mo_unattended_source_attach_rewrite_compose import (
    CompetitionDrMoUnattendedSourceAttachRewriteComposeError,
    compose_competition_dr_mo_unattended_source_attach_rewrite,
)

competition_dr_mo_unattended_source_attach_rewrite_compose_router = APIRouter(
    prefix="/research/competition-dr-mo-unattended-source-attach-rewrite",
    tags=["competition-dr-mo-unattended-source-attach-rewrite-compose"],
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


class MoPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    research_pack: ResearchPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    mo_pack: MoPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@competition_dr_mo_unattended_source_attach_rewrite_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_mo_unattended_source_attach_rewrite(
            competition=req.competition.model_dump(),
            mo_pack=req.mo_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrMoUnattendedSourceAttachRewriteComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_mo_unattended_source_attach_rewrite_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_mo_unattended_source_attach_rewrite_compose_router
    )


__all__ = [
    "competition_dr_mo_unattended_source_attach_rewrite_compose_router",
    "register_competition_dr_mo_unattended_source_attach_rewrite_compose_routes",
    "CompetitionBody",
    "MoPackBody",
]

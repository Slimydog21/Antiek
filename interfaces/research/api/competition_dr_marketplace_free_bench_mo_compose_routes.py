"""Registerable HTTP surface for competition DR + free marketplace bench MO."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.marketplace_free_antiek_bench_recommend_mo_compose_routes import (
    BenchMoBody,
    MarketBody,
)
from substrate.competition_dr_marketplace_free_bench_mo_compose import (
    CompetitionDrMarketplaceFreeBenchMoComposeError,
    compose_competition_dr_marketplace_free_bench_mo,
)

competition_dr_marketplace_free_bench_mo_compose_router = APIRouter(
    prefix="/research/competition-dr-marketplace-free-bench-mo",
    tags=["competition-dr-marketplace-free-bench-mo-compose"],
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


class FreePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    bench_mo: BenchMoBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    free_pack: FreePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@competition_dr_marketplace_free_bench_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_marketplace_free_bench_mo(
            competition=req.competition.model_dump(),
            free_pack=req.free_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrMarketplaceFreeBenchMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_marketplace_free_bench_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_marketplace_free_bench_mo_compose_router
    )


__all__ = [
    "competition_dr_marketplace_free_bench_mo_compose_router",
    "register_competition_dr_marketplace_free_bench_mo_compose_routes",
]

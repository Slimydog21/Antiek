"""Registerable HTTP surface for marketplace → highlight twin MO pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_highlight_float_recursive_twin_mo_compose import (
    MarketplaceHighlightFloatRecursiveTwinMoComposeError,
    compose_marketplace_highlight_float_recursive_twin_mo,
)

marketplace_highlight_float_recursive_twin_mo_compose_router = APIRouter(
    prefix="/research/marketplace-highlight-float-recursive-twin-mo",
    tags=["marketplace-highlight-float-recursive-twin-mo-compose"],
)

Area = Literal[
    "source_acquisition",
    "citation_grounding",
    "multi_agent_orchestration",
    "budget_controls",
    "html_native_reading",
    "model_routing",
    "evaluation_harness",
    "unattended_swarm",
]
Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question"]


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=128)
    purchase_html_projection_sha: str | None = Field(
        default=None, max_length=128
    )
    port_requested: bool = Field(strict=True)
    purchase_ack: bool = Field(strict=True)
    list_price_usd: float | None = Field(default=None, ge=0)
    approved_spend_usd: float | None = Field(default=None, ge=0)
    remaining_budget_usd: float | None = Field(default=None, ge=0)
    view_requested: bool = Field(strict=True)
    twin_findings: list[FindingBody] | None = None
    mark_for_prompt_context: bool | None = Field(default=None, strict=True)


class HighlightSurfaceBody(BaseModel):
    model_config = {"extra": "forbid"}

    highlight: str | None = Field(default=None, max_length=8000)
    gated: bool = Field(strict=True)
    would_exceed: bool | None = None
    surface_action: Literal[
        "spawn_only", "spawn_and_tray", "tray_merge", "fullscreen"
    ]
    source_families: list[Family] | None = None
    session_id: str | None = Field(default=None, max_length=256)
    parent_asset_id: str | None = Field(default=None, max_length=256)


class MoGoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: int = Field(ge=1, le=24 * 60)
    goals: list[MoGoalBody] = Field(min_length=1)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)
    usd_per_hour: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)


class ModelOptionBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class DecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelOptionBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)


class CompDecisionBody(BaseModel):
    model_config = {"extra": "forbid"}

    competitor: str = Field(min_length=1, max_length=256)
    area: Area
    decision_summary: str = Field(min_length=1, max_length=4000)
    antiek_status: Literal["ahead", "parity", "behind", "unknown"]
    residual: str | None = Field(default=None, max_length=4000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)


class CompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[CompDecisionBody] = Field(min_length=1)
    requested_families: list[Family] = Field(min_length=1)
    citations: list[CitationBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    search_query: str = Field(min_length=1, max_length=2000)


class CompetitionViewBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=128)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    competition: CompetitionBody
    claimed_format: str | None = Field(default=None, max_length=64)


class ResearchInnerBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    competition_view: CompetitionViewBody


class MoCompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    research: ResearchInnerBody
    parent_asset_id: str | None = Field(default=None, max_length=256)


class ResearchBody(BaseModel):
    model_config = {"extra": "forbid"}

    highlight_surface: HighlightSurfaceBody
    mo_competition: MoCompetitionBody


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    research: ResearchBody
    operator_ack: bool = Field(strict=True)
    seed_highlight_from_title: bool = Field(default=True, strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_highlight_float_recursive_twin_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_highlight_float_recursive_twin_mo(
            market=req.market.model_dump(),
            research=req.research.model_dump(),
            operator_ack=req.operator_ack,
            seed_highlight_from_title=req.seed_highlight_from_title,
            require_both=req.require_both,
        )
    except MarketplaceHighlightFloatRecursiveTwinMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_highlight_float_recursive_twin_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_highlight_float_recursive_twin_mo_compose_router
    )


__all__ = [
    "marketplace_highlight_float_recursive_twin_mo_compose_router",
    "register_marketplace_highlight_float_recursive_twin_mo_compose_routes",
]

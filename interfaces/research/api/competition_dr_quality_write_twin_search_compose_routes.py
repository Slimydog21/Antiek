"""Registerable HTTP surface for competition quality write + twin search."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.competition_dr_quality_write_twin_search_compose import (
    CompetitionDrQualityWriteTwinSearchComposeError,
    compose_competition_dr_quality_write_twin_search,
)

competition_dr_quality_write_twin_search_compose_router = APIRouter(
    prefix="/research/competition-dr-quality-write-twin-search",
    tags=["competition-dr-quality-write-twin-search-compose"],
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


class DecisionBody(BaseModel):
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


class TwinSliceBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class SlotBody(BaseModel):
    model_config = {"extra": "forbid"}

    slot_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    findings: list[str] | None = None
    body: str | None = Field(default=None, max_length=8000)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, max_length=512)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody] = Field(min_length=1)
    requested_families: list[Family] = Field(min_length=1)
    citations: list[CitationBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_ack: bool = Field(strict=True)
    search_query: str = Field(min_length=1, max_length=2000)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)
    require_no_behind_gaps: bool = Field(default=False, strict=True)
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    twin_slices: list[TwinSliceBody] | None = None
    chase_slots: list[SlotBody] | None = None
    base_draft_html: str | None = Field(default=None, max_length=100000)
    require_both_with_write: bool = Field(default=True, strict=True)
    extra_twin_records: list[TwinRecordBody] | None = None
    search_limit: int | None = Field(default=None, ge=1, le=200)
    min_parents_for_merge: int | None = Field(default=None, ge=2, le=50)
    search_pack_id: str | None = Field(default=None, max_length=256)
    require_both_with_search: bool = Field(default=True, strict=True)


@competition_dr_quality_write_twin_search_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_quality_write_twin_search(
            session_id=req.session_id,
            draft_id=req.draft_id,
            parent_asset_id=req.parent_asset_id,
            competitor_decisions=[
                d.model_dump() for d in req.competitor_decisions
            ],
            requested_families=list(req.requested_families),
            citations=[c.model_dump() for c in req.citations],
            quality_overall=req.quality_overall,
            would_exceed=req.would_exceed,
            operator_ack=req.operator_ack,
            search_query=req.search_query,
            quality_floor=req.quality_floor,
            operator_override=req.operator_override,
            require_no_behind_gaps=req.require_no_behind_gaps,
            analysis_kind=req.analysis_kind,
            twin_slices=(
                [s.model_dump() for s in req.twin_slices]
                if req.twin_slices is not None
                else None
            ),
            chase_slots=(
                [s.model_dump() for s in req.chase_slots]
                if req.chase_slots is not None
                else None
            ),
            base_draft_html=req.base_draft_html,
            require_both_with_write=req.require_both_with_write,
            extra_twin_records=(
                [r.model_dump() for r in req.extra_twin_records]
                if req.extra_twin_records is not None
                else None
            ),
            search_limit=req.search_limit,
            min_parents_for_merge=req.min_parents_for_merge,
            search_pack_id=req.search_pack_id,
            require_both_with_search=req.require_both_with_search,
        )
    except CompetitionDrQualityWriteTwinSearchComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_quality_write_twin_search_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_quality_write_twin_search_compose_router
    )


__all__ = [
    "competition_dr_quality_write_twin_search_compose_router",
    "register_competition_dr_quality_write_twin_search_compose_routes",
]

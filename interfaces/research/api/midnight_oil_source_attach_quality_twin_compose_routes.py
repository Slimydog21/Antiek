"""Registerable HTTP surface for MO source attach quality twin compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil_source_attach_quality_twin_compose import (
    MidnightOilSourceAttachQualityTwinComposeError,
    compose_midnight_oil_source_attach_quality_twin,
)

midnight_oil_source_attach_quality_twin_compose_router = APIRouter(
    prefix="/research/midnight-oil-source-attach-quality-twin",
    tags=["midnight-oil-source-attach-quality-twin-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)
    html_fragment: str | None = Field(default=None, max_length=100000)


class CitationBody(BaseModel):
    model_config = {"extra": "forbid"}

    citation_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)
    year: int | None = None
    authors: str | None = Field(default=None, max_length=2000)


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: int = Field(ge=1, le=10080)
    goals: list[GoalBody] = Field(min_length=1)
    usd_per_hour: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)
    brief_dispatch_ready: bool | None = Field(default=None, strict=True)
    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    citations: list[CitationBody] | None = None
    derive_citations_from_sources: bool = Field(default=True, strict=True)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)
    require_both: bool = Field(default=True, strict=True)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    analysis_excerpt: str | None = Field(default=None, max_length=8000)
    mark_for_prompt_context: bool = Field(default=True, strict=True)
    twin_findings: list[FindingBody] | None = None
    require_both_with_twin: bool = Field(default=True, strict=True)


@midnight_oil_source_attach_quality_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_midnight_oil_source_attach_quality_twin(
            operator_id=req.operator_id,
            work_minutes=req.work_minutes,
            goals=[g.model_dump() for g in req.goals],
            usd_per_hour=req.usd_per_hour,
            approved_ceiling_usd=req.approved_ceiling_usd,
            operator_ack=req.operator_ack,
            unattended_ack=req.unattended_ack,
            spend_consent=req.spend_consent,
            brief_dispatch_ready=req.brief_dispatch_ready,
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            requested_families=list(req.requested_families),
            sources=[s.model_dump() for s in req.sources],
            quality_overall=req.quality_overall,
            would_exceed=req.would_exceed,
            citations=(
                [c.model_dump() for c in req.citations]
                if req.citations is not None
                else None
            ),
            derive_citations_from_sources=req.derive_citations_from_sources,
            quality_floor=req.quality_floor,
            operator_override=req.operator_override,
            require_both=req.require_both,
            existing_twin_asset_id=req.existing_twin_asset_id,
            analysis_excerpt=req.analysis_excerpt,
            mark_for_prompt_context=req.mark_for_prompt_context,
            twin_findings=(
                [f.model_dump() for f in req.twin_findings]
                if req.twin_findings is not None
                else None
            ),
            require_both_with_twin=req.require_both_with_twin,
        )
    except MidnightOilSourceAttachQualityTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_midnight_oil_source_attach_quality_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(midnight_oil_source_attach_quality_twin_compose_router)


__all__ = [
    "midnight_oil_source_attach_quality_twin_compose_router",
    "register_midnight_oil_source_attach_quality_twin_compose_routes",
]

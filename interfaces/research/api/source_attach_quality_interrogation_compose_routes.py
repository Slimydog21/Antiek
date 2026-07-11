"""Registerable HTTP surface for source attach quality interrogation compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.source_attach_quality_interrogation_compose import (
    SourceAttachQualityInterrogationComposeError,
    compose_source_attach_quality_interrogation,
)

source_attach_quality_interrogation_compose_router = APIRouter(
    prefix="/research/source-attach-quality-interrogation",
    tags=["source-attach-quality-interrogation-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


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


class QuestionBody(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    priority: int | None = None


class ModelBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class RecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: Literal["insight", "question", "data", "claim"]
    body: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = Field(default=None, max_length=256)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_ack: bool = Field(strict=True)
    citations: list[CitationBody] | None = None
    derive_citations_from_sources: bool = Field(default=True, strict=True)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)
    questions: list[QuestionBody] = Field(min_length=1)
    chase_mode: Literal[
        "single_question", "swarm_fanout", "collective_merge_after"
    ]
    prior_records: list[RecordBody] | None = None
    user_prompt: str = Field(min_length=1, max_length=8000)
    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    focus_task: str | None = Field(default=None, max_length=256)
    require_both: bool = Field(default=True, strict=True)


@source_attach_quality_interrogation_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_attach_quality_interrogation(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            requested_families=list(req.requested_families),
            sources=[s.model_dump() for s in req.sources],
            quality_overall=req.quality_overall,
            would_exceed=req.would_exceed,
            operator_ack=req.operator_ack,
            citations=(
                [c.model_dump() for c in req.citations]
                if req.citations is not None
                else None
            ),
            derive_citations_from_sources=req.derive_citations_from_sources,
            quality_floor=req.quality_floor,
            operator_override=req.operator_override,
            questions=[q.model_dump() for q in req.questions],
            chase_mode=req.chase_mode,
            prior_records=(
                [r.model_dump() for r in req.prior_records]
                if req.prior_records is not None
                else None
            ),
            user_prompt=req.user_prompt,
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            focus_task=req.focus_task,
            require_both=req.require_both,
        )
    except SourceAttachQualityInterrogationComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_attach_quality_interrogation_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(source_attach_quality_interrogation_compose_router)


__all__ = [
    "source_attach_quality_interrogation_compose_router",
    "register_source_attach_quality_interrogation_compose_routes",
]

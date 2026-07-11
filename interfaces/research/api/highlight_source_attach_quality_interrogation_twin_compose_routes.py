"""Registerable HTTP surface for highlight source attach interrogation twin."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.highlight_source_attach_quality_interrogation_twin_compose import (
    HighlightSourceAttachQualityInterrogationTwinComposeError,
    compose_highlight_source_attach_quality_interrogation_twin,
)

highlight_source_attach_quality_interrogation_twin_compose_router = APIRouter(
    prefix="/research/highlight-source-attach-quality-interrogation-twin",
    tags=["highlight-source-attach-quality-interrogation-twin-compose"],
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


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    would_exceed: bool | None = None
    operator_ack: bool = Field(strict=True)
    session_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    questions: list[QuestionBody] = Field(min_length=1)
    chase_mode: Literal[
        "single_question", "swarm_fanout", "collective_merge_after"
    ]
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    prompt: str | None = Field(default=None, max_length=8000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    operator_override: bool | None = Field(default=None, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=256)
    source_families: list[Family] | None = None
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    user_prompt: str | None = Field(default=None, max_length=8000)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    require_both: bool = Field(default=True, strict=True)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    analysis_excerpt: str | None = Field(default=None, max_length=8000)
    mark_for_prompt_context: bool = Field(default=True, strict=True)
    twin_findings: list[FindingBody] | None = None
    require_both_with_twin: bool = Field(default=True, strict=True)


@highlight_source_attach_quality_interrogation_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_highlight_source_attach_quality_interrogation_twin(
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            gated=req.gated,
            would_exceed=req.would_exceed,
            operator_ack=req.operator_ack,
            session_id=req.session_id,
            requested_families=list(req.requested_families),
            sources=[s.model_dump() for s in req.sources],
            quality_overall=req.quality_overall,
            questions=[q.model_dump() for q in req.questions],
            chase_mode=req.chase_mode,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            prompt=req.prompt,
            preferred_view_mode=req.preferred_view_mode,
            operator_override=req.operator_override,
            selected_model_id=req.selected_model_id,
            source_families=(
                list(req.source_families)
                if req.source_families is not None
                else None
            ),
            quality_floor=req.quality_floor,
            user_prompt=req.user_prompt,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
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
    except HighlightSourceAttachQualityInterrogationTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_highlight_source_attach_quality_interrogation_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        highlight_source_attach_quality_interrogation_twin_compose_router
    )


__all__ = [
    "highlight_source_attach_quality_interrogation_twin_compose_router",
    "register_highlight_source_attach_quality_interrogation_twin_compose_routes",
]

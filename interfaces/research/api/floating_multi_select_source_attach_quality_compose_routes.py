"""Registerable HTTP surface for floating multi-select + source attach quality."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_multi_select_source_attach_quality_compose import (
    FloatingMultiSelectSourceAttachQualityComposeError,
    compose_floating_multi_select_source_attach_quality,
)

floating_multi_select_source_attach_quality_compose_router = APIRouter(
    prefix="/research/floating-multi-select-source-attach-quality",
    tags=["floating-multi-select-source-attach-quality-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    highlight: str | None = Field(default=None, max_length=8000)
    prior_prompt: str | None = Field(default=None, max_length=8000)
    context: list[str] | None = None
    findings: list[str] | None = None
    live_dispatched: Literal[False] | None = None
    merge_executed: Literal[False] | None = None


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


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=2)
    selected_instance_ids: list[str] = Field(min_length=2)
    pack_mode: Literal[
        "cohesive_prompt", "collective_pack", "cohesive_plus_analysis"
    ]
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    operator_ack: bool = Field(strict=True)
    extra_context: list[str] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    extra_findings: list[str] | None = None
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    citations: list[CitationBody] | None = None
    derive_citations_from_sources: bool = Field(default=True, strict=True)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)
    require_both: bool = Field(default=True, strict=True)


@floating_multi_select_source_attach_quality_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_multi_select_source_attach_quality(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            members=[m.model_dump() for m in req.members],
            selected_instance_ids=req.selected_instance_ids,
            pack_mode=req.pack_mode,
            cohesive_prompt=req.cohesive_prompt,
            operator_ack=req.operator_ack,
            extra_context=req.extra_context,
            analysis_kind=req.analysis_kind,
            extra_findings=req.extra_findings,
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
        )
    except FloatingMultiSelectSourceAttachQualityComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_multi_select_source_attach_quality_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        floating_multi_select_source_attach_quality_compose_router
    )


__all__ = [
    "floating_multi_select_source_attach_quality_compose_router",
    "register_floating_multi_select_source_attach_quality_compose_routes",
]

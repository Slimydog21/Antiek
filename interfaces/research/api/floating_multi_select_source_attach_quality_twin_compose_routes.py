"""Registerable HTTP surface for multi-select source attach quality twin."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_multi_select_source_attach_quality_twin_compose import (
    FloatingMultiSelectSourceAttachQualityTwinComposeError,
    compose_floating_multi_select_source_attach_quality_twin,
)

floating_multi_select_source_attach_quality_twin_compose_router = APIRouter(
    prefix="/research/floating-multi-select-source-attach-quality-twin",
    tags=["floating-multi-select-source-attach-quality-twin-compose"],
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


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2000)
    html_fragment: str | None = Field(default=None, max_length=100000)


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


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
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    twin_findings: list[FindingBody] | None = None
    analysis_excerpt: str | None = Field(default=None, max_length=8000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=True, strict=True)
    require_both: bool = Field(default=True, strict=True)
    require_both_with_twin: bool = Field(default=True, strict=True)


@floating_multi_select_source_attach_quality_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_multi_select_source_attach_quality_twin(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            members=[m.model_dump() for m in req.members],
            selected_instance_ids=req.selected_instance_ids,
            pack_mode=req.pack_mode,
            cohesive_prompt=req.cohesive_prompt,
            operator_ack=req.operator_ack,
            requested_families=list(req.requested_families),
            sources=[s.model_dump() for s in req.sources],
            quality_overall=req.quality_overall,
            would_exceed=req.would_exceed,
            quality_floor=req.quality_floor,
            twin_findings=(
                [f.model_dump() for f in req.twin_findings]
                if req.twin_findings is not None
                else None
            ),
            analysis_excerpt=req.analysis_excerpt,
            existing_twin_asset_id=req.existing_twin_asset_id,
            mark_for_prompt_context=req.mark_for_prompt_context,
            require_both=req.require_both,
            require_both_with_twin=req.require_both_with_twin,
        )
    except FloatingMultiSelectSourceAttachQualityTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_multi_select_source_attach_quality_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        floating_multi_select_source_attach_quality_twin_compose_router
    )


__all__ = [
    "floating_multi_select_source_attach_quality_twin_compose_router",
    "register_floating_multi_select_source_attach_quality_twin_compose_routes",
]

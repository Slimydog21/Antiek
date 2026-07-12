"""Registerable HTTP surface for source attach + weekly learn twin presentation."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_routes import (
    TwinPresentationPackBody,
    WeeklyLearnBody,
)
from substrate.source_attach_antiek_bench_weekly_learn_twin_presentation_compose import (
    SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError,
    compose_source_attach_antiek_bench_weekly_learn_twin_presentation,
)

source_attach_antiek_bench_weekly_learn_twin_presentation_compose_router = APIRouter(
    prefix="/research/source-attach-antiek-bench-weekly-learn-twin-presentation",
    tags=["source-attach-antiek-bench-weekly-learn-twin-presentation-compose"],
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


class SourcesBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)
    derive_citations_from_sources: bool | None = Field(default=None, strict=True)


class WeeklyPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    twin_presentation_pack: TwinPresentationPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    weekly_pack: WeeklyPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@source_attach_antiek_bench_weekly_learn_twin_presentation_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
            sources=req.sources.model_dump(),
            weekly_pack=req.weekly_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_attach_antiek_bench_weekly_learn_twin_presentation_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        source_attach_antiek_bench_weekly_learn_twin_presentation_compose_router
    )


__all__ = [
    "source_attach_antiek_bench_weekly_learn_twin_presentation_compose_router",
    "register_source_attach_antiek_bench_weekly_learn_twin_presentation_compose_routes",
]

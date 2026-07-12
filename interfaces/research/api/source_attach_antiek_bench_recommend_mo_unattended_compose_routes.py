"""Registerable HTTP surface for source attach + Antiek-bench recommend MO unattended."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_recommend_mo_unattended_fullscreen_draft_compose_routes import (
    BenchBody,
    MoPackBody,
)
from substrate.source_attach_antiek_bench_recommend_mo_unattended_compose import (
    SourceAttachAntiekBenchRecommendMoUnattendedComposeError,
    compose_source_attach_antiek_bench_recommend_mo_unattended,
)

source_attach_antiek_bench_recommend_mo_unattended_compose_router = APIRouter(
    prefix="/research/source-attach-antiek-bench-recommend-mo-unattended",
    tags=["source-attach-antiek-bench-recommend-mo-unattended-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    family: Family
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=4000)
    html_fragment: str | None = Field(default=None, max_length=500_000)


class SourcesBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]


class RecommendPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    bench: BenchBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    recommend_pack: RecommendPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@source_attach_antiek_bench_recommend_mo_unattended_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_attach_antiek_bench_recommend_mo_unattended(
            sources=req.sources.model_dump(),
            recommend_pack=req.recommend_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SourceAttachAntiekBenchRecommendMoUnattendedComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_attach_antiek_bench_recommend_mo_unattended_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        source_attach_antiek_bench_recommend_mo_unattended_compose_router
    )


__all__ = [
    "source_attach_antiek_bench_recommend_mo_unattended_compose_router",
    "register_source_attach_antiek_bench_recommend_mo_unattended_compose_routes",
]

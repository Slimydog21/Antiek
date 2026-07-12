"""Registerable HTTP surface for twin search + Antiek-bench weekly HTML-native."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_weekly_html_native_recursive_twin_compose_routes import (
    HtmlPackBody,
    WeeklyLearnBody,
)
from substrate.twin_search_antiek_bench_weekly_html_native_compose import (
    TwinSearchAntiekBenchWeeklyHtmlNativeComposeError,
    compose_twin_search_antiek_bench_weekly_html_native,
)

twin_search_antiek_bench_weekly_html_native_compose_router = APIRouter(
    prefix="/research/twin-search-antiek-bench-weekly-html-native",
    tags=["twin-search-antiek-bench-weekly-html-native-compose"],
)


class TwinSearchRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str | None = Field(default=None, max_length=256)


class WeeklyHtmlBody(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    html_pack: HtmlPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2048)
    twin_records: list[TwinSearchRecordBody]
    weekly_html: WeeklyHtmlBody
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=500)
    require_both: bool = Field(default=True, strict=True)


@twin_search_antiek_bench_weekly_html_native_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_search_antiek_bench_weekly_html_native(
            search_query=req.search_query,
            twin_records=[r.model_dump() for r in req.twin_records],
            weekly_html=req.weekly_html.model_dump(),
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            require_both=req.require_both,
        )
    except TwinSearchAntiekBenchWeeklyHtmlNativeComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_search_antiek_bench_weekly_html_native_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        twin_search_antiek_bench_weekly_html_native_compose_router
    )


__all__ = [
    "twin_search_antiek_bench_weekly_html_native_compose_router",
    "register_twin_search_antiek_bench_weekly_html_native_compose_routes",
]

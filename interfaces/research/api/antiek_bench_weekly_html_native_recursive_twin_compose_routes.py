"""Registerable HTTP surface for Antiek-bench weekly + HTML-native recursive twin."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_recursive_twin_settings_fullscreen_mo_compose_routes import (
    HtmlViewBody,
    TwinPackBody,
)
from substrate.antiek_bench_weekly_html_native_recursive_twin_compose import (
    AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError,
    compose_antiek_bench_weekly_html_native_recursive_twin,
)

antiek_bench_weekly_html_native_recursive_twin_compose_router = APIRouter(
    prefix="/research/antiek-bench-weekly-html-native-recursive-twin",
    tags=["antiek-bench-weekly-html-native-recursive-twin-compose"],
)


class EventBody(BaseModel):
    model_config = {"extra": "forbid"}

    event_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    outcome: Literal["worked", "failed", "mixed", "unknown"]
    score: float | None = Field(default=None, ge=0, le=1)


class WeeklyLearnBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    events: list[EventBody]
    min_events_per_task: int | None = Field(default=None, ge=1)


class HtmlPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    twin_pack: TwinPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    html_pack: HtmlPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@antiek_bench_weekly_html_native_recursive_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_weekly_html_native_recursive_twin(
            weekly_learn=req.weekly_learn.model_dump(),
            html_pack=req.html_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_weekly_html_native_recursive_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        antiek_bench_weekly_html_native_recursive_twin_compose_router
    )


__all__ = [
    "antiek_bench_weekly_html_native_recursive_twin_compose_router",
    "register_antiek_bench_weekly_html_native_recursive_twin_compose_routes",
]

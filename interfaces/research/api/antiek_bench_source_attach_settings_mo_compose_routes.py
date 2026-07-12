"""Registerable HTTP surface for Antiek-bench + source attach settings MO."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_task_model_recommendation_compose_routes import (
    EventBody,
    ModelBody,
    TaskSeedBody,
)
from interfaces.research.api.source_attach_settings_decision_mo_compose_routes import (
    SettingsMoBody,
    SourcesBody,
)
from substrate.antiek_bench_source_attach_settings_mo_compose import (
    AntiekBenchSourceAttachSettingsMoComposeError,
    compose_antiek_bench_source_attach_settings_mo,
)

antiek_bench_source_attach_settings_mo_compose_router = APIRouter(
    prefix="/research/antiek-bench-source-attach-settings-mo",
    tags=["antiek-bench-source-attach-settings-mo-compose"],
)


class BenchBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    focus_task: str = Field(min_length=1, max_length=256)
    events: list[EventBody]
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    selected_model_id: str | None = Field(default=None, max_length=256)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    existing_tasks: list[str] | None = None
    proposed_new_tasks: list[TaskSeedBody] | None = None
    min_events_per_task: int | None = Field(default=None, ge=1)
    min_events_for_recommendation: int | None = Field(default=None, ge=1)


class SourcePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    settings_mo: SettingsMoBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    bench: BenchBody
    source_pack: SourcePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@antiek_bench_source_attach_settings_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_source_attach_settings_mo(
            bench=req.bench.model_dump(),
            source_pack=req.source_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except AntiekBenchSourceAttachSettingsMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_source_attach_settings_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(antiek_bench_source_attach_settings_mo_compose_router)


__all__ = [
    "antiek_bench_source_attach_settings_mo_compose_router",
    "register_antiek_bench_source_attach_settings_mo_compose_routes",
]

"""Registerable HTTP surface for settings add-model + Antiek-bench source MO."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_source_attach_settings_mo_compose_routes import (
    BenchBody,
    SourcePackBody,
)
from interfaces.research.api.settings_add_model_inventory_compose_routes import (
    ModelBody,
)
from substrate.settings_add_model_antiek_bench_source_attach_mo_compose import (
    SettingsAddModelAntiekBenchSourceAttachMoComposeError,
    compose_settings_add_model_antiek_bench_source_attach_mo,
)

settings_add_model_antiek_bench_source_attach_mo_compose_router = APIRouter(
    prefix="/research/settings-add-model-antiek-bench-source-attach-mo",
    tags=["settings-add-model-antiek-bench-source-attach-mo-compose"],
)


class SettingsBody(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[ModelBody]
    pending_add_model_ids: list[str]
    action: Literal["preview", "propose_add"]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    selected_model_id: str | None = Field(default=None, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class BenchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    bench: BenchBody
    source_pack: SourcePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    bench_pack: BenchPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@settings_add_model_antiek_bench_source_attach_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_add_model_antiek_bench_source_attach_mo(
            settings=req.settings.model_dump(),
            bench_pack=req.bench_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsAddModelAntiekBenchSourceAttachMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_settings_add_model_antiek_bench_source_attach_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_add_model_antiek_bench_source_attach_mo_compose_router
    )


__all__ = [
    "settings_add_model_antiek_bench_source_attach_mo_compose_router",
    "register_settings_add_model_antiek_bench_source_attach_mo_compose_routes",
]

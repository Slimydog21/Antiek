"""Registerable HTTP surface for competition DR + settings add-model pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_quality_source_pack_compose_routes import (
    CitationBody,
    DecisionBody,
)
from interfaces.research.api.settings_add_model_antiek_bench_source_attach_mo_compose_routes import (
    BenchPackBody,
    SettingsBody,
)
from substrate.competition_dr_settings_add_model_bench_source_mo_compose import (
    CompetitionDrSettingsAddModelBenchSourceMoComposeError,
    compose_competition_dr_settings_add_model_bench_source_mo,
)

# Re-export citation family / area literals via nested models from competition routes
from interfaces.research.api.competition_dr_quality_source_pack_compose_routes import (
    CitationFamily,
    DecisionArea,
)

competition_dr_settings_add_model_bench_source_mo_compose_router = APIRouter(
    prefix="/research/competition-dr-settings-add-model-bench-source-mo",
    tags=["competition-dr-settings-add-model-bench-source-mo-compose"],
)


class CompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody]
    focus_areas: list[DecisionArea] | None = None
    requested_families: list[CitationFamily] = Field(min_length=1)
    citations: list[CitationBody]
    filter_to_selected_families: bool = Field(default=True, strict=True)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    require_no_behind_gaps: bool = Field(default=False, strict=True)


class SettingsPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    bench_pack: BenchPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    settings_pack: SettingsPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@competition_dr_settings_add_model_bench_source_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_settings_add_model_bench_source_mo(
            competition=req.competition.model_dump(),
            settings_pack=req.settings_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrSettingsAddModelBenchSourceMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_dr_settings_add_model_bench_source_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_settings_add_model_bench_source_mo_compose_router
    )


__all__ = [
    "competition_dr_settings_add_model_bench_source_mo_compose_router",
    "register_competition_dr_settings_add_model_bench_source_mo_compose_routes",
]

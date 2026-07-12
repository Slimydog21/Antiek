"""Registerable HTTP surface for marketplace free + competition DR pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_settings_add_model_bench_source_mo_compose_routes import (
    CompetitionBody,
    SettingsPackBody,
)
from substrate.marketplace_free_competition_dr_settings_bench_mo_compose import (
    MarketplaceFreeCompetitionDrSettingsBenchMoComposeError,
    compose_marketplace_free_competition_dr_settings_bench_mo,
)

marketplace_free_competition_dr_settings_bench_mo_compose_router = APIRouter(
    prefix="/research/marketplace-free-competition-dr-settings-bench-mo",
    tags=["marketplace-free-competition-dr-settings-bench-mo-compose"],
)


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(
        default=None, max_length=256
    )


class CompetitionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    settings_pack: SettingsPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    competition_pack: CompetitionPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_free_competition_dr_settings_bench_mo_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_competition_dr_settings_bench_mo(
            market=req.market.model_dump(),
            competition_pack=req.competition_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeCompetitionDrSettingsBenchMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_competition_dr_settings_bench_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_competition_dr_settings_bench_mo_compose_router
    )


__all__ = [
    "marketplace_free_competition_dr_settings_bench_mo_compose_router",
    "register_marketplace_free_competition_dr_settings_bench_mo_compose_routes",
]

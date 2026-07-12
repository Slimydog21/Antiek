"""Registerable HTTP surface for recursive twin + marketplace free pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.marketplace_free_competition_dr_settings_bench_mo_compose_routes import (
    CompetitionPackBody,
    MarketBody,
)
from substrate.recursive_twin_marketplace_free_competition_dr_compose import (
    RecursiveTwinMarketplaceFreeCompetitionDrComposeError,
    compose_recursive_twin_marketplace_free_competition_dr,
)

recursive_twin_marketplace_free_competition_dr_compose_router = APIRouter(
    prefix="/research/recursive-twin-marketplace-free-competition-dr",
    tags=["recursive-twin-marketplace-free-competition-dr-compose"],
)


class TwinBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=100_000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None


class MarketPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    competition_pack: CompetitionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    market_pack: MarketPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@recursive_twin_marketplace_free_competition_dr_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_marketplace_free_competition_dr(
            twin=req.twin.model_dump(),
            market_pack=req.market_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinMarketplaceFreeCompetitionDrComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_marketplace_free_competition_dr_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        recursive_twin_marketplace_free_competition_dr_compose_router
    )


__all__ = [
    "recursive_twin_marketplace_free_competition_dr_compose_router",
    "register_recursive_twin_marketplace_free_competition_dr_compose_routes",
]

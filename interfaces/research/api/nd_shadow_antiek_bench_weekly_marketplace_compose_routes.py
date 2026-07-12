"""Registerable HTTP surface for ND shadow + Antiek-bench weekly marketplace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_weekly_marketplace_free_source_compose_routes import (
    MarketResearchBody,
    WeeklyLearnBody,
)
from substrate.nd_shadow_antiek_bench_weekly_marketplace_compose import (
    NdShadowAntiekBenchWeeklyMarketplaceComposeError,
    compose_nd_shadow_antiek_bench_weekly_marketplace,
)

nd_shadow_antiek_bench_weekly_marketplace_compose_router = APIRouter(
    prefix="/research/nd-shadow-antiek-bench-weekly-marketplace",
    tags=["nd-shadow-antiek-bench-weekly-marketplace-compose"],
)


class NdShadowBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    nd_recommended_model_id: str | None = Field(default=None, max_length=128)
    kill_switch_on: bool = Field(strict=True)
    confidence: float | None = Field(default=None, ge=0, le=1)
    task: str | None = Field(default=None, max_length=128)
    inventory_model_ids: list[str] | None = None


class WeeklyMarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    market_research: MarketResearchBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    weekly_market: WeeklyMarketBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@nd_shadow_antiek_bench_weekly_marketplace_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_nd_shadow_antiek_bench_weekly_marketplace(
            nd_shadow=req.nd_shadow.model_dump(),
            weekly_market=req.weekly_market.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except NdShadowAntiekBenchWeeklyMarketplaceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_nd_shadow_antiek_bench_weekly_marketplace_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(nd_shadow_antiek_bench_weekly_marketplace_compose_router)


__all__ = [
    "nd_shadow_antiek_bench_weekly_marketplace_compose_router",
    "register_nd_shadow_antiek_bench_weekly_marketplace_compose_routes",
]

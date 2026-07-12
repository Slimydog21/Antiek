"""Registerable HTTP surface for Antiek-bench weekly + marketplace free source."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_weekly_usage_learn_compose_routes import (
    EventBody,
)
from interfaces.research.api.marketplace_free_source_attach_record_prompt_compose_routes import (
    MarketBody,
    ResearchBody,
)
from substrate.antiek_bench_weekly_marketplace_free_source_compose import (
    AntiekBenchWeeklyMarketplaceFreeSourceComposeError,
    compose_antiek_bench_weekly_marketplace_free_source,
)

antiek_bench_weekly_marketplace_free_source_compose_router = APIRouter(
    prefix="/research/antiek-bench-weekly-marketplace-free-source",
    tags=["antiek-bench-weekly-marketplace-free-source-compose"],
)


class WeeklyLearnBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    events: list[EventBody]
    min_events_per_task: int | None = Field(default=None, ge=1, le=100)


class MarketResearchBody(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    research: ResearchBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    market_research: MarketResearchBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@antiek_bench_weekly_marketplace_free_source_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_weekly_marketplace_free_source(
            weekly_learn=req.weekly_learn.model_dump(),
            market_research=req.market_research.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except AntiekBenchWeeklyMarketplaceFreeSourceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_weekly_marketplace_free_source_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        antiek_bench_weekly_marketplace_free_source_compose_router
    )


__all__ = [
    "antiek_bench_weekly_marketplace_free_source_compose_router",
    "register_antiek_bench_weekly_marketplace_free_source_compose_routes",
]

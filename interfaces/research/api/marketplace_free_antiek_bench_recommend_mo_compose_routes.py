"""Registerable HTTP surface for marketplace free + bench recommend MO."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.antiek_bench_recommend_mo_unattended_compose_routes import (
    BenchBody,
    MoPackBody,
)
from substrate.marketplace_free_antiek_bench_recommend_mo_compose import (
    MarketplaceFreeAntiekBenchRecommendMoComposeError,
    compose_marketplace_free_antiek_bench_recommend_mo,
)

marketplace_free_antiek_bench_recommend_mo_compose_router = APIRouter(
    prefix="/research/marketplace-free-antiek-bench-recommend-mo",
    tags=["marketplace-free-antiek-bench-recommend-mo-compose"],
)


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(default=None, max_length=256)


class BenchMoBody(BaseModel):
    model_config = {"extra": "forbid"}

    bench: BenchBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    bench_mo: BenchMoBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_free_antiek_bench_recommend_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_antiek_bench_recommend_mo(
            market=req.market.model_dump(),
            bench_mo=req.bench_mo.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeAntiekBenchRecommendMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_antiek_bench_recommend_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_antiek_bench_recommend_mo_compose_router
    )


__all__ = [
    "marketplace_free_antiek_bench_recommend_mo_compose_router",
    "register_marketplace_free_antiek_bench_recommend_mo_compose_routes",
]

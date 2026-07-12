"""Registerable HTTP surface for Antiek-bench rewrite + model decision marketplace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.model_decision_twin_search_html_native_marketplace_compose_routes import (
    TwinSearchPackBody,
)
from interfaces.research.api.model_decision_twin_search_weekly_html_native_compose_routes import (
    DecisionBody,
)
from substrate.antiek_bench_rewrite_model_decision_marketplace_compose import (
    AntiekBenchRewriteModelDecisionMarketplaceComposeError,
    compose_antiek_bench_rewrite_model_decision_marketplace,
)

antiek_bench_rewrite_model_decision_marketplace_compose_router = APIRouter(
    prefix="/research/antiek-bench-rewrite-model-decision-marketplace",
    tags=["antiek-bench-rewrite-model-decision-marketplace-compose"],
)


class UsagePatternBody(BaseModel):
    model_config = {"extra": "forbid"}

    task_family: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=256)
    outcome: str = Field(min_length=1, max_length=32)
    n: float | None = Field(default=None, gt=0)


class RewriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_label: str = Field(min_length=1, max_length=64)
    patterns: list[UsagePatternBody]


class ModelDecisionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    twin_search_pack: TwinSearchPackBody
    require_both: bool | None = Field(default=None, strict=True)
    block_on_budget_exceed: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    rewrite: RewriteBody
    model_decision_pack: ModelDecisionPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)
    block_if_applied: bool = Field(default=True, strict=True)


@antiek_bench_rewrite_model_decision_marketplace_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_rewrite_model_decision_marketplace(
            rewrite=req.rewrite.model_dump(),
            model_decision_pack=req.model_decision_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
            block_if_applied=req.block_if_applied,
        )
    except AntiekBenchRewriteModelDecisionMarketplaceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_rewrite_model_decision_marketplace_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        antiek_bench_rewrite_model_decision_marketplace_compose_router
    )


__all__ = [
    "antiek_bench_rewrite_model_decision_marketplace_compose_router",
    "register_antiek_bench_rewrite_model_decision_marketplace_compose_routes",
]

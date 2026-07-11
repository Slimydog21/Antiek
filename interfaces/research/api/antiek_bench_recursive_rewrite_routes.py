"""Registerable HTTP surface for Antiek-bench recursive rewrite (advisory)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.antiek_bench_recursive_rewrite import (
    AntiekBenchRewriteError,
    propose_antiek_bench_recursive_rewrite,
)

antiek_bench_recursive_rewrite_router = APIRouter(
    prefix="/settings/antiek-bench/recursive-rewrite",
    tags=["antiek-bench-recursive-rewrite"],
)


class UsagePatternBody(BaseModel):
    model_config = {"extra": "forbid"}

    task_family: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=256)
    outcome: Literal["worked", "failed", "mixed", "unknown"]
    n: float = Field(default=1, gt=0)


class RewriteRequest(BaseModel):
    model_config = {"extra": "forbid"}

    week_label: str = Field(min_length=1, max_length=64)
    patterns: list[UsagePatternBody] = Field(default_factory=list)


@antiek_bench_recursive_rewrite_router.post("/propose")
def post_propose(req: RewriteRequest) -> dict[str, Any]:
    try:
        proposal = propose_antiek_bench_recursive_rewrite(
            week_label=req.week_label,
            patterns=[p.model_dump() for p in req.patterns],
        )
    except AntiekBenchRewriteError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return proposal.to_dict()


def register_antiek_bench_recursive_rewrite_routes(app: FastAPI) -> None:
    app.include_router(antiek_bench_recursive_rewrite_router)


__all__ = [
    "antiek_bench_recursive_rewrite_router",
    "register_antiek_bench_recursive_rewrite_routes",
]

"""HTTP surface for Antiek-bench weekly presentation (registerable).

Callers inject weekly records — this route does not run the bench or own
``substrate/antiek_bench``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from substrate.bench_presentation.view import present_weekly_bench, weekly_view_to_dict

bench_view_router = APIRouter(
    prefix="/settings/antiek-bench",
    tags=["antiek-bench-view"],
)


class BenchRecordIn(BaseModel):
    task: str = "general"
    model_id: str = Field(min_length=1)
    score: float | None = None
    n_runs: int = 0
    notes: str = ""


class WeeklyBenchRequest(BaseModel):
    week_id: str = ""
    records: list[BenchRecordIn] = Field(default_factory=list)


@bench_view_router.post("/weekly")
def weekly_bench_view(req: WeeklyBenchRequest) -> dict[str, Any]:
    """Present injected weekly bench records. No bench execution."""
    view = present_weekly_bench(
        [r.model_dump() for r in req.records],
        week_id=req.week_id,
    )
    return weekly_view_to_dict(view)


def register_bench_view_routes(app: FastAPI) -> None:
    app.include_router(bench_view_router)


__all__ = [
    "WeeklyBenchRequest",
    "bench_view_router",
    "register_bench_view_routes",
    "weekly_bench_view",
]

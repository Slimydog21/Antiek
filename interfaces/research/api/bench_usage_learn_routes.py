"""HTTP surface for Antiek-bench usage-learn proposals (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field, field_validator

from substrate.bench_presentation.usage_learn import propose_next_week_weights

bench_usage_learn_router = APIRouter(
    prefix="/settings/antiek-bench",
    tags=["antiek-bench-usage-learn"],
)


class UsageEventIn(BaseModel):
    task: str = "general"
    success: bool | None = None
    model_id: str = ""
    notes: str = ""

    @field_validator("success", mode="before")
    @classmethod
    def _success_not_stringy_invent(cls, v: object) -> object:
        # Allow null; require real bool when present (not truthy strings via loose coerce)
        if v is None or isinstance(v, bool):
            return v
        raise ValueError("success must be boolean or null")


class UsageLearnRequest(BaseModel):
    week_id: str = ""
    usage_events: list[UsageEventIn] = Field(default_factory=list)
    prior_weights: dict[str, float] | None = None
    min_weight: float = Field(default=0.05, ge=0.0, le=0.5)


@bench_usage_learn_router.post("/usage-learn")
def usage_learn(req: UsageLearnRequest) -> dict[str, Any]:
    """Propose next-week bench weights from injected usage. No live runs."""
    proposal = propose_next_week_weights(
        [e.model_dump() for e in req.usage_events],
        week_id=req.week_id,
        prior_weights=req.prior_weights,
        min_weight=req.min_weight,
    )
    return proposal.to_dict()


def register_bench_usage_learn_routes(app: FastAPI) -> None:
    app.include_router(bench_usage_learn_router)


__all__ = [
    "UsageLearnRequest",
    "bench_usage_learn_router",
    "register_bench_usage_learn_routes",
    "usage_learn",
]

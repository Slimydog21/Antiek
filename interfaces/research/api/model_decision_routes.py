"""HTTP surface for the advisory model decision tree.

Register with::

    from interfaces.research.api.model_decision_routes import (
        register_model_decision_routes,
    )
    register_model_decision_routes(app)

``app.py`` may be owned by another lane; registration is additive and tested
via a local FastAPI app until create_app can absorb it.

Authority is always ``advisory`` — this route never dispatches a model.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from substrate.model_decision.tree import (
    AUTHORITY,
    ModelCandidate,
    rank_models_for_task,
    result_to_dict,
)

model_decision_router = APIRouter(
    prefix="/settings/model-decision",
    tags=["model-decision-advisory"],
)


class ModelIn(BaseModel):
    model_id: str = Field(min_length=1, max_length=256)
    provider: str = ""
    tier: str = "unknown"
    usd_per_1k_tokens: float | None = Field(default=None, ge=0)
    enabled: bool = True


class DecisionTreeRequest(BaseModel):
    task: str = Field(default="general", min_length=1, max_length=64)
    models: list[ModelIn] = Field(min_length=0)
    remaining_usd: float | None = None
    prompt_chars: int | None = Field(default=None, ge=0)
    # Optional Antiek-bench scores: {task: {model_id: score}}
    bench_scores: dict[str, dict[str, float]] | None = None


@model_decision_router.post("/rank")
def rank_models(req: DecisionTreeRequest) -> dict[str, Any]:
    """Rank models for a task. Advisory only — no dispatch, no spend."""
    candidates = [
        ModelCandidate(
            model_id=m.model_id,
            provider=m.provider,
            tier=m.tier,
            usd_per_1k_tokens=m.usd_per_1k_tokens,
            enabled=m.enabled,
        )
        for m in req.models
    ]
    result = rank_models_for_task(
        req.task,
        candidates,
        remaining_usd=req.remaining_usd,
        prompt_chars=req.prompt_chars,
        bench_scores=req.bench_scores,
    )
    body = result_to_dict(result)
    assert body["authority"] == AUTHORITY
    return body


def register_model_decision_routes(app: FastAPI) -> None:
    app.include_router(model_decision_router)


__all__ = [
    "DecisionTreeRequest",
    "ModelIn",
    "model_decision_router",
    "rank_models",
    "register_model_decision_routes",
]

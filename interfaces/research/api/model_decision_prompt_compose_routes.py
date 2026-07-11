"""Registerable HTTP surface for model decision + prompt projection compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.model_decision.prompt_compose import (
    ModelDecisionPromptComposeError,
    compose_model_decision_with_projection,
)

model_decision_prompt_compose_router = APIRouter(
    prefix="/settings/model-decision-prompt-compose",
    tags=["model-decision-prompt-compose"],
)


class ModelOptionBody(BaseModel):
    model_config = {"extra": "forbid"}

    model_id: str = Field(min_length=1, max_length=256)
    tier: str | None = Field(default=None, max_length=64)
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    models: list[ModelOptionBody] = Field(min_length=1)
    daily_cap_usd: float | None = None
    spent_usd: float | None = None
    projected_cost_usd_high: float | None = None
    projected_cost_usd_low: float | None = None
    use_model_cost_defaults: bool = Field(default=True, strict=True)


@model_decision_prompt_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_model_decision_with_projection(
            selected_model_id=req.selected_model_id,
            models=[m.model_dump() for m in req.models],
            daily_cap_usd=req.daily_cap_usd,
            spent_usd=req.spent_usd,
            projected_cost_usd_high=req.projected_cost_usd_high,
            projected_cost_usd_low=req.projected_cost_usd_low,
            use_model_cost_defaults=req.use_model_cost_defaults,
        )
    except ModelDecisionPromptComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_model_decision_prompt_compose_routes(app: FastAPI) -> None:
    app.include_router(model_decision_prompt_compose_router)


__all__ = [
    "model_decision_prompt_compose_router",
    "register_model_decision_prompt_compose_routes",
]

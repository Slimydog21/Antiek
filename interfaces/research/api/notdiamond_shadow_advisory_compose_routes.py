"""Registerable HTTP surface for NotDiamond shadow advisory compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)

notdiamond_shadow_advisory_compose_router = APIRouter(
    prefix="/research/notdiamond-shadow",
    tags=["notdiamond-shadow-advisory-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    nd_recommended_model_id: str | None = Field(default=None, max_length=128)
    kill_switch_on: bool = Field(strict=True)
    confidence: float | None = Field(default=None)
    task: str | None = Field(default=None, max_length=256)
    inventory_model_ids: list[str] | None = None


@notdiamond_shadow_advisory_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_notdiamond_shadow_advisory(
            selected_model_id=req.selected_model_id,
            nd_recommended_model_id=req.nd_recommended_model_id,
            kill_switch_on=req.kill_switch_on,
            confidence=req.confidence,
            task=req.task,
            inventory_model_ids=req.inventory_model_ids,
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_notdiamond_shadow_advisory_compose_routes(app: FastAPI) -> None:
    app.include_router(notdiamond_shadow_advisory_compose_router)


__all__ = [
    "notdiamond_shadow_advisory_compose_router",
    "register_notdiamond_shadow_advisory_compose_routes",
]

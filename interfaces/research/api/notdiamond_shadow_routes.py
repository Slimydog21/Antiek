"""HTTP surface for NotDiamond shadow comparison (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.advisory.notdiamond_shadow import (
    NotDiamondShadowError,
    record_shadow_comparison,
)

notdiamond_shadow_router = APIRouter(
    prefix="/settings/notdiamond",
    tags=["notdiamond-shadow"],
)


class ShadowCompareRequest(BaseModel):
    task: str = "general"
    local_model_id: str = Field(min_length=1)
    nd_recommended_model_id: str | None = None
    enabled: bool = False
    extra_notes: list[str] = Field(default_factory=list)


@notdiamond_shadow_router.post("/shadow")
def shadow_compare(req: ShadowCompareRequest) -> dict[str, Any]:
    """Advisory shadow only — never production dispatch."""
    try:
        rec = record_shadow_comparison(
            task=req.task,
            local_model_id=req.local_model_id,
            nd_recommended_model_id=req.nd_recommended_model_id,
            enabled=req.enabled,
            extra_notes=req.extra_notes,
        )
    except NotDiamondShadowError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return rec.to_dict()


def register_notdiamond_shadow_routes(app: FastAPI) -> None:
    app.include_router(notdiamond_shadow_router)


__all__ = [
    "ShadowCompareRequest",
    "notdiamond_shadow_router",
    "register_notdiamond_shadow_routes",
    "shadow_compare",
]

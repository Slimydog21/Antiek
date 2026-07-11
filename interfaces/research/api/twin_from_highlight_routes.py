"""Registerable HTTP surface for highlight → twin seed (no LLM)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_notes.from_highlight import (
    HighlightTwinError,
    build_highlight_twin_seed,
)

twin_from_highlight_router = APIRouter(
    prefix="/twins/from-highlight",
    tags=["twin-from-highlight"],
)


class HighlightTwinRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=512)
    highlight: str = Field(min_length=1)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str = "highlight"
    # Required explicit boolean — never default to False (fail-open for gated bodies).
    # strict=True rejects "false"/0 coercion (fail closed).
    gated: bool = Field(strict=True)


@twin_from_highlight_router.post("/seed")
def post_highlight_seed(req: HighlightTwinRequest) -> dict[str, Any]:
    try:
        seed = build_highlight_twin_seed(
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            insights=req.insights,
            questions=req.questions,
            source_label=req.source_label,
            gated=req.gated,
        )
    except HighlightTwinError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return seed.to_dict()


def register_twin_from_highlight_routes(app: FastAPI) -> None:
    app.include_router(twin_from_highlight_router)


__all__ = [
    "register_twin_from_highlight_routes",
    "twin_from_highlight_router",
]

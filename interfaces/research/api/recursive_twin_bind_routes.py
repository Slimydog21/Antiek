"""Registerable HTTP surface for recursive twin bind (pure decision)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.recursive_twin_bind import (
    RecursiveTwinBindError,
    evaluate_recursive_twin_bind,
)

recursive_twin_bind_router = APIRouter(
    prefix="/twins/recursive-bind",
    tags=["recursive-twin-bind"],
)


class RecursiveTwinBindRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_id: str | None = Field(default=None, max_length=256)
    insights: list[str] | None = None
    questions: list[str] | None = None
    source: Literal["operator", "llm_note_taker", "highlight_seed", "unknown"]
    llm_filled: bool = Field(strict=True)
    gated: bool = Field(strict=True)


@recursive_twin_bind_router.post("/evaluate")
def post_evaluate(req: RecursiveTwinBindRequest) -> dict[str, Any]:
    try:
        decision = evaluate_recursive_twin_bind(
            parent_asset_id=req.parent_asset_id,
            twin_id=req.twin_id,
            insights=req.insights,
            questions=req.questions,
            source=req.source,
            llm_filled=req.llm_filled,
            gated=req.gated,
        )
    except RecursiveTwinBindError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_recursive_twin_bind_routes(app: FastAPI) -> None:
    app.include_router(recursive_twin_bind_router)


__all__ = [
    "recursive_twin_bind_router",
    "register_recursive_twin_bind_routes",
]

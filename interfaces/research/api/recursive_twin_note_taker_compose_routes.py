"""Registerable HTTP surface for recursive twin note-taker compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)

recursive_twin_note_taker_compose_router = APIRouter(
    prefix="/research/recursive-twin-note-taker",
    tags=["recursive-twin-note-taker-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=500_000)
    operator_ack: bool = Field(strict=True)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None


@recursive_twin_note_taker_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_note_taker(
            parent_asset_id=req.parent_asset_id,
            source_excerpt=req.source_excerpt,
            operator_ack=req.operator_ack,
            existing_twin_asset_id=req.existing_twin_asset_id,
            focus_questions=req.focus_questions,
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_note_taker_compose_routes(app: FastAPI) -> None:
    app.include_router(recursive_twin_note_taker_compose_router)


__all__ = [
    "recursive_twin_note_taker_compose_router",
    "register_recursive_twin_note_taker_compose_routes",
]

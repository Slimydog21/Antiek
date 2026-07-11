"""Registerable HTTP surface for LLM note-taker twin payloads (no model call)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_notes.llm_note_taker import (
    LlmNoteTakerError,
    build_twin_note_payload,
)

twin_llm_note_taker_router = APIRouter(
    prefix="/twins/note-taker",
    tags=["twin-llm-note-taker"],
)


class NoteTakerRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=512)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source_label: str = "llm-note-taker"
    llm_filled: bool = Field(strict=True)
    asset_text_sha256: str | None = None
    gated: bool = Field(strict=True)


@twin_llm_note_taker_router.post("/payload")
def post_note_taker_payload(req: NoteTakerRequest) -> dict[str, Any]:
    try:
        payload = build_twin_note_payload(
            parent_asset_id=req.parent_asset_id,
            insights=req.insights,
            questions=req.questions,
            source_label=req.source_label,
            llm_filled=req.llm_filled,
            asset_text_sha256=req.asset_text_sha256,
            gated=req.gated,
        )
    except LlmNoteTakerError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return payload.to_dict()


def register_twin_llm_note_taker_routes(app: FastAPI) -> None:
    app.include_router(twin_llm_note_taker_router)


__all__ = [
    "register_twin_llm_note_taker_routes",
    "twin_llm_note_taker_router",
]

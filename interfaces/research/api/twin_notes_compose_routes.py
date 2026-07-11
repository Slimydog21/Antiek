"""HTTP compose surface for twin analysis drafts (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_notes.compose import compose_analysis_html
from substrate.twin_notes.store import (
    TwinNotesError,
    TwinNotesStore,
    TwinNotFound,
    TwinParentMismatch,
)

twin_notes_compose_router = APIRouter(prefix="/twins", tags=["twin-notes-compose"])

_STORE: TwinNotesStore | None = None


def set_twin_notes_compose_store(store: TwinNotesStore | None) -> None:
    global _STORE
    _STORE = store


def _store() -> TwinNotesStore:
    return _STORE if _STORE is not None else TwinNotesStore()


class ComposeRequest(BaseModel):
    twin_ids: list[str] = Field(min_length=1)
    title: str = "Combined analysis"
    parent_asset_id: str | None = None


@twin_notes_compose_router.post("/compose")
def compose_twins(req: ComposeRequest) -> dict[str, Any]:
    store = _store()
    docs = []
    try:
        for tid in req.twin_ids:
            docs.append(store.load(tid, parent_asset_id=req.parent_asset_id))
        draft = compose_analysis_html(docs, title=req.title)
    except TwinParentMismatch as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "cross_parent_compose_rejected", "message": str(e)},
        ) from e
    except TwinNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "parent_asset_id": draft.parent_asset_id,
        "title": draft.title,
        "html": draft.html,
        "twin_ids": draft.twin_ids,
        "insight_count": draft.insight_count,
        "question_count": draft.question_count,
    }


def register_twin_notes_compose_routes(app: FastAPI) -> None:
    app.include_router(twin_notes_compose_router)


__all__ = [
    "register_twin_notes_compose_routes",
    "set_twin_notes_compose_store",
    "twin_notes_compose_router",
]

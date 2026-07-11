"""HTTP search surface for twin-notes (registerable; app.py not required)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from substrate.twin_notes.search import search_store
from substrate.twin_notes.store import TwinNotesStore

twin_notes_search_router = APIRouter(prefix="/twins", tags=["twin-notes-search"])

_STORE: TwinNotesStore | None = None


def set_twin_notes_search_store(store: TwinNotesStore | None) -> None:
    global _STORE
    _STORE = store


def _store() -> TwinNotesStore:
    return _STORE if _STORE is not None else TwinNotesStore()


class TwinSearchResponse(BaseModel):
    query: str
    count: int
    hits: list[dict[str, Any]] = Field(default_factory=list)


@twin_notes_search_router.get("/search", response_model=TwinSearchResponse)
def search_twins_http(
    q: str = Query(..., min_length=1, max_length=500),
    parent_asset_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> TwinSearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="q must be non-empty")
    hits = search_store(
        _store(),
        query,
        parent_asset_id=parent_asset_id,
        limit=limit,
    )
    return TwinSearchResponse(
        query=query,
        count=len(hits),
        hits=[
            {
                "twin_id": h.twin_id,
                "parent_asset_id": h.parent_asset_id,
                "score": h.score,
                "matched_insights": h.matched_insights,
                "matched_questions": h.matched_questions,
                "source_label": h.source_label,
            }
            for h in hits
        ],
    )


def register_twin_notes_search_routes(app: FastAPI) -> None:
    app.include_router(twin_notes_search_router)


__all__ = [
    "register_twin_notes_search_routes",
    "set_twin_notes_search_store",
    "twin_notes_search_router",
]

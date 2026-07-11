"""HTTP surface for provisional twin draft-merge (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_notes.draft_merge import build_draft_merge
from substrate.twin_notes.store import (
    TwinNotesError,
    TwinNotesStore,
    TwinNotFound,
    TwinParentMismatch,
)

twin_notes_draft_merge_router = APIRouter(
    prefix="/twins",
    tags=["twin-notes-draft-merge"],
)

_STORE: TwinNotesStore | None = None


def set_twin_notes_draft_merge_store(store: TwinNotesStore | None) -> None:
    global _STORE
    _STORE = store


def _store() -> TwinNotesStore:
    return _STORE if _STORE is not None else TwinNotesStore()


class DraftMergeRequest(BaseModel):
    parent_asset_id: str = Field(min_length=1, max_length=512)
    parent_html: str = ""
    twin_ids: list[str] = Field(min_length=1)
    title: str = "Draft merge"


@twin_notes_draft_merge_router.post("/draft-merge")
def draft_merge(req: DraftMergeRequest) -> dict[str, Any]:
    store = _store()
    docs = []
    try:
        # Load by id only so cross-parent twins surface as 409 (policy), not 404.
        for tid in req.twin_ids:
            docs.append(store.load(tid))
        result = build_draft_merge(
            parent_asset_id=req.parent_asset_id,
            parent_html=req.parent_html,
            twins=docs,
            title=req.title,
        )
    except TwinParentMismatch as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "cross_parent_draft_merge_rejected", "message": str(e)},
        ) from e
    except TwinNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "draft_id": result.draft_id,
        "parent_asset_id": result.parent_asset_id,
        "provisional": result.provisional,
        "html": result.html,
        "twin_ids": result.twin_ids,
        "insight_count": result.insight_count,
        "question_count": result.question_count,
        "created_at": result.created_at,
        "notes": result.notes,
    }


def register_twin_notes_draft_merge_routes(app: FastAPI) -> None:
    app.include_router(twin_notes_draft_merge_router)


__all__ = [
    "register_twin_notes_draft_merge_routes",
    "set_twin_notes_draft_merge_store",
    "twin_notes_draft_merge_router",
]

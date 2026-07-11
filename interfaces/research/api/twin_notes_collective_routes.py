"""HTTP surface for collective twin packs (registerable; app.py not required)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_notes.collective import build_collective_pack
from substrate.twin_notes.store import TwinNotesError, TwinNotesStore, TwinNotFound

twin_notes_collective_router = APIRouter(
    prefix="/twins",
    tags=["twin-notes-collective"],
)

_STORE: TwinNotesStore | None = None


def set_twin_notes_collective_store(store: TwinNotesStore | None) -> None:
    global _STORE
    _STORE = store


def _store() -> TwinNotesStore:
    return _STORE if _STORE is not None else TwinNotesStore()


class CollectivePackRequest(BaseModel):
    twin_ids: list[str] = Field(min_length=1)
    instruction: str = ""


@twin_notes_collective_router.post("/collective")
def collective_pack(req: CollectivePackRequest) -> dict[str, Any]:
    store = _store()
    docs = []
    try:
        for tid in req.twin_ids:
            docs.append(store.load(tid))
        pack = build_collective_pack(docs, instruction=req.instruction)
    except TwinNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "instruction": pack.instruction,
        "twin_ids": pack.twin_ids,
        "parent_asset_ids": pack.parent_asset_ids,
        "pack_text": pack.pack_text,
        "insight_count": pack.insight_count,
        "question_count": pack.question_count,
        "notes": pack.notes,
    }


def register_twin_notes_collective_routes(app: FastAPI) -> None:
    app.include_router(twin_notes_collective_router)


__all__ = [
    "register_twin_notes_collective_routes",
    "set_twin_notes_collective_store",
    "twin_notes_collective_router",
]

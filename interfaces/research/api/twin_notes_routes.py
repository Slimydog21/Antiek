"""HTTP surface for twin-notes substrate (registerable; app.py not required).

Register with::

    from interfaces.research.api.twin_notes_routes import register_twin_notes_routes
    register_twin_notes_routes(app)
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from substrate.twin_notes.store import (
    TwinNotesError,
    TwinNotesStore,
    TwinNotFound,
    TwinParentMismatch,
    TwinStoreCorrupt,
)

twin_notes_router = APIRouter(prefix="/twins", tags=["twin-notes"])

# Injectable store for tests; production uses default root.
_STORE: TwinNotesStore | None = None


def set_twin_notes_store(store: TwinNotesStore | None) -> None:
    global _STORE
    _STORE = store


def _store() -> TwinNotesStore:
    return _STORE if _STORE is not None else TwinNotesStore()


class RecordTwinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_asset_id: str = Field(min_length=1, max_length=512)
    insights: list[Annotated[str, Field(min_length=1, max_length=10_000)]] = Field(
        default_factory=list, max_length=200
    )
    questions: list[Annotated[str, Field(min_length=1, max_length=10_000)]] = Field(
        default_factory=list, max_length=200
    )
    source_label: str = Field(default="", max_length=256)


class MergeTwinsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    twin_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        min_length=1, max_length=100
    )
    parent_asset_id: str | None = Field(default=None, max_length=512)
    source_label: str = Field(default="merged", max_length=256)


@twin_notes_router.post("")
def record_twin(req: RecordTwinRequest) -> dict[str, Any]:
    try:
        doc = _store().record(
            req.parent_asset_id,
            insights=req.insights,
            questions=req.questions,
            source_label=req.source_label,
        )
    except TwinStoreCorrupt as e:
        raise HTTPException(status_code=503, detail="twin store unavailable") from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return doc.to_dict()


@twin_notes_router.get("/by-parent/{parent_asset_id}")
def list_twins(parent_asset_id: str) -> dict[str, Any]:
    try:
        twins = _store().list_for_parent(parent_asset_id)
    except TwinStoreCorrupt as e:
        raise HTTPException(status_code=503, detail="twin store unavailable") from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"parent_asset_id": parent_asset_id, "twins": [t.to_dict() for t in twins]}


@twin_notes_router.get("/{twin_id}")
def get_twin(twin_id: str, parent_asset_id: str | None = None) -> dict[str, Any]:
    try:
        doc = _store().load(twin_id, parent_asset_id=parent_asset_id)
    except TwinNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TwinStoreCorrupt as e:
        raise HTTPException(status_code=503, detail="twin store unavailable") from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return doc.to_dict()


@twin_notes_router.post("/merge")
def merge_twins(req: MergeTwinsRequest) -> dict[str, Any]:
    try:
        doc = _store().merge(
            req.twin_ids,
            parent_asset_id=req.parent_asset_id,
            source_label=req.source_label,
        )
    except TwinParentMismatch as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "cross_parent_merge_rejected", "message": str(e)},
        ) from e
    except TwinNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TwinStoreCorrupt as e:
        raise HTTPException(status_code=503, detail="twin store unavailable") from e
    except TwinNotesError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return doc.to_dict()


def register_twin_notes_routes(app: FastAPI) -> None:
    app.include_router(twin_notes_router)


__all__ = [
    "MergeTwinsRequest",
    "RecordTwinRequest",
    "register_twin_notes_routes",
    "set_twin_notes_store",
    "twin_notes_router",
]

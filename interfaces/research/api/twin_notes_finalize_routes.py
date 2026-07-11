"""HTTP surface for provisional draft finalize authorization (registerable)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.twin_notes.finalize_gate import (
    FinalizeGateError,
    authorize_finalize,
)

twin_notes_finalize_router = APIRouter(
    prefix="/twins/finalize",
    tags=["twin-notes-finalize"],
)


class FinalizeAuthorizeRequest(BaseModel):
    draft_id: str = Field(min_length=1, max_length=512)
    parent_asset_id: str = Field(min_length=1, max_length=512)
    provisional: bool
    operator_accepted: bool
    twin_ids: list[str] | None = None
    twin_parent_ids: list[str] | None = None


@twin_notes_finalize_router.post("/authorize")
def finalize_authorize(req: FinalizeAuthorizeRequest) -> dict[str, Any]:
    """Authorize finalize of a provisional draft. Never mutates parent."""
    try:
        auth = authorize_finalize(
            draft_id=req.draft_id,
            parent_asset_id=req.parent_asset_id,
            provisional=req.provisional,
            operator_accepted=req.operator_accepted,
            twin_ids=req.twin_ids,
            twin_parent_ids=req.twin_parent_ids,
        )
    except FinalizeGateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "authorized": auth.authorized,
        "draft_id": auth.draft_id,
        "parent_asset_id": auth.parent_asset_id,
        "reason": auth.reason,
        "notes": list(auth.notes),
    }


def register_twin_notes_finalize_routes(app: FastAPI) -> None:
    app.include_router(twin_notes_finalize_router)


__all__ = [
    "register_twin_notes_finalize_routes",
    "twin_notes_finalize_router",
]

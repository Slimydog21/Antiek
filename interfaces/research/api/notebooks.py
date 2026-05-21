"""Per-document notebook HTTP API (SPR-08 / M1-M6).

FastAPI route handlers for:

  GET    /api/notebooks/by-doc/{document_id}      — load (or create-empty)
  POST   /api/notebooks/by-doc/{document_id}      — save TipTap content
  POST   /api/notebooks/by-doc/{document_id}/auto-populate
                                                  — run auto-populator on demand
  PATCH  /api/notebooks/blocks/{block_id}/demote  — demote / restore

The substrate-side methods (services.notebooks.persistence +
auto_populate) carry the business logic; this module is the HTTP
wrapper. SPR-09's AntiekPersistence is the active default — every save
materialises a .antiek archive next to the substrate row.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.notebooks import auto_populate as auto_populate_mod  # noqa: E402
from services.notebooks.persistence import (  # noqa: E402
    BlockRecord,
    NotebookRecord,
    SAVE_KIND_AUTO,
    SAVE_KIND_EXPLICIT,
    get_default_persistence,
)


# ─────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────


class BlockOut(BaseModel):
    block_id: str
    notebook_id: str
    block_type: str
    source_event_ids: list[str]
    content_json: dict[str, Any]
    position: float
    demoted_at: Optional[str] = None
    edited_at: Optional[str] = None
    created_at: Optional[str] = None
    document_id: Optional[str] = None


class NotebookOut(BaseModel):
    notebook_id: str
    user_id: str
    document_id: str
    title: Optional[str]
    content_json: dict[str, Any]
    format_version: int
    created_at: Optional[str]
    last_saved_at: Optional[str]
    blocks: list[BlockOut]


class SaveNotebookRequest(BaseModel):
    """Body for ``POST /api/notebooks/by-doc/{document_id}``."""

    user_id: str = Field(default="__operator__")
    title: Optional[str] = None
    content_json: dict[str, Any]
    save_kind: str = Field(default=SAVE_KIND_AUTO)


class DemoteRequest(BaseModel):
    demoted: bool = True


class AutoPopulateRequest(BaseModel):
    user_id: str = Field(default="__operator__")
    run_mode: str = Field(default="on_open")


# ─────────────────────────────────────────────────────────────────────
# Serialisers
# ─────────────────────────────────────────────────────────────────────


def _block_to_out(b: BlockRecord) -> BlockOut:
    return BlockOut(
        block_id=b.block_id,
        notebook_id=b.notebook_id,
        block_type=b.block_type,
        source_event_ids=list(b.source_event_ids),
        content_json=dict(b.content_json),
        position=b.position,
        demoted_at=b.demoted_at.isoformat() if b.demoted_at else None,
        edited_at=b.edited_at.isoformat() if b.edited_at else None,
        created_at=b.created_at.isoformat() if b.created_at else None,
        document_id=b.document_id,
    )


def _notebook_to_out(n: NotebookRecord) -> NotebookOut:
    return NotebookOut(
        notebook_id=n.notebook_id,
        user_id=n.user_id,
        document_id=n.document_id,
        title=n.title,
        content_json=dict(n.content_json),
        format_version=n.format_version,
        created_at=n.created_at.isoformat() if n.created_at else None,
        last_saved_at=n.last_saved_at.isoformat() if n.last_saved_at else None,
        blocks=[_block_to_out(b) for b in n.blocks],
    )


# ─────────────────────────────────────────────────────────────────────
# Route registration
# ─────────────────────────────────────────────────────────────────────


def register_notebook_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
) -> None:
    """Mount per-document notebook routes on ``app``."""

    # db_path is currently informational — the persistence factory
    # reads ANTIEK_DUCKDB_PATH from env, not from this argument. We
    # keep the param on the registration function so a future
    # multi-DB deployment can plumb it through without changing the
    # call sites.
    _ = db_path

    @app.get(
        "/api/notebooks/by-doc/{document_id}",
        response_model=NotebookOut,
        tags=["notebooks"],
    )
    async def get_notebook_by_doc(
        document_id: str,
        user_id: str = Query(default="__operator__"),
    ) -> NotebookOut:
        persistence = get_default_persistence()
        record = persistence.get_or_create_notebook(
            user_id=user_id, document_id=document_id,
        )
        return _notebook_to_out(record)

    @app.post(
        "/api/notebooks/by-doc/{document_id}",
        response_model=NotebookOut,
        tags=["notebooks"],
    )
    async def save_notebook_by_doc(
        document_id: str,
        body: SaveNotebookRequest,
    ) -> NotebookOut:
        if body.save_kind not in (SAVE_KIND_AUTO, SAVE_KIND_EXPLICIT):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "invalid_save_kind",
                        "message": (
                            f"save_kind must be one of "
                            f"{[SAVE_KIND_AUTO, SAVE_KIND_EXPLICIT]}; "
                            f"got {body.save_kind!r}"
                        ),
                    },
                },
            )
        persistence = get_default_persistence()
        existing = persistence.get_or_create_notebook(
            user_id=body.user_id, document_id=document_id,
        )
        merged = NotebookRecord(
            notebook_id=existing.notebook_id,
            user_id=existing.user_id,
            document_id=existing.document_id,
            title=body.title if body.title is not None else existing.title,
            content_json=body.content_json,
            format_version=existing.format_version,
            created_at=existing.created_at,
            last_saved_at=existing.last_saved_at,
            blocks=existing.blocks,
        )
        saved = persistence.save_notebook(merged, save_kind=body.save_kind)
        return _notebook_to_out(saved)

    @app.post(
        "/api/notebooks/by-doc/{document_id}/auto-populate",
        response_model=NotebookOut,
        tags=["notebooks"],
    )
    async def auto_populate_notebook(
        document_id: str,
        body: AutoPopulateRequest,
    ) -> NotebookOut:
        # The populator's run_mode is a TS-side concept (on_open vs
        # on_event); the substrate API doesn't expose it directly, so
        # we ignore it for now and always do a full populate.
        _ = body.run_mode
        persistence = get_default_persistence()
        auto_populate_mod.populate_per_doc_notebook(
            user_id=body.user_id,
            document_id=document_id,
            persistence=persistence,
        )
        record = persistence.get_or_create_notebook(
            user_id=body.user_id, document_id=document_id,
        )
        return _notebook_to_out(record)

    @app.patch(
        "/api/notebooks/blocks/{block_id}/demote",
        response_model=BlockOut,
        tags=["notebooks"],
    )
    async def demote_block(
        block_id: str,
        body: DemoteRequest,
    ) -> BlockOut:
        persistence = get_default_persistence()
        try:
            updated = persistence.demote_block(
                block_id, demoted=body.demoted,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "block_not_found",
                        "message": str(exc),
                    },
                },
            ) from exc
        return _block_to_out(updated)

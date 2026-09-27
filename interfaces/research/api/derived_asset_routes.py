"""Derived-asset routes: Write informs (THREAD-CONTRACT §1.11a "Write informs (S5)").

``PUT /derived-assets/{asset_id}/blocks/{block_id}/informs`` replaces one Write
block's ordered document list by committing one §1.11 ``revise``. The owner
comes from middleware state (``_reader_owner_id``), never from the request.
The answers, all top-level so the client narrows on ``reason``:

- ``200 {revision_id, block_id, informs: [{ordinal, document_id, anchor?}]}``;
  a replay answers the first commit's exact bytes.
- ``404 {"detail": "not_found"}`` for a missing asset, another owner's, one
  with no revision yet, or a block not in the current revision. No 403.
- ``409 {reason: "revision_moved", current_revision_id}`` and
  ``409 {reason: "idempotency_conflict"}``.
- ``422 {reason: "informs_invalid", index, detail}``, and
  ``422 {"detail": "informs_body_invalid"}`` for a body that is not the
  signed envelope.

A refused request writes nothing. The route owns no DDL and no SQL: the
revise primitive (``substrate.derived_assets``) does the work inside one
``connect_write`` transaction, opened with the re-entrant
``con.transaction()``.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from runtime.db_lock import connect_write
from substrate.derived_assets import informs
from substrate.derived_assets.repository import (
    IdempotencyConflict,
    NotFound,
    RevisionIntegrityError,
    RevisionMoved,
    StoredOperation,
)

derived_asset_router = APIRouter(tags=["derived-assets"])

_INFORMS_PATH = "/derived-assets/{asset_id}/blocks/{block_id}/informs"


def _not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "not_found"})


def _stored(stored: StoredOperation) -> Response:
    return Response(content=stored.response_json.encode("utf-8"), media_type="application/json")


def _put_informs(owner: str, asset_id: str, block_id: str, raw: bytes) -> Response:
    try:
        request = informs.parse_body(asset_id, block_id, raw)
    except informs.InformsBodyInvalid:
        return JSONResponse(status_code=422, content={"detail": "informs_body_invalid"})
    with connect_write(_resolve_db_path(), purpose="derived-assets/informs/put") as con:
        try:
            with con.transaction():
                stored = informs.put_block_informs(
                    con, owner_user_id=owner, asset_id=asset_id, block_id=block_id, request=request
                )
        except NotFound:
            return _not_found()
        except IdempotencyConflict:
            return JSONResponse(status_code=409, content={"reason": "idempotency_conflict"})
        except RevisionMoved as moved:
            return JSONResponse(
                status_code=409,
                content={"reason": "revision_moved", "current_revision_id": moved.current_revision_id},
            )
        except informs.InformsInvalid as invalid:
            return JSONResponse(
                status_code=422,
                content={"reason": "informs_invalid", "index": invalid.index, "detail": invalid.detail},
            )
        except RevisionIntegrityError:
            return JSONResponse(status_code=500, content={"detail": "revision_integrity_error"})
    return _stored(stored)


@derived_asset_router.put(_INFORMS_PATH)
async def put_block_informs(asset_id: str, block_id: str, request: Request) -> Response:
    """Replace one Write block's informs (signed rev 8.10 §1.11a)."""
    owner = _reader_owner_id(request)
    raw = await request.body()
    # The write lock is a blocking wait; keep it off the event loop.
    return await asyncio.to_thread(_put_informs, owner, asset_id, block_id, raw)

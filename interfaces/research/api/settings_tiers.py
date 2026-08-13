"""Operator-settable chunk tier overrides — OYM P1 §5 (visible tiers, write half).

The read half (P0, PR #3064) renders ``chunk_tier_overrides`` in the
Explain panel; this module is the user-settable WRITE half:

- ``GET  /settings/tier-overrides?chunk_id=...`` — the chunk's append-only
  override history (newest first) plus the tier the chunk currently
  carries (its source document's ``source_tier`` — the same value the
  Explain panel's tier chips render; ``chunks`` has no tier column, the
  tier lives on ``documents``).
- ``POST /settings/tier-overrides`` — append one override row
  (``{chunk_id, override_tier, reason}``) through the sanctioned writer
  ``middleware/source_tier/overrides_db.record_chunk_tier_override``,
  stamped with the request owner's id.

Honesty rules (load-bearing):

  * The table is an APPEND-ONLY audit trail — there is no delete and no
    update; a newer override supersedes an older one. The API never
    offers one, and ``reason`` is mandatory because an audit row without
    a rationale is a lie (400 with an honest message, not a pydantic 422).
  * ``original_tier`` is the chunk's tier AT WRITE TIME, read from the
    same locked connection that appends the row — no TOCTOU window
    between reading the tier and recording it.
  * A missing store is an honest 404 (``chunk not found``), never a
    creation event: a GET must not initialize a store (P0 read-only
    discipline), and a POST cannot validly target a chunk that does not
    exist.
  * Lock contention surfaces as 503 (the account-memory write pattern):
    ``connect_write`` blocks up to ``_LOCK_TIMEOUT_S`` for the exclusive
    flock, and a timeout means the graph is busy with another writer —
    retrying later is the honest answer, not a fabricated row.
  * Every 4xx/5xx is value-free: no submitted chunk ids, tiers, or
    reasons echo back in error details.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import duckdb
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from middleware.source_tier.overrides_db import record_chunk_tier_override
from runtime.db_lock import WriteLockTimeout, connect_read, connect_write
from substrate.graph import default_db_path

from .settings_models_admin import request_owner_user_id

settings_tiers_router = APIRouter(prefix="/settings", tags=["settings"])

# HTTP endpoints wait a bounded window for the exclusive flock; the ingest
# cron can legitimately hold it for minutes, so 15s is a compromise between
# "settings must answer promptly" and "don't 503 through a normal ingest".
_LOCK_TIMEOUT_S = 15.0

_MAX_CHUNK_ID_CHARS = 512
_MAX_REASON_CHARS = 2_048
_MAX_BODY_BYTES = 16_384

_BODY_FIELDS = frozenset({"chunk_id", "override_tier", "reason"})


class TierOverrideRow(BaseModel):
    """One ``chunk_tier_overrides`` row — same wire shape the Explain panel
    already renders (``explain_routes._load_chunk_tier_overrides``)."""

    chunk_id: str
    original_tier: int
    override_tier: int
    set_by: str | None
    reason: str
    set_at: str | None


class TierOverridesResponse(BaseModel):
    """GET payload: the chunk's current tier for context + its override
    history, newest first."""

    chunk_id: str
    current_original_tier: int
    overrides: list[TierOverrideRow]


def _resolve_db_path() -> str | None:
    """Resolve the graph DB path WITHOUT creating or mutating it.

    Same discipline as ``explain_routes._resolve_db_path``: a missing
    store is an honest 404, never a creation event (a GET must not
    initialize a store, and a POST cannot target a chunk that cannot
    exist without one).
    """
    path = os.path.expanduser(default_db_path())
    if not os.path.exists(path):
        return None
    return path


def _iso(value: Any) -> str | None:
    """Serialize a DuckDB timestamp / None to an ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return str(value.isoformat())
    except AttributeError:
        return str(value)


def _override_row(row: Any) -> TierOverrideRow:
    return TierOverrideRow(
        chunk_id=row[0],
        original_tier=row[1],
        override_tier=row[2],
        set_by=row[3],
        reason=row[4],
        set_at=_iso(row[5]),
    )


def _chunk_current_tier(con: Any, chunk_id: str) -> int | None:
    """The tier the chunk currently carries: its source document's
    ``source_tier`` (chunks have no tier column; documents do). None when
    the chunk (or its document) does not exist."""
    row = con.execute(
        "SELECT d.source_tier FROM chunks c "
        "JOIN documents d ON d.document_id = c.document_id "
        "WHERE c.chunk_id = ?",
        [chunk_id],
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def _validate_chunk_id(chunk_id: object) -> str:
    if not isinstance(chunk_id, str):
        raise HTTPException(status_code=400, detail="chunk_id is invalid")
    normalized = chunk_id.strip()
    if not normalized or len(normalized) > _MAX_CHUNK_ID_CHARS:
        raise HTTPException(status_code=400, detail="chunk_id is invalid")
    return normalized


def _validate_override_tier(value: object) -> int:
    # Strict int semantics: bool is an int subclass and must not count as a
    # tier, and a JSON float/string must not be coerced into one. The POST
    # body is parsed BY HAND (settings_models_admin precedent) so every 4xx
    # is a value-free 400 — pydantic's 422 echo would reflect submitted
    # values back at the client.
    if type(value) is not int or not 1 <= value <= 5:
        raise HTTPException(
            status_code=400,
            detail=(
                "override_tier must be an integer 1..5 "
                "(1 = strongest, 5 = weakest)"
            ),
        )
    return value


def _validate_reason(reason: object) -> str:
    if not isinstance(reason, str):
        raise HTTPException(status_code=400, detail="reason is invalid")
    normalized = reason.strip()
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail=(
                "reason is required: chunk_tier_overrides is an append-only "
                "audit trail, and every entry must say why"
            ),
        )
    if len(normalized) > _MAX_REASON_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"reason must be at most {_MAX_REASON_CHARS} characters",
        )
    return normalized


async def _parse_body(request: Request) -> dict[str, object]:
    """Parse + bound the JSON POST body BY HAND.

    Mirror of ``settings_models_admin``'s manual-parsing discipline:
    FastAPI's ``RequestValidationError`` echoes the offending input in the
    422 body; manual parsing keeps every 4xx value-free and lets semantic
    refusals (bad tier, empty reason) be honest 400s instead of pydantic
    422s. Body is bounded to ``_MAX_BODY_BYTES`` before any parse.
    """
    declared = request.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) < 1 or int(declared) > _MAX_BODY_BYTES:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=400, detail="tier override request is invalid"
            ) from None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(
                status_code=400, detail="tier override request is invalid"
            )
        body.extend(chunk)
    try:
        payload = json.loads(bytes(body))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400, detail="tier override request is invalid"
        ) from None
    if not isinstance(payload, dict) or set(payload) != _BODY_FIELDS:
        raise HTTPException(
            status_code=400, detail="tier override request is invalid"
        )
    return payload


def _unavailable(exc: Exception) -> HTTPException:
    # Deliberately do not interpolate database, identity, or submitted values.
    return HTTPException(status_code=503, detail="chunk tier override unavailable")


@settings_tiers_router.get("/tier-overrides", response_model=TierOverridesResponse)
def get_chunk_tier_overrides(
    chunk_id: str = Query(..., description="chunk whose override history to list"),
) -> TierOverridesResponse:
    """One chunk's append-only override history, newest first, plus the
    tier it currently carries."""
    normalized = _validate_chunk_id(chunk_id)
    db = _resolve_db_path()
    if db is None:
        raise HTTPException(
            status_code=404, detail=f"chunk {normalized!r} not found"
        )
    con = connect_read(db)
    try:
        current = _chunk_current_tier(con, normalized)
        if current is None:
            raise HTTPException(
                status_code=404, detail=f"chunk {normalized!r} not found"
            )
        rows = con.execute(
            "SELECT chunk_id, original_tier, override_tier, set_by, reason, set_at "
            "FROM chunk_tier_overrides WHERE chunk_id = ? "
            "ORDER BY set_at DESC, chunk_id",
            [normalized],
        ).fetchall()
    finally:
        con.close()
    return TierOverridesResponse(
        chunk_id=normalized,
        current_original_tier=current,
        overrides=[_override_row(row) for row in rows],
    )


@settings_tiers_router.post(
    "/tier-overrides", response_model=TierOverrideRow
)
async def create_chunk_tier_override(request: Request) -> TierOverrideRow:
    """Append one override row to the audit trail.

    The chunk's current tier is read on the SAME locked write connection
    that appends the row, so ``original_tier`` can never race a retier
    between read and write.
    """
    payload = await _parse_body(request)
    normalized_chunk_id = _validate_chunk_id(payload["chunk_id"])
    override_tier = _validate_override_tier(payload["override_tier"])
    reason = _validate_reason(payload["reason"])
    owner = request_owner_user_id(request)

    db = _resolve_db_path()
    if db is None:
        raise HTTPException(
            status_code=404, detail=f"chunk {normalized_chunk_id!r} not found"
        )
    set_at = datetime.now(UTC)
    try:
        with connect_write(db, purpose="tier_override_write", timeout_s=_LOCK_TIMEOUT_S) as con:
            original_tier = _chunk_current_tier(con, normalized_chunk_id)
            if original_tier is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"chunk {normalized_chunk_id!r} not found",
                )
            record_chunk_tier_override(
                con,
                chunk_id=normalized_chunk_id,
                original_tier=original_tier,
                override_tier=override_tier,
                reason=reason,
                set_by=owner,
                set_at=set_at,
            )
            row = con.execute(
                "SELECT chunk_id, original_tier, override_tier, set_by, reason, set_at "
                "FROM chunk_tier_overrides WHERE chunk_id = ? AND set_at = ?",
                [normalized_chunk_id, set_at.astimezone(UTC).replace(tzinfo=None)],
            ).fetchone()
    except HTTPException:
        raise
    except (WriteLockTimeout, OSError, duckdb.Error) as exc:
        raise _unavailable(exc) from None
    if row is None:  # defensive: the insert above must be visible on this con
        raise HTTPException(status_code=503, detail="chunk tier override unavailable")
    return _override_row(row)


def register_settings_tiers_routes(app: FastAPI) -> None:
    """Mount the tier-override router. Additive; safe to call once per app."""
    app.include_router(settings_tiers_router)


__all__ = [
    "TierOverrideRow",
    "TierOverridesResponse",
    "create_chunk_tier_override",
    "get_chunk_tier_overrides",
    "register_settings_tiers_routes",
    "settings_tiers_router",
]

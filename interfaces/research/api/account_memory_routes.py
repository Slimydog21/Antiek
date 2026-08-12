"""Authenticated, durable owner-private account-memory HTTP surface."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from runtime.db_lock import WriteLockTimeout, connect_write
from substrate.graph import default_db_path
from substrate.memory import (
    MemoryItem,
    load_memory_timeline,
    recall_memory,
    route_memory_update,
    write_memory_item,
)

from .account_memory_identity import SESSION_AUTH_METHOD, distinct_signed_owner

_MAX_PROVENANCE_BYTES = 8_192
_MAX_BODY_BYTES = 16_384

account_memory_router = APIRouter(prefix="/account/memory", tags=["account-memory"])


class AccountMemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=256)
    predicate: str = Field(min_length=1, max_length=128)
    object: str = Field(min_length=1, max_length=4_096)
    provenance: dict[str, JsonValue]
    valid_from: datetime

    @field_validator("subject", "predicate", "object")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("provenance")
    @classmethod
    def _bounded_provenance(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if any(key.strip().casefold().startswith("authority_") for key in value):
            raise ValueError("provenance authority fields are server-owned")
        try:
            encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("provenance must be finite JSON") from exc
        if len(encoded.encode("utf-8")) > _MAX_PROVENANCE_BYTES:
            raise ValueError("provenance is too large")
        return value

    @field_validator("valid_from")
    @classmethod
    def _bounded_valid_from(cls, value: datetime) -> datetime:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if normalized.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("valid_from cannot be in the future")
        return value


class AccountMemoryItem(BaseModel):
    memory_id: str
    edge_id: str
    subject: str
    predicate: str
    object: str
    provenance: dict[str, JsonValue]
    valid_from: datetime
    valid_to: datetime | None
    superseded_by: str | None


class AccountMemoryWriteResponse(BaseModel):
    action: str
    item: AccountMemoryItem


class AccountMemoryListResponse(BaseModel):
    items: list[AccountMemoryItem]


def _owner(request: Request) -> str:
    owner = distinct_signed_owner(request)
    if owner is None:
        raise HTTPException(status_code=401, detail="signed owner identity required")
    return owner


def _safe_item(item: MemoryItem) -> AccountMemoryItem:
    return AccountMemoryItem(
        memory_id=item.memory_id,
        edge_id=item.edge_id,
        subject=item.subject,
        predicate=item.predicate,
        object=item.object,
        provenance=item.provenance,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        superseded_by=item.superseded_by,
    )


def _unavailable(exc: Exception) -> HTTPException:
    # Deliberately do not interpolate database, identity, or submitted values.
    return HTTPException(status_code=503, detail="account memory unavailable")


async def _bounded_json_object(request: Request) -> dict[str, Any]:
    declared = request.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) < 1 or int(declared) > _MAX_BODY_BYTES:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="memory request is invalid") from None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=400, detail="memory request is invalid")
        body.extend(chunk)
    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="memory request is invalid") from None
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=422, detail="memory write is invalid")
    return decoded


@account_memory_router.post("", response_model=AccountMemoryWriteResponse)
async def write_account_memory(request: Request) -> AccountMemoryWriteResponse:
    owner = _owner(request)
    raw_payload = await _bounded_json_object(request)
    try:
        payload = AccountMemoryWrite.model_validate(raw_payload)
    except ValidationError:
        # Pydantic's default 422 includes the rejected input; keep private values out.
        raise HTTPException(status_code=422, detail="memory write is invalid") from None
    provenance = dict(payload.provenance)
    provenance["authority"] = SESSION_AUTH_METHOD
    request_id = request.headers.get("X-Request-Id", "").strip()
    if request_id and len(request_id) <= 256:
        provenance["authority_request_id"] = request_id
    try:
        encoded_provenance = json.dumps(provenance, allow_nan=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="memory write is invalid") from None
    if len(encoded_provenance) > _MAX_PROVENANCE_BYTES:
        raise HTTPException(status_code=422, detail="memory write is invalid")
    try:
        candidate = MemoryItem(
            memory_id="candidate",
            edge_id="candidate",
            owner_user_id=owner,
            subject=payload.subject,
            predicate=payload.predicate,
            object=payload.object,
            provenance=provenance,
            valid_from=payload.valid_from,
            created_at=payload.valid_from,
        )
        with connect_write(default_db_path(), purpose="account_memory_write") as con:
            timeline = load_memory_timeline(con, candidate)
            decision = route_memory_update(timeline, candidate)
            item = (
                decision.matched_item
                if decision.action == "NOOP"
                else write_memory_item(
                    con,
                    owner_user_id=owner,
                    subject=candidate.subject,
                    predicate=candidate.predicate,
                    object=candidate.object,
                    provenance=candidate.provenance,
                    valid_from=candidate.valid_from,
                )
            )
    except (WriteLockTimeout, OSError, duckdb.Error) as exc:
        raise _unavailable(exc) from None
    except ValueError:
        raise HTTPException(status_code=422, detail="memory write is invalid") from None
    if item is None:  # defensive: every NOOP has a matched current item
        raise HTTPException(status_code=503, detail="account memory unavailable")
    return AccountMemoryWriteResponse(action=decision.action, item=_safe_item(item))


@account_memory_router.get("", response_model=AccountMemoryListResponse)
def get_account_memory(
    request: Request,
) -> AccountMemoryListResponse:
    owner = _owner(request)
    q = request.query_params.get("q")
    if q is not None and len(q) > 512:
        raise HTTPException(status_code=422, detail="memory query is invalid")
    raw_limit = request.query_params.get("limit", "8")
    try:
        limit = int(raw_limit)
    except ValueError:
        raise HTTPException(status_code=422, detail="memory query is invalid") from None
    if not 1 <= limit <= 50:
        raise HTTPException(status_code=422, detail="memory query is invalid")
    try:
        with connect_write(default_db_path(), purpose="account_memory_recall") as con:
            items = recall_memory(con, owner, query=q, limit=limit)
    except (WriteLockTimeout, OSError, duckdb.Error) as exc:
        raise _unavailable(exc) from None
    return AccountMemoryListResponse(items=[_safe_item(item) for item in items])


__all__ = ["account_memory_router"]

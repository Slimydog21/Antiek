"""Bridge-only HTTP transport for canonical agent work."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from substrate.agent_work.service import (
    CompleteReplyCommand,
    LeaseWorkCommand,
    MarkSubmittedCommand,
    complete_agent_reply,
    lease_agent_work,
    mark_agent_work_submitted,
)
from substrate.agent_work.store import LeaseConflict, WorkLease
from substrate.graph import default_db_path, ensure_initialized

from .bridge_auth import BridgePrincipal, authenticate_bridge

agent_work_router = APIRouter(prefix="/internal/agent-work", tags=["agent-work-bridge"])


class LeaseIn(BaseModel):
    model_config = {"extra": "forbid"}

    bridge_instance_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=120, ge=1, le=300)


class SubmittedIn(BaseModel):
    model_config = {"extra": "forbid"}

    attempt_no: int = Field(gt=0)
    adapter_version: str = Field(min_length=1, max_length=128)
    herdr_target_observed: str = Field(min_length=1, max_length=256)


class ResultIn(BaseModel):
    model_config = {"extra": "forbid"}

    attempt_no: int = Field(gt=0)
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal["reply"]
    reply_markdown: str = Field(min_length=1, max_length=32768)


def _require_enabled() -> None:
    if os.environ.get("ANTIEK_AGENT_WORK_BRIDGE_ENABLED", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        raise HTTPException(status_code=404, detail="not found")


def _idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not 16 <= len(key) <= 160 or not key.isascii() or not key.isprintable():
        raise HTTPException(status_code=400, detail="valid Idempotency-Key is required")
    return key


def _require_scope(principal: BridgePrincipal, scope: str) -> None:
    if scope not in principal.scopes:
        raise HTTPException(
            status_code=403,
            detail=f"bridge credential lacks {scope} scope",
        )


def _db_path() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


def _lease_payload(lease: WorkLease) -> dict[str, Any]:
    return {
        "work_id": lease.work_id,
        "thread_id": lease.thread_id,
        "lease_id": lease.lease_id,
        "attempt_no": lease.attempt_no,
        "logical_worker_id": lease.logical_worker_id,
        "lease_expires_at": lease.lease_expires_at.astimezone(UTC).isoformat(),
        "artifact": {
            "artifact_id": lease.artifact.artifact_id,
            "version": lease.artifact.version,
            "content_sha256": lease.artifact.content_sha256,
            "source_sha256": lease.artifact.source_sha256,
        },
        "anchor": {
            "normalization": lease.anchor.normalization,
            "node_id": lease.anchor.node_id,
            "node_text_sha256": lease.anchor.node_text_sha256,
            "start_scalar": lease.anchor.start_scalar,
            "end_scalar": lease.anchor.end_scalar,
            "quote": lease.anchor.quote,
            "prefix": lease.anchor.prefix,
            "suffix": lease.anchor.suffix,
        },
        "comment_markdown": lease.comment_markdown,
        "context_sha256": lease.context_sha256,
    }


@agent_work_router.post("/lease")
async def lease_work(
    body: LeaseIn,
    principal: Annotated[BridgePrincipal, Depends(authenticate_bridge)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any] | None:
    _require_enabled()
    _require_scope(principal, "lease")
    key = _idempotency_key(idempotency_key)
    lease_digest = hashlib.sha256(f"{principal.credential_id}\0{key}".encode()).hexdigest()
    lease = lease_agent_work(
        _db_path(),
        LeaseWorkCommand(
            logical_worker_id=principal.logical_worker_id,
            bridge_credential_id=principal.credential_id,
            bridge_instance_id=body.bridge_instance_id,
            lease_id=f"lse-{lease_digest[:24]}",
            lease_seconds=body.lease_seconds,
            idempotency_key=key,
            now=datetime.now(UTC),
        ),
    )
    return None if lease is None else _lease_payload(lease)


@agent_work_router.post("/{work_id}/leases/{lease_id}/submitted")
async def mark_submitted(
    work_id: str,
    lease_id: str,
    body: SubmittedIn,
    principal: Annotated[BridgePrincipal, Depends(authenticate_bridge)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    _require_enabled()
    _require_scope(principal, "submitted")
    key = _idempotency_key(idempotency_key)
    try:
        result = mark_agent_work_submitted(
            _db_path(),
            MarkSubmittedCommand(
                work_id=work_id,
                lease_id=lease_id,
                attempt_no=body.attempt_no,
                logical_worker_id=principal.logical_worker_id,
                bridge_credential_id=principal.credential_id,
                adapter_version=body.adapter_version,
                herdr_target_observed=body.herdr_target_observed,
                idempotency_key=key,
                now=datetime.now(UTC),
            ),
        )
    except LeaseConflict as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "work_id": result.work_id,
        "thread_id": result.thread_id,
        "state": result.state,
        "attempt_no": result.attempt_no,
        "lease_id": result.lease_id,
    }


@agent_work_router.post("/{work_id}/leases/{lease_id}/result")
async def complete_result(
    work_id: str,
    lease_id: str,
    body: ResultIn,
    principal: Annotated[BridgePrincipal, Depends(authenticate_bridge)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    _require_enabled()
    _require_scope(principal, "result")
    key = _idempotency_key(idempotency_key)
    result_digest = hashlib.sha256(f"{principal.credential_id}\0{key}".encode()).hexdigest()
    try:
        result = complete_agent_reply(
            _db_path(),
            CompleteReplyCommand(
                work_id=work_id,
                lease_id=lease_id,
                attempt_no=body.attempt_no,
                logical_worker_id=principal.logical_worker_id,
                bridge_credential_id=principal.credential_id,
                context_sha256=body.context_sha256,
                reply_item_id=f"fit-{result_digest[:24]}",
                reply_markdown=body.reply_markdown,
                agent_id=principal.logical_worker_id,
                idempotency_key=key,
                now=datetime.now(UTC),
            ),
        )
    except LeaseConflict as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "work_id": work_id,
        "state": result.state,
        "reply_item_id": result.reply_item_id,
        "thread": {
            "thread_id": result.thread.thread_id,
            "state": result.thread.state,
            "items": [
                {
                    "item_id": item.item_id,
                    "author_kind": item.author_kind,
                    "author_id": item.author_id,
                    "body_markdown": item.body_markdown,
                    "sequence": item.sequence,
                }
                for item in result.thread.items
            ],
        },
    }


__all__ = ["agent_work_router"]

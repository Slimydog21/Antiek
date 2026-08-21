"""Authenticated browser API for immutable artifact feedback threads."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from runtime.db_lock import connect_write
from substrate.feedback.anchor import ArtifactAnchorMismatch
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import (
    ResolveThreadCommand,
    create_artifact_feedback,
    resolve_feedback_thread,
)
from substrate.feedback.store import CreateThreadCommand, FeedbackStore, ThreadView
from substrate.graph import default_db_path, ensure_initialized

feedback_router = APIRouter(tags=["artifact-feedback"])


class NodeAnchorIn(BaseModel):
    model_config = {"extra": "forbid"}

    normalization: Literal["unicode-nfc-v1"] = "unicode-nfc-v1"
    node_id: str = Field(min_length=1, max_length=256)
    node_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_scalar: int = Field(ge=0)
    end_scalar: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=4096)
    prefix: str = Field(max_length=32)
    suffix: str = Field(max_length=32)


class CreateFeedbackIn(BaseModel):
    model_config = {"extra": "forbid"}

    investigation_id: str = Field(min_length=1, max_length=256)
    artifact_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    anchor: NodeAnchorIn
    body_markdown: str = Field(min_length=1, max_length=32768)


def _enabled() -> bool:
    return os.environ.get("ANTIEK_FEEDBACK_ENABLED", "").lower() in {"1", "true", "yes"}


def _db_path() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


def _owner(request: Request) -> str:
    return str(getattr(request.state, "user_id", None) or "__operator__")


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not 16 <= len(key) <= 160 or not key.isascii() or not key.isprintable():
        raise HTTPException(status_code=400, detail="valid Idempotency-Key is required")
    return key


def _thread_payload(thread: ThreadView) -> dict[str, Any]:
    return {
        "thread_id": thread.thread_id,
        "investigation_id": thread.investigation_id,
        "state": thread.state,
        "artifact": {
            "artifact_id": thread.artifact.artifact_id,
            "version": thread.artifact.version,
            "content_sha256": thread.artifact.content_sha256,
            "source_sha256": thread.artifact.source_sha256,
        },
        "anchor": {
            "normalization": thread.anchor.normalization,
            "node_id": thread.anchor.node_id,
            "node_text_sha256": thread.anchor.node_text_sha256,
            "start_scalar": thread.anchor.start_scalar,
            "end_scalar": thread.anchor.end_scalar,
            "quote": thread.anchor.quote,
            "prefix": thread.anchor.prefix,
            "suffix": thread.anchor.suffix,
        },
        "items": [
            {
                "item_id": item.item_id,
                "author_kind": item.author_kind,
                "author_id": item.author_id,
                "body_markdown": item.body_markdown,
                "sequence": item.sequence,
            }
            for item in thread.items
        ],
        "work": {
            "work_id": thread.work.work_id,
            "logical_worker_id": thread.work.logical_worker_id,
            "state": thread.work.state,
            "attempt_count": thread.work.attempt_count,
        },
    }


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="not found")


@feedback_router.post(
    "/artifacts/{artifact_id}/versions/{version}/feedback/threads",
    status_code=201,
)
async def create_feedback(
    artifact_id: str,
    version: int,
    body: CreateFeedbackIn,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    _require_enabled()
    key = _require_idempotency_key(idempotency_key)
    if version < 1:
        raise HTTPException(status_code=404, detail="artifact version not found")
    owner_user_id = _owner(request)
    request_json = body.model_dump(mode="json")
    request_sha256 = _canonical_digest(request_json)
    operation_seed = f"{owner_user_id}\0{key}".encode()
    operation_digest = hashlib.sha256(operation_seed).hexdigest()
    anchor = NodeTextAnchor(**body.anchor.model_dump())
    command = CreateThreadCommand(
        thread_id=f"fth-{operation_digest[:24]}",
        root_item_id=f"fit-{operation_digest[8:32]}",
        work_id=f"wrk-{operation_digest[16:40]}",
        owner_user_id=owner_user_id,
        investigation_id=body.investigation_id,
        logical_worker_id=os.environ.get(
            "ANTIEK_FEEDBACK_LOGICAL_WORKER_ID", "research-owner"
        ).strip()
        or "research-owner",
        artifact=ArtifactVersionRef(
            artifact_id=artifact_id,
            version=version,
            content_sha256=body.artifact_content_sha256,
            source_sha256=body.artifact_source_sha256,
        ),
        anchor=anchor,
        body_markdown=body.body_markdown,
        operation_id=f"feedback:create:{operation_digest}",
        request_sha256=request_sha256,
        context_sha256=_canonical_digest(
            {
                "artifact": [
                    artifact_id,
                    version,
                    body.artifact_content_sha256,
                    body.artifact_source_sha256,
                ],
                "anchor": body.anchor.model_dump(mode="json"),
                "comment": body.body_markdown,
            }
        ),
    )
    try:
        return _thread_payload(create_artifact_feedback(_db_path(), command))
    except ArtifactAnchorMismatch as exc:
        message = str(exc)
        status = 404 if "not found" in message else 422 if "not servable" in message else 409
        raise HTTPException(status_code=status, detail=message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@feedback_router.get("/feedback/threads/{thread_id}")
async def get_feedback(
    thread_id: str,
    request: Request,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    _require_enabled()
    with connect_write(_db_path(), purpose="feedback/read") as con:
        thread = FeedbackStore().get_thread(
            con,
            owner_user_id=_owner(request),
            thread_id=thread_id,
        )
    if thread is None:
        raise HTTPException(status_code=404, detail="feedback thread not found")
    payload = _thread_payload(thread)
    etag = f'"{_canonical_digest(payload)}"'
    candidates = {
        candidate.strip().removeprefix("W/")
        for candidate in (if_none_match or "").split(",")
    }
    if "*" in candidates or etag in candidates:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(payload, headers={"ETag": etag})


@feedback_router.post("/feedback/threads/{thread_id}/resolve")
async def resolve_feedback(
    thread_id: str,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    _require_enabled()
    try:
        thread = resolve_feedback_thread(
            _db_path(),
            ResolveThreadCommand(
                owner_user_id=_owner(request),
                thread_id=thread_id,
                idempotency_key=_require_idempotency_key(idempotency_key),
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="feedback thread not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _thread_payload(thread)


__all__ = ["feedback_router"]

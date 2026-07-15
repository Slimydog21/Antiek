"""Owner-safe paid-operation consent and queue HTTP boundary."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from substrate.paid_operations import (
    ConsentAlreadyIssued,
    ConsentConflict,
    ConsentKeyring,
    OperationConflict,
    OperationSnapshot,
    PaidOperationConsentService,
    PaidOperationStore,
    QueueSnapshot,
    Subject,
)

_AUTHENTICATED_METHODS = frozenset(
    {"antiek_session_cookie", "bearer_token", "cloudflare_access_email", "cloudflare_service_token"}
)


class PaidOperationStatus(BaseModel):
    operation_id: str
    kind: str
    intent_hash: str
    quote_cents: int
    ceiling_cents: int
    state: str
    version: int
    created_at_ms: int
    updated_at_ms: int
    expires_at_ms: int
    consent_issued_at_ms: int | None = None
    consent_expires_at_ms: int | None = None
    consent_claimed_at_ms: int | None = None


class ConsentIssueResponse(BaseModel):
    token: str
    operation: PaidOperationStatus


class QueueClaimRequest(BaseModel):
    options: dict[str, Any]


class QueueStatus(BaseModel):
    operation_id: str
    intent_hash: str
    enqueued_at_ms: int
    queue_state: str


class QueueClaimResponse(BaseModel):
    operation: PaidOperationStatus
    queue: QueueStatus


@dataclass(frozen=True)
class PaidOperationRouteRuntime:
    consent: PaidOperationConsentService


_runtime: PaidOperationRouteRuntime | None = None


def get_paid_operation_runtime() -> PaidOperationRouteRuntime:
    global _runtime
    if _runtime is None:
        db_path = os.environ.get("ANTIEK_PAID_OPERATION_DB", "").strip()
        key_id = os.environ.get("ANTIEK_PAID_OPERATION_CONSENT_KEY_ID", "").strip()
        key = os.environ.get("ANTIEK_PAID_OPERATION_CONSENT_KEY", "").encode("utf-8")
        if not db_path or not key_id or not key:
            raise RuntimeError("paid operation authority configuration is incomplete")
        store = PaidOperationStore(db_path)
        keys: dict[str, bytes] = {key_id: key}
        verification_keys = os.environ.get("ANTIEK_PAID_OPERATION_CONSENT_VERIFICATION_KEYS_JSON", "").strip()
        if verification_keys:
            try:
                decoded = json.loads(verification_keys)
            except json.JSONDecodeError as exc:
                raise RuntimeError("paid operation consent verification keyring is invalid") from exc
            if not isinstance(decoded, dict):
                raise RuntimeError("paid operation consent verification keyring is invalid")
            for verification_key_id, verification_key in decoded.items():
                if not isinstance(verification_key_id, str) or not isinstance(verification_key, str):
                    raise RuntimeError("paid operation consent verification keyring is invalid")
                candidate = verification_key.encode("utf-8")
                if verification_key_id in keys and keys[verification_key_id] != candidate:
                    raise RuntimeError("active consent key conflicts with verification keyring")
                keys[verification_key_id] = candidate
        keyring = ConsentKeyring(active_key_id=key_id, keys=keys)
        keyring.active_key()
        for verification_key_id in keys:
            keyring.key(verification_key_id)
        _runtime = PaidOperationRouteRuntime(
            consent=PaidOperationConsentService(store, keyring, clock_ms=lambda: int(time.time() * 1000))
        )
    return _runtime


def set_paid_operation_runtime(runtime: PaidOperationRouteRuntime | None) -> None:
    global _runtime
    _runtime = runtime


def authenticated_paid_operation_subject(request: Request) -> Subject:
    method = getattr(request.state, "auth_method", None)
    owner = getattr(request.state, "user_id", None)
    account = getattr(request.state, "account_id", None)
    if account is None:
        account = getattr(request.state, "tenant_id", None)
    if method not in _AUTHENTICATED_METHODS or not isinstance(owner, str) or not isinstance(account, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    owner = owner.strip()
    account = account.strip()
    if not owner or not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return Subject(owner_user_id=owner, account_id=account)


paid_operation_router = APIRouter(prefix="/paid-operations", tags=["paid-operations"])


@paid_operation_router.post("/{operation_id}/consent", response_model=ConsentIssueResponse)
def issue_paid_operation_consent(
    operation_id: str,
    response: Response,
    subject: Subject = Depends(authenticated_paid_operation_subject),
    runtime: PaidOperationRouteRuntime = Depends(get_paid_operation_runtime),
) -> ConsentIssueResponse:
    try:
        issued = runtime.consent.issue(subject, operation_id)
    except ConsentAlreadyIssued as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "consent_already_issued", "operation": _status(exc.snapshot).model_dump()},
        ) from exc
    except OperationConflict as exc:
        raise _not_found() from exc
    response.headers["Cache-Control"] = issued.cache_control
    return ConsentIssueResponse(token=issued.token, operation=_status(issued.snapshot))


@paid_operation_router.post("/{operation_id}/queue", response_model=QueueClaimResponse)
def claim_paid_operation_queue(
    operation_id: str,
    body: QueueClaimRequest,
    consent_token: str | None = Header(default=None, alias="X-Antiek-Paid-Consent"),
    subject: Subject = Depends(authenticated_paid_operation_subject),
    runtime: PaidOperationRouteRuntime = Depends(get_paid_operation_runtime),
) -> QueueClaimResponse:
    try:
        result = runtime.consent.claim(
            subject,
            operation_id,
            token=consent_token,
            options=body.options,
        )
    except ConsentConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "consent_unclaimable"}) from exc
    except OperationConflict as exc:
        raise _not_found() from exc
    return QueueClaimResponse(operation=_status(result.snapshot), queue=_queue_status(result.queue))


def register_paid_operation_routes(app: FastAPI) -> None:
    configured = (
        os.environ.get("ANTIEK_PAID_OPERATION_DB", "").strip(),
        os.environ.get("ANTIEK_PAID_OPERATION_CONSENT_KEY_ID", "").strip(),
        os.environ.get("ANTIEK_PAID_OPERATION_CONSENT_KEY", "").strip(),
    )
    verification_keys = os.environ.get("ANTIEK_PAID_OPERATION_CONSENT_VERIFICATION_KEYS_JSON", "").strip()
    if not any((*configured, verification_keys)):
        return
    if not all(configured):
        raise RuntimeError("paid operation authority configuration is incomplete")
    runtime = get_paid_operation_runtime()
    set_paid_operation_runtime(runtime)
    app.include_router(paid_operation_router)


def _status(snapshot: OperationSnapshot) -> PaidOperationStatus:
    return PaidOperationStatus(
        operation_id=snapshot.operation_id,
        kind=snapshot.kind,
        intent_hash=snapshot.intent_hash,
        quote_cents=snapshot.quote_cents,
        ceiling_cents=snapshot.ceiling_cents,
        state=snapshot.state,
        version=snapshot.version,
        created_at_ms=snapshot.created_at_ms,
        updated_at_ms=snapshot.updated_at_ms,
        expires_at_ms=snapshot.expires_at_ms,
        consent_issued_at_ms=snapshot.consent_issued_at_ms,
        consent_expires_at_ms=snapshot.consent_expires_at_ms,
        consent_claimed_at_ms=snapshot.consent_claimed_at_ms,
    )


def _queue_status(queue: QueueSnapshot) -> QueueStatus:
    return QueueStatus(
        operation_id=queue.operation_id,
        intent_hash=queue.intent_hash,
        enqueued_at_ms=queue.enqueued_at_ms,
        queue_state=queue.queue_state,
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "paid_operation_unavailable"})


__all__ = [
    "PaidOperationRouteRuntime",
    "authenticated_paid_operation_subject",
    "paid_operation_router",
    "register_paid_operation_routes",
    "set_paid_operation_runtime",
]

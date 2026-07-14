"""Durable idempotent issuance for multimedia execution authorizations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from runtime.db_lock import FlockWriteCoordinator
from substrate.multimedia.execution_authorization import (
    MAX_CENTS,
    MultimediaExecutionAuthorization,
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
    issue_execution_authorization,
    verify_async_execution_authorization,
    verify_execution_authorization,
)


class ExecutionAuthorizationIssueConflict(RuntimeError):
    """An idempotency key was replayed with different authorization terms."""


@dataclass(frozen=True)
class ExecutionAuthorizationIssueRequest:
    request_id: str
    operator_id: str
    asset_id: str
    revision_id: str
    provider: str
    route_policy: str
    approved_ceiling_cents: int
    ttl_seconds: int


@dataclass(frozen=True)
class AsyncExecutionAuthorizationIssueRequest:
    request_id: str
    operator_id: str
    asset_id: str
    revision_id: str
    provider: str
    route_policy: str
    model: str
    endpoint_capability: str
    catalog_version: str
    catalog_digest: str
    quote_id: str
    quote_ttl_seconds: int
    recovery_authority_id: str
    recovery_verification_key_digest: str
    approved_ceiling_microdollars: int
    request_body_digest: str
    ttl_seconds: int


_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_execution_authorization_issues (
    operator_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (operator_id, request_id)
)
"""


class ExecutionAuthorizationIssuer:
    """Issue once per operator/request id and replay the exact signed receipt."""

    def __init__(self, *, db_path: str, signing_key: bytes) -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path is required")
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("signing_key must contain at least 32 bytes")
        self._db_path = db_path
        self._signing_key = signing_key

    def issue(
        self,
        request: ExecutionAuthorizationIssueRequest,
        *,
        now: datetime,
    ) -> MultimediaExecutionAuthorization:
        request_hash = _request_hash(request)
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.execution_authorization.issue") as ctx:
            ctx.execute(_DDL)
            ctx.execute("BEGIN TRANSACTION")
            try:
                existing = ctx.execute(
                    "SELECT request_hash, receipt_json "
                    "FROM multimedia_execution_authorization_issues "
                    "WHERE operator_id = ? AND request_id = ?",
                    [request.operator_id, request.request_id],
                ).fetchone()
                if existing is not None:
                    if existing[0] != request_hash:
                        raise ExecutionAuthorizationIssueConflict(
                            "authorization request id already has different terms"
                        )
                    receipt = _load_receipt(existing[1])
                    _verify_stored(receipt, request, self._signing_key)
                    ctx.execute("COMMIT")
                    return receipt

                receipt = issue_execution_authorization(
                    signing_key=self._signing_key,
                    request_id=request.request_id,
                    operator_id=request.operator_id,
                    asset_id=request.asset_id,
                    revision_id=request.revision_id,
                    provider=request.provider,
                    route_policy=request.route_policy,
                    approved_ceiling_cents=request.approved_ceiling_cents,
                    issued_at=now,
                    expires_at=now + timedelta(seconds=_ttl_seconds(request.ttl_seconds)),
                )
                ctx.execute(
                    "INSERT INTO multimedia_execution_authorization_issues "
                    "(operator_id, request_id, request_hash, receipt_json, created_at) "
                    "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    [
                        request.operator_id,
                        request.request_id,
                        request_hash,
                        json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")),
                    ],
                )
            except Exception:
                ctx.execute("ROLLBACK")
                raise
            else:
                ctx.execute("COMMIT")
                return receipt

    def issue_async(
        self,
        request: AsyncExecutionAuthorizationIssueRequest,
        *,
        now: datetime,
    ) -> MultimediaExecutionAuthorizationV2:
        """Issue or exactly replay one v2 async execution authorization."""
        request_hash = _async_request_hash(request)
        ttl = _ttl_seconds(request.ttl_seconds)
        quote_ttl = _quote_ttl_seconds(request.quote_ttl_seconds, ttl)
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context(
            "multimedia.execution_authorization.issue_async"
        ) as ctx:
            ctx.execute(_DDL)
            ctx.execute("BEGIN TRANSACTION")
            try:
                existing = ctx.execute(
                    "SELECT request_hash, receipt_json "
                    "FROM multimedia_execution_authorization_issues "
                    "WHERE operator_id = ? AND request_id = ?",
                    [request.operator_id, request.request_id],
                ).fetchone()
                if existing is not None:
                    if existing[0] != request_hash:
                        raise ExecutionAuthorizationIssueConflict(
                            "authorization request id already has different terms"
                        )
                    receipt = _load_async_receipt(existing[1])
                    _verify_stored_async(receipt, request, self._signing_key)
                    ctx.execute("COMMIT")
                    return receipt
                receipt = issue_async_execution_authorization(
                    signing_key=self._signing_key,
                    request_id=request.request_id,
                    operator_id=request.operator_id,
                    asset_id=request.asset_id,
                    revision_id=request.revision_id,
                    provider=request.provider,
                    route_policy=request.route_policy,
                    model=request.model,
                    endpoint_capability=request.endpoint_capability,
                    catalog_version=request.catalog_version,
                    catalog_digest=request.catalog_digest,
                    quote_id=request.quote_id,
                    quote_expires_at=now + timedelta(seconds=quote_ttl),
                    recovery_authority_id=request.recovery_authority_id,
                    recovery_verification_key_digest=(request.recovery_verification_key_digest),
                    approved_ceiling_microdollars=(request.approved_ceiling_microdollars),
                    request_body_digest=request.request_body_digest,
                    issued_at=now,
                    expires_at=now + timedelta(seconds=ttl),
                )
                ctx.execute(
                    "INSERT INTO multimedia_execution_authorization_issues "
                    "(operator_id, request_id, request_hash, receipt_json, created_at) "
                    "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    [
                        request.operator_id,
                        request.request_id,
                        request_hash,
                        json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")),
                    ],
                )
            except Exception:
                ctx.execute("ROLLBACK")
                raise
            else:
                ctx.execute("COMMIT")
                return receipt


def _request_hash(request: ExecutionAuthorizationIssueRequest) -> str:
    if (
        isinstance(request.approved_ceiling_cents, bool)
        or not isinstance(request.approved_ceiling_cents, int)
        or request.approved_ceiling_cents <= 0
        or request.approved_ceiling_cents > MAX_CENTS
    ):
        raise ValueError("approved_ceiling_cents must be a positive signed-BIGINT integer")
    _ttl_seconds(request.ttl_seconds)
    value = {
        "asset_id": request.asset_id,
        "approved_ceiling_cents": request.approved_ceiling_cents,
        "operator_id": request.operator_id,
        "provider": request.provider,
        "request_id": request.request_id,
        "revision_id": request.revision_id,
        "route_policy": request.route_policy,
        "ttl_seconds": request.ttl_seconds,
    }
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _async_request_hash(request: AsyncExecutionAuthorizationIssueRequest) -> str:
    if (
        isinstance(request.approved_ceiling_microdollars, bool)
        or not isinstance(request.approved_ceiling_microdollars, int)
        or request.approved_ceiling_microdollars <= 0
        or request.approved_ceiling_microdollars > MAX_CENTS
    ):
        raise ValueError("approved_ceiling_microdollars must be a positive signed-BIGINT integer")
    ttl = _ttl_seconds(request.ttl_seconds)
    _quote_ttl_seconds(request.quote_ttl_seconds, ttl)
    encoded = json.dumps(
        request.__dict__,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _ttl_seconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("ttl_seconds must be an integer")
    if value < 60 or value > 3600:
        raise ValueError("ttl_seconds must be between 60 and 3600")
    return value


def _quote_ttl_seconds(value: object, authorization_ttl: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("quote_ttl_seconds must be an integer")
    if value < 1 or value > authorization_ttl:
        raise ValueError("quote_ttl_seconds must be positive and no more than ttl_seconds")
    return value


def _load_receipt(value: object) -> MultimediaExecutionAuthorization:
    if not isinstance(value, str):
        raise RuntimeError("stored multimedia authorization is malformed")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("stored multimedia authorization is malformed") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("stored multimedia authorization is malformed")
    return MultimediaExecutionAuthorization.from_dict(decoded)


def _load_async_receipt(value: object) -> MultimediaExecutionAuthorizationV2:
    if not isinstance(value, str):
        raise RuntimeError("stored asynchronous multimedia authorization is malformed")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("stored asynchronous multimedia authorization is malformed") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("stored asynchronous multimedia authorization is malformed")
    return MultimediaExecutionAuthorizationV2.from_dict(decoded)


def _verify_stored(
    receipt: MultimediaExecutionAuthorization,
    request: ExecutionAuthorizationIssueRequest,
    signing_key: bytes,
) -> None:
    issued_at = datetime.fromisoformat(receipt.issued_at.replace("Z", "+00:00"))
    verify_execution_authorization(
        receipt,
        signing_key=signing_key,
        operator_id=request.operator_id,
        asset_id=request.asset_id,
        revision_id=request.revision_id,
        provider=request.provider,
        route_policy=request.route_policy,
        now=issued_at,
    )


def _verify_stored_async(
    receipt: MultimediaExecutionAuthorizationV2,
    request: AsyncExecutionAuthorizationIssueRequest,
    signing_key: bytes,
) -> None:
    issued_at = datetime.fromisoformat(receipt.issued_at.replace("Z", "+00:00"))
    verify_async_execution_authorization(
        receipt,
        signing_key=signing_key,
        operator_id=request.operator_id,
        asset_id=request.asset_id,
        revision_id=request.revision_id,
        provider=request.provider,
        route_policy=request.route_policy,
        model=request.model,
        endpoint_capability=request.endpoint_capability,
        catalog_version=request.catalog_version,
        catalog_digest=request.catalog_digest,
        quote_id=request.quote_id,
        recovery_authority_id=request.recovery_authority_id,
        recovery_verification_key_digest=(request.recovery_verification_key_digest),
        approved_ceiling_microdollars=request.approved_ceiling_microdollars,
        request_body_digest=request.request_body_digest,
        now=issued_at,
    )


__all__ = [
    "AsyncExecutionAuthorizationIssueRequest",
    "ExecutionAuthorizationIssueConflict",
    "ExecutionAuthorizationIssueRequest",
    "ExecutionAuthorizationIssuer",
]

"""Unmounted operator-safe operations over signed provider executions."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .operations_read_model import MultimediaExecutionPage, MultimediaExecutionView
from .provider_execution import (
    _ALLOWED_TRANSITIONS,
    ProviderExecutionIntegrityError,
    ProviderExecutionRecord,
    ProviderExecutionStatus,
    _record,
    _record_mac,
)

_OPAQUE_MESSAGE = "multimedia execution is unavailable"
_WAKE_REASONS = frozenset({"manual", "stale", "outcome_unknown", "webhook_wake"})
_STORE_ERRORS = (ProviderExecutionIntegrityError, TypeError, ValueError)
_WAKE_ELIGIBLE = frozenset(
    {
        ProviderExecutionStatus.SUBMITTED,
        ProviderExecutionStatus.RUNNING,
        ProviderExecutionStatus.CANCEL_REQUESTED,
        ProviderExecutionStatus.CANCEL_ACKNOWLEDGED,
        ProviderExecutionStatus.OUTCOME_UNKNOWN,
    }
)


class MultimediaExecutionUnavailable(LookupError):
    """Opaque missing-or-not-owned result."""


class MultimediaOperationConflict(RuntimeError):
    """A replay or persisted operation record conflicts with signed authority."""


class MultimediaOperationRateLimited(RuntimeError):
    """The operator/job wake budget is exhausted for the current window."""


@dataclass(frozen=True)
class ReconciliationWakeReceipt:
    wake_id: str
    execution_id: str
    reason: str
    requested_at: str


@dataclass(frozen=True)
class KillSwitchPolicy:
    all_paid_disabled: bool = False
    disabled_providers: frozenset[str] = frozenset()
    disabled_models: frozenset[str] = frozenset()
    disabled_routes: frozenset[str] = frozenset()
    webhook_disabled: bool = False
    artifact_fetch_disabled: bool = False

    def __post_init__(self) -> None:
        for selectors in (
            self.disabled_providers,
            self.disabled_models,
            self.disabled_routes,
        ):
            if not isinstance(selectors, frozenset) or any(
                not _valid_label(item) for item in selectors
            ):
                raise ValueError("kill-switch selectors must be bounded canonical labels")
        for flag in (
            self.all_paid_disabled,
            self.webhook_disabled,
            self.artifact_fetch_disabled,
        ):
            if not isinstance(flag, bool):
                raise ValueError("kill-switch flags must be booleans")

    def blocks_paid_start(self, *, provider: str, model: str, route_policy: str) -> bool:
        provider = _label("provider", provider)
        model = _label("model", model)
        route_policy = _label("route_policy", route_policy)
        return (
            self.all_paid_disabled
            or provider in self.disabled_providers
            or model in self.disabled_models
            or route_policy in self.disabled_routes
        )

    def allows_reads(self) -> bool:
        return True

    def allows_reconciliation(self) -> bool:
        return True


_WAKE_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_reconciliation_wake_requests (
 wake_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, operator_id TEXT NOT NULL,
 reason TEXT NOT NULL, idempotency_key TEXT NOT NULL, requested_at TEXT NOT NULL,
 wake_mac TEXT NOT NULL, UNIQUE(execution_id, idempotency_key))
"""


def get_execution(
    *, db_path: str, execution_id: object, authenticated_operator_id: object, signing_key: bytes
) -> MultimediaExecutionView:
    with connect_read(db_path) as connection:
        execution, row = _owned_execution_in_connection(
            connection,
            execution_id=execution_id,
            authenticated_operator_id=authenticated_operator_id,
            signing_key=signing_key,
        )
        return _view(connection, execution, row)


def list_executions(
    *,
    db_path: str,
    authenticated_operator_id: object,
    signing_key: bytes,
    limit: object = 50,
    after: object | None = None,
) -> MultimediaExecutionPage:
    operator_id = _opaque_identifier(authenticated_operator_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 through 100")
    cursor = None if after is None else _opaque_identifier(after)
    if not Path(db_path).exists():
        return MultimediaExecutionPage((), None)
    try:
        with connect_read(db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM multimedia_provider_executions WHERE operator_id=? "
                "AND (? IS NULL OR execution_id>?) ORDER BY execution_id LIMIT ?",
                [operator_id, cursor, cursor, limit + 1],
            ).fetchall()
            records = [(_record(row, signing_key=signing_key), row) for row in rows[:limit]]
            items = tuple(_view(connection, record, row) for record, row in records)
    except _STORE_ERRORS:
        raise MultimediaOperationConflict("multimedia execution store is invalid") from None
    next_cursor = items[-1].execution_id if len(rows) > limit and items else None
    return MultimediaExecutionPage(items, next_cursor)


def cancel_execution(
    *,
    db_path: str,
    execution_id: object,
    authenticated_operator_id: object,
    signing_key: bytes,
    now: datetime,
) -> MultimediaExecutionView:
    canonical_id = _opaque_identifier(execution_id)
    operator_id = _opaque_identifier(authenticated_operator_id)
    timestamp = _timestamp(now)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.operations.cancel") as ctx:
        ctx.execute("BEGIN TRANSACTION")
        try:
            current, row = _owned_execution_in_connection(
                ctx,
                execution_id=canonical_id,
                authenticated_operator_id=operator_id,
                signing_key=signing_key,
            )
            target = ProviderExecutionStatus.CANCEL_REQUESTED
            if current.status is not target:
                if target not in _ALLOWED_TRANSITIONS[current.status]:
                    raise MultimediaOperationConflict("execution cannot be cancelled")
                if current.provider_job_id is None:
                    raise MultimediaOperationConflict("execution has no provider job binding")
                if timestamp < current.updated_at:
                    raise MultimediaOperationConflict("cancellation predates execution state")
                values = list(row[:15]) + [
                    target.value,
                    current.provider_job_id,
                    row[17],
                    timestamp,
                    row[19],
                    row[20],
                ]
                ctx.execute(
                    "UPDATE multimedia_provider_executions SET status=?, updated_at=?, record_mac=? "
                    "WHERE execution_id=? AND operator_id=?",
                    [
                        target.value,
                        timestamp,
                        _record_mac(signing_key, values),
                        canonical_id,
                        operator_id,
                    ],
                )
                updated = ctx.execute(
                    "SELECT * FROM multimedia_provider_executions WHERE execution_id=? AND operator_id=?",
                    [canonical_id, operator_id],
                ).fetchone()
                if updated is None:
                    raise MultimediaOperationConflict("execution authority changed")
                current, row = _record(updated, signing_key=signing_key), updated
            view = _view(ctx, current, row)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return view


def request_reconciliation(
    *,
    db_path: str,
    execution_id: object,
    authenticated_operator_id: object,
    reason: object,
    idempotency_key: object,
    signing_key: bytes,
    now: datetime,
    max_requests: int = 3,
    window_seconds: int = 60,
    before_commit: object | None = None,
) -> ReconciliationWakeReceipt:
    execution, _ = _owned_execution(
        db_path=db_path,
        execution_id=execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
    )
    canonical_reason = _label("reason", reason)
    if canonical_reason not in _WAKE_REASONS:
        raise ValueError("reason is not allowed")
    key = _idempotency_key(idempotency_key)
    if not isinstance(max_requests, int) or isinstance(max_requests, bool) or max_requests < 1:
        raise ValueError("max_requests must be positive")
    if (
        not isinstance(window_seconds, int)
        or isinstance(window_seconds, bool)
        or window_seconds < 1
    ):
        raise ValueError("window_seconds must be positive")
    timestamp = _timestamp(now)
    wake_id = "mmwake_" + hashlib.sha256(f"{execution.execution_id}:{key}".encode()).hexdigest()
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.operations.reconcile_wake") as ctx:
        ctx.execute(_WAKE_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            current, _ = _owned_execution_in_connection(
                ctx,
                execution_id=execution.execution_id,
                authenticated_operator_id=execution.operator_id,
                signing_key=signing_key,
            )
            existing = ctx.execute(
                "SELECT * FROM multimedia_reconciliation_wake_requests "
                "WHERE execution_id=? AND idempotency_key=?",
                [execution.execution_id, key],
            ).fetchone()
            if existing is not None:
                receipt = _wake_receipt(existing, signing_key=signing_key)
                if existing[2] != execution.operator_id or existing[3] != canonical_reason:
                    raise MultimediaOperationConflict("reconciliation replay conflicts")
                ctx.execute("COMMIT")
                return receipt
            if current.provider_job_id is None or current.status not in _WAKE_ELIGIBLE:
                raise MultimediaOperationConflict("execution is not eligible for reconciliation")
            threshold = _timestamp(now - timedelta(seconds=window_seconds))
            count = ctx.execute(
                "SELECT count(*) FROM multimedia_reconciliation_wake_requests "
                "WHERE operator_id=? AND execution_id=? AND requested_at>=?",
                [execution.operator_id, execution.execution_id, threshold],
            ).fetchone()
            if count is None or int(count[0]) >= max_requests:
                raise MultimediaOperationRateLimited("reconciliation wake rate limited")
            values: list[object] = [
                wake_id,
                current.execution_id,
                current.operator_id,
                canonical_reason,
                key,
                timestamp,
            ]
            ctx.execute(
                "INSERT INTO multimedia_reconciliation_wake_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
                [*values, _mac(signing_key, values)],
            )
            if before_commit is not None:
                if not callable(before_commit):
                    raise ValueError("before_commit must be callable")
                before_commit(ctx)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return ReconciliationWakeReceipt(
                wake_id, current.execution_id, canonical_reason, timestamp
            )


def _owned_execution(
    *, db_path: str, execution_id: object, authenticated_operator_id: object, signing_key: bytes
) -> tuple[ProviderExecutionRecord, tuple[object, ...]]:
    try:
        canonical_id = _opaque_identifier(execution_id)
        operator_id = _opaque_identifier(authenticated_operator_id)
        with connect_read(db_path) as connection:
            row = connection.execute(
                "SELECT * FROM multimedia_provider_executions "
                "WHERE execution_id=? AND operator_id=?",
                [canonical_id, operator_id],
            ).fetchone()
        if row is None:
            raise ValueError
        return _record(row, signing_key=signing_key), row
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MultimediaExecutionUnavailable(_OPAQUE_MESSAGE) from None


def _owned_execution_in_connection(
    connection: Any,
    *,
    execution_id: object,
    authenticated_operator_id: object,
    signing_key: bytes,
) -> tuple[ProviderExecutionRecord, tuple[object, ...]]:
    try:
        canonical_id = _opaque_identifier(execution_id)
        operator_id = _opaque_identifier(authenticated_operator_id)
        row = connection.execute(
            "SELECT * FROM multimedia_provider_executions WHERE execution_id=? AND operator_id=?",
            [canonical_id, operator_id],
        ).fetchone()
        if row is None:
            raise ValueError
        return _record(row, signing_key=signing_key), row
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MultimediaExecutionUnavailable(_OPAQUE_MESSAGE) from None


def _view(
    connection: Any, execution: ProviderExecutionRecord, row: tuple[object, ...]
) -> MultimediaExecutionView:
    claim = connection.execute(
        "SELECT signature, status, actual_cents FROM multimedia_execution_authorization_claims "
        "WHERE authorization_id=?",
        [execution.authorization_id],
    ).fetchone()
    if claim is None or claim[0] != row[2]:
        raise MultimediaOperationConflict("authorization claim is invalid")
    balance = connection.execute(
        "SELECT spent_cents, held_cents FROM midnight_oil_reservations WHERE run_id=?",
        [execution.authorization_id],
    ).fetchone()
    if balance is None:
        raise MultimediaOperationConflict("execution accounting is unavailable")
    spent_cents, held_cents = int(balance[0]), int(balance[1])
    ceiling_cents = (execution.approved_ceiling_microdollars + 9_999) // 10_000
    if spent_cents < 0 or held_cents < 0 or spent_cents + held_cents > ceiling_cents:
        raise MultimediaOperationConflict("execution accounting is invalid")
    if execution.status in {
        ProviderExecutionStatus.SUBMITTING,
    } and (spent_cents, held_cents, claim[1], claim[2]) != (
        0,
        ceiling_cents,
        "claimed",
        None,
    ):
        raise MultimediaOperationConflict("execution accounting is invalid")
    if execution.status in {
        ProviderExecutionStatus.SUBMITTED,
        ProviderExecutionStatus.RUNNING,
        ProviderExecutionStatus.CANCEL_REQUESTED,
        ProviderExecutionStatus.CANCEL_ACKNOWLEDGED,
    } and (spent_cents, held_cents, claim[1], claim[2]) not in {
        (0, ceiling_cents, "claimed", None),
        (ceiling_cents, 0, "claimed", None),
    }:
        raise MultimediaOperationConflict("execution accounting is invalid")
    if execution.status is ProviderExecutionStatus.OUTCOME_UNKNOWN and (
        spent_cents,
        held_cents,
        claim[1],
        claim[2],
    ) != (ceiling_cents, 0, "claimed", None):
        raise MultimediaOperationConflict("execution accounting is invalid")
    if execution.status is ProviderExecutionStatus.SUCCEEDED and (
        spent_cents,
        held_cents,
        claim[1],
        claim[2],
    ) != (ceiling_cents, 0, "settled", ceiling_cents):
        raise MultimediaOperationConflict("execution accounting is invalid")
    if execution.status in {ProviderExecutionStatus.FAILED, ProviderExecutionStatus.CANCELLED} and (
        spent_cents,
        held_cents,
        claim[1],
        claim[2],
    ) != (0, ceiling_cents, "reconciliation_required", None):
        raise MultimediaOperationConflict("execution accounting is invalid")
    candidates = connection.execute(
        "SELECT count(*) FROM multimedia_provider_artifact_candidates WHERE execution_id=?",
        [execution.execution_id],
    ).fetchone()
    candidate_count = int(candidates[0]) if candidates else 0
    ready = 0
    table = connection.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name='multimedia_artifact_quarantine_receipts'"
    ).fetchone()
    if table and table[0]:
        result = connection.execute(
            "SELECT count(*) FROM multimedia_artifact_quarantine_receipts WHERE execution_id=?",
            [execution.execution_id],
        ).fetchone()
        ready = int(result[0]) if result else 0
    return MultimediaExecutionView(
        execution.execution_id,
        execution.status,
        execution.provider,
        execution.model,
        execution.route_policy,
        execution.approved_ceiling_microdollars,
        spent_cents,
        held_cents,
        str(claim[1]),
        execution.created_at,
        execution.updated_at,
        _cancellation_state(execution.status),
        candidate_count,
        ready,
        None,
    )


def _wake_receipt(row: tuple[object, ...], *, signing_key: bytes) -> ReconciliationWakeReceipt:
    if len(row) != 7 or not isinstance(row[6], str):
        raise MultimediaOperationConflict("reconciliation wake is invalid")
    if not hmac.compare_digest(row[6], _mac(signing_key, list(row[:6]))):
        raise MultimediaOperationConflict("reconciliation wake is invalid")
    return ReconciliationWakeReceipt(str(row[0]), str(row[1]), str(row[3]), str(row[5]))


def _cancellation_state(status: ProviderExecutionStatus) -> str:
    if status is ProviderExecutionStatus.CANCEL_REQUESTED:
        return "pending"
    if status is ProviderExecutionStatus.CANCEL_ACKNOWLEDGED:
        return "acknowledged"
    if status is ProviderExecutionStatus.CANCELLED:
        return "terminal_cancelled"
    if status in {ProviderExecutionStatus.SUCCEEDED, ProviderExecutionStatus.FAILED}:
        return "terminal_not_cancelled"
    return "not_requested"


def _opaque_identifier(value: object) -> str:
    if not isinstance(value, str) or not _valid_label(value):
        raise MultimediaExecutionUnavailable(_OPAQUE_MESSAGE)
    return value


def _label(name: str, value: object) -> str:
    if not isinstance(value, str) or not _valid_label(value):
        raise ValueError(f"{name} must be a bounded canonical label")
    return value


def _valid_label(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and all(character.isalnum() or character in "._:-" for character in value)
    )


def _idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or value != value.strip():
        raise ValueError("idempotency_key must be a bounded nonempty string")
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise ValueError("idempotency_key must contain visible ASCII")
    return value


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _mac(key: bytes, values: list[object]) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    payload = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


__all__ = [
    "KillSwitchPolicy",
    "MultimediaExecutionUnavailable",
    "MultimediaOperationConflict",
    "MultimediaOperationRateLimited",
    "ReconciliationWakeReceipt",
    "cancel_execution",
    "get_execution",
    "list_executions",
    "request_reconciliation",
]

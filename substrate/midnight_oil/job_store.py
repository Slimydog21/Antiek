"""Owner-bound durable authority for Midnight Oil jobs.

This module is intentionally not wired into the HTTP surface yet.  It defines
the storage contract that authenticated callers must use: every operation is
scoped by both the authenticated owner and the job id, and state transitions
are compare-and-set writes rather than blind updates.

DuckDB is retained to share Midnight Oil's existing single-writer discipline
and operational database tooling.  ``FlockWriteCoordinator`` serializes writes
across processes; the version predicate supplies the logical CAS invariant.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol

from runtime.db_lock import FlockWriteCoordinator, connect_read

SCHEMA_VERSION: Final = 3
MAX_APPROVED_CEILING_CENTS: Final = 1_000_000_000


class OperationState(StrEnum):
    NONE = "none"
    CONSENT_ISSUED = "consent_issued"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    BUDGET_HALTED = "budget_halted"
    TIMED_OUT = "timed_out"
    FAILED_RECONCILE = "failed_reconcile"


class StoreConstructionError(RuntimeError):
    """Raised before production startup when durable authority is unavailable."""


class InvalidStoredJob(RuntimeError):
    """A persisted row cannot safely be interpreted as authority."""


@dataclass(frozen=True)
class OwnerJob:
    owner_user_id: str
    job_id: str
    state_version: int
    approved_ceiling_cents: int | None
    consent_receipt_id: str | None
    consent_config_hash: str | None
    consent_issued_at_ms: int | None
    consent_expires_at_ms: int | None
    consent_claimed_at_ms: int | None
    operation_id: str | None
    operation_state: OperationState
    dispatch_started_at_ms: int | None
    dispatched_at_ms: int | None
    completed_at_ms: int | None
    payload: dict[str, object]


@dataclass(frozen=True)
class CompareAndSetResult:
    applied: bool
    job: OwnerJob | None


class OwnerJobStore(Protocol):
    def put_job(self, job: OwnerJob) -> None: ...

    def delete_uninitialized_job(self, *, owner_user_id: str, job_id: str) -> bool: ...

    def get_job(self, *, owner_user_id: str, job_id: str) -> OwnerJob | None: ...

    def publish_consent(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        expected_version: int,
        operation_id: str,
        approved_ceiling_cents: int,
        consent_receipt_id: str,
        consent_config_hash: str,
        consent_issued_at_ms: int,
        consent_expires_at_ms: int,
    ) -> CompareAndSetResult: ...

    def compare_and_set(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        expected_version: int,
        expected_state: OperationState,
        operation_id: str,
        next_state: OperationState,
        consent_claimed_at_ms: int | None = None,
        dispatch_started_at_ms: int | None = None,
        dispatched_at_ms: int | None = None,
        completed_at_ms: int | None = None,
    ) -> CompareAndSetResult: ...


_DDL: Final = """
CREATE TABLE IF NOT EXISTS midnight_oil_jobs (
    owner_user_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    state_version BIGINT NOT NULL,
    approved_ceiling_cents BIGINT,
    consent_receipt_id TEXT,
    consent_config_hash TEXT,
    consent_issued_at_ms BIGINT,
    consent_expires_at_ms BIGINT,
    consent_claimed_at_ms BIGINT,
    operation_id TEXT,
    operation_state TEXT NOT NULL,
    dispatch_started_at_ms BIGINT,
    dispatched_at_ms BIGINT,
    completed_at_ms BIGINT,
    payload_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    PRIMARY KEY (owner_user_id, job_id),
    UNIQUE (job_id)
)
"""

_COLUMNS: Final = (
    "owner_user_id",
    "job_id",
    "state_version",
    "approved_ceiling_cents",
    "consent_receipt_id",
    "consent_config_hash",
    "consent_issued_at_ms",
    "consent_expires_at_ms",
    "consent_claimed_at_ms",
    "operation_id",
    "operation_state",
    "dispatch_started_at_ms",
    "dispatched_at_ms",
    "completed_at_ms",
    "payload_json",
    "schema_version",
)

_TRANSITIONS: Final[dict[OperationState, frozenset[OperationState]]] = {
    OperationState.NONE: frozenset({OperationState.CONSENT_ISSUED}),
    OperationState.CONSENT_ISSUED: frozenset({OperationState.QUEUED}),
    OperationState.QUEUED: frozenset({OperationState.RUNNING}),
    OperationState.RUNNING: frozenset(
        {
            OperationState.COMPLETE,
            OperationState.FAILED,
            OperationState.BUDGET_HALTED,
            OperationState.TIMED_OUT,
            OperationState.FAILED_RECONCILE,
        }
    ),
    OperationState.COMPLETE: frozenset(),
    OperationState.FAILED: frozenset(),
    OperationState.BUDGET_HALTED: frozenset(),
    OperationState.TIMED_OUT: frozenset(),
    OperationState.FAILED_RECONCILE: frozenset(),
}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"{field} must be a non-empty bounded string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _optional_nonnegative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    checked = _optional_nonnegative_int(value, field)
    if checked is None or checked == 0:
        raise ValueError(f"{field} must be a positive integer")
    return checked


def _ceiling(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= MAX_APPROVED_CEILING_CENTS:
        raise ValueError("approved_ceiling_cents is outside authority bounds")
    return value


def _state(value: object) -> OperationState:
    if not isinstance(value, str):
        raise ValueError("operation_state is not a closed state")
    try:
        return OperationState(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("operation_state is not a closed state") from exc


def _transition(before: OperationState, after: OperationState) -> None:
    if after not in _TRANSITIONS[before]:
        raise ValueError(f"operation transition {before.value}->{after.value} is not allowed")


def _transition_timestamps(
    before: OperationState,
    after: OperationState,
    *,
    consent_claimed_at_ms: int | None,
    dispatch_started_at_ms: int | None,
    dispatched_at_ms: int | None,
    completed_at_ms: int | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    values = (
        _optional_nonnegative_int(consent_claimed_at_ms, "consent_claimed_at_ms"),
        _optional_nonnegative_int(dispatch_started_at_ms, "dispatch_started_at_ms"),
        _optional_nonnegative_int(dispatched_at_ms, "dispatched_at_ms"),
        _optional_nonnegative_int(completed_at_ms, "completed_at_ms"),
    )
    if before is OperationState.CONSENT_ISSUED and after is OperationState.QUEUED:
        valid = values[0] is not None and values[1:] == (None, None, None)
    elif before is OperationState.QUEUED and after is OperationState.RUNNING:
        valid = values[0] is None and values[1] is not None and values[2:] == (None, None)
    elif before is OperationState.RUNNING:
        valid = values[0] is None and values[1] is None and values[3] is not None
    else:
        valid = False
    if not valid:
        raise ValueError("transition requires exactly its immutable audit timestamps")
    return values


def _reject_sensitive_payload_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            parts = frozenset(normalized.split("_"))
            if parts.intersection({"token", "secret", "password", "credential"}) or normalized in {
                "key",
                "api_key",
                "apikey",
                "access_key",
                "private_key",
                "signing_key",
            }:
                raise ValueError("payload must not contain token, key, or secret fields")
            _reject_sensitive_payload_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive_payload_keys(nested)


_PAYLOAD_FIELDS: Final = frozenset(
    {
        "goals",
        "duration_minutes",
        "model_id",
        "research_tier",
        "fanout_depth",
        "asset_id",
        "force_below_recommended",
        "recommended_ceiling_cents",
        "display_usd",
    }
)


def _validate_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dictionary")
    unknown = set(payload).difference(_PAYLOAD_FIELDS)
    if unknown:
        raise ValueError("payload contains fields outside the closed job configuration")
    _reject_sensitive_payload_keys(payload)
    if any(isinstance(value, dict) for value in payload.values()):
        raise ValueError("payload values must not contain nested objects")
    return deepcopy(payload)


def _validate_state_coherence(job: OwnerJob) -> None:
    consent = (
        job.approved_ceiling_cents,
        job.consent_receipt_id,
        job.consent_config_hash,
        job.consent_issued_at_ms,
        job.consent_expires_at_ms,
    )
    if job.operation_state is OperationState.NONE:
        if any(
            value is not None for value in (*consent, job.operation_id, job.consent_claimed_at_ms)
        ):
            raise ValueError("none state must not carry consent or operation authority")
    elif any(value is None for value in (*consent, job.operation_id)):
        raise ValueError("active operation state requires complete consent authority")
    elif job.consent_expires_at_ms == 0:
        raise ValueError("active consent expiry must be positive")
    elif (
        job.consent_issued_at_ms is not None
        and job.consent_expires_at_ms is not None
        and job.consent_expires_at_ms <= job.consent_issued_at_ms
    ):
        raise ValueError("consent expiry must follow issuance")

    queued_or_later = job.operation_state not in {
        OperationState.NONE,
        OperationState.CONSENT_ISSUED,
    }
    if queued_or_later != (job.consent_claimed_at_ms is not None):
        raise ValueError("claimed timestamp must exist exactly for queued-or-later states")
    running_or_later = job.operation_state not in {
        OperationState.NONE,
        OperationState.CONSENT_ISSUED,
        OperationState.QUEUED,
    }
    if running_or_later != (job.dispatch_started_at_ms is not None):
        raise ValueError("dispatch start must exist exactly for running-or-later states")
    if job.operation_state is OperationState.RUNNING and job.completed_at_ms is not None:
        raise ValueError("running state cannot be completed")
    terminal = not _TRANSITIONS[job.operation_state]
    if terminal != (job.completed_at_ms is not None):
        raise ValueError("completion timestamp must exist exactly for terminal states")
    ordered = [
        value
        for value in (
            job.consent_claimed_at_ms,
            job.dispatch_started_at_ms,
            job.dispatched_at_ms,
            job.completed_at_ms,
        )
        if value is not None
    ]
    if ordered != sorted(ordered):
        raise ValueError("authority timestamps must be monotonic")
    if (
        job.consent_claimed_at_ms is not None
        and job.consent_issued_at_ms is not None
        and job.consent_expires_at_ms is not None
        and not (job.consent_issued_at_ms <= job.consent_claimed_at_ms < job.consent_expires_at_ms)
    ):
        raise ValueError("consent claim must fall within its validity interval")


def _validate(job: OwnerJob) -> OwnerJob:
    owner = _text(job.owner_user_id, "owner_user_id")
    job_id = _text(job.job_id, "job_id")
    if type(job.state_version) is not int or job.state_version < 0:
        raise ValueError("state_version must be a non-negative integer")
    state = _state(job.operation_state)
    operation_id = _optional_text(job.operation_id, "operation_id")
    if state is not OperationState.NONE and operation_id is None:
        raise ValueError("non-none operation state requires operation_id")
    checked = OwnerJob(
        owner_user_id=owner,
        job_id=job_id,
        state_version=job.state_version,
        approved_ceiling_cents=_ceiling(job.approved_ceiling_cents),
        consent_receipt_id=_optional_text(job.consent_receipt_id, "consent_receipt_id"),
        consent_config_hash=_optional_text(job.consent_config_hash, "consent_config_hash"),
        consent_issued_at_ms=_optional_nonnegative_int(
            job.consent_issued_at_ms, "consent_issued_at_ms"
        ),
        consent_expires_at_ms=_optional_nonnegative_int(
            job.consent_expires_at_ms, "consent_expires_at_ms"
        ),
        consent_claimed_at_ms=_optional_nonnegative_int(
            job.consent_claimed_at_ms, "consent_claimed_at_ms"
        ),
        operation_id=operation_id,
        operation_state=state,
        dispatch_started_at_ms=_optional_nonnegative_int(
            job.dispatch_started_at_ms, "dispatch_started_at_ms"
        ),
        dispatched_at_ms=_optional_nonnegative_int(job.dispatched_at_ms, "dispatched_at_ms"),
        completed_at_ms=_optional_nonnegative_int(job.completed_at_ms, "completed_at_ms"),
        payload=_validate_payload(job.payload),
    )
    _validate_state_coherence(checked)
    return checked


def _legacy_usd_to_cents(value: object) -> int | None:
    """Convert a legacy display float once without increasing authority."""
    if value is None:
        return None
    try:
        cents = int((Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_FLOOR))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidStoredJob("legacy approved ceiling is malformed") from exc
    try:
        return _ceiling(cents)
    except ValueError as exc:
        raise InvalidStoredJob("legacy approved ceiling is outside authority bounds") from exc


def _row(job: OwnerJob) -> tuple[object, ...]:
    checked = _validate(job)
    try:
        payload = json.dumps(
            checked.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be JSON serializable") from exc
    return (
        checked.owner_user_id,
        checked.job_id,
        checked.state_version,
        checked.approved_ceiling_cents,
        checked.consent_receipt_id,
        checked.consent_config_hash,
        checked.consent_issued_at_ms,
        checked.consent_expires_at_ms,
        checked.consent_claimed_at_ms,
        checked.operation_id,
        checked.operation_state.value,
        checked.dispatch_started_at_ms,
        checked.dispatched_at_ms,
        checked.completed_at_ms,
        payload,
        SCHEMA_VERSION,
    )


def _decode(row: tuple[Any, ...]) -> OwnerJob:
    try:
        schema_version = int(row[15])
        if schema_version != SCHEMA_VERSION:
            raise InvalidStoredJob("unsupported job schema version")
        payload = json.loads(str(row[14]))
        if not isinstance(payload, dict):
            raise InvalidStoredJob("stored payload is not an object")
        return _validate(
            OwnerJob(
                owner_user_id=str(row[0]),
                job_id=str(row[1]),
                state_version=int(row[2]),
                approved_ceiling_cents=None if row[3] is None else int(row[3]),
                consent_receipt_id=None if row[4] is None else str(row[4]),
                consent_config_hash=None if row[5] is None else str(row[5]),
                consent_issued_at_ms=None if row[6] is None else int(row[6]),
                consent_expires_at_ms=None if row[7] is None else int(row[7]),
                consent_claimed_at_ms=None if row[8] is None else int(row[8]),
                operation_id=None if row[9] is None else str(row[9]),
                operation_state=_state(row[10]),
                dispatch_started_at_ms=None if row[11] is None else int(row[11]),
                dispatched_at_ms=None if row[12] is None else int(row[12]),
                completed_at_ms=None if row[13] is None else int(row[13]),
                payload=payload,
            )
        )
    except InvalidStoredJob:
        raise
    except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidStoredJob("stored job row is malformed") from exc


class DurableOwnerJobStore:
    """DuckDB-backed store with process-safe serialized writes."""

    def __init__(self, path: str | Path) -> None:
        raw_path = os.fspath(path)
        if not raw_path.strip() or raw_path == ":memory:":
            raise StoreConstructionError("a durable Midnight Oil job path is required")
        self.path = Path(raw_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._coordinator = FlockWriteCoordinator(str(self.path))
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._coordinator.acquire_write_context("midnight_oil.job_store") as connection:
            connection.execute(_DDL)
            info = connection.execute("PRAGMA table_info('midnight_oil_jobs')").fetchall()
            names = {str(column[1]) for column in info}
            if set(_COLUMNS).issubset(names):
                constraints = {
                    (str(row[0]), tuple(str(name) for name in row[1]))
                    for row in connection.execute(
                        "SELECT constraint_type, constraint_column_names FROM duckdb_constraints() "
                        "WHERE table_name = 'midnight_oil_jobs'"
                    ).fetchall()
                }
                required_constraints = {
                    ("PRIMARY KEY", ("owner_user_id", "job_id")),
                    ("UNIQUE", ("job_id",)),
                }
                if not required_constraints.issubset(constraints):
                    raise InvalidStoredJob("authoritative job constraints are missing")
                rows = connection.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM midnight_oil_jobs"
                ).fetchall()
                for row in rows:
                    _decode(tuple(row))
                duplicate = connection.execute(
                    "SELECT job_id FROM midnight_oil_jobs GROUP BY job_id HAVING COUNT(*) > 1 LIMIT 1"
                ).fetchone()
                if duplicate is not None:
                    raise InvalidStoredJob("job ids are not globally unique")
                return
            connection.execute("BEGIN TRANSACTION")
            try:
                self._migrate_legacy(connection, names)
            except Exception:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")

    def _migrate_legacy(self, connection: Any, names: set[str]) -> None:
        # A partially migrated authority table is never guessed at.  The sole
        # supported legacy shape is the former blind job table with job_id,
        # owner_user_id and payload/display fields.
        required = {"job_id", "owner_user_id"}
        if not required.issubset(names):
            raise InvalidStoredJob("legacy jobs lack durable owner identity")
        execute = connection.execute
        execute("ALTER TABLE midnight_oil_jobs RENAME TO midnight_oil_jobs_legacy_v0")
        execute(_DDL)
        legacy_columns = [
            str(row[1])
            for row in execute("PRAGMA table_info('midnight_oil_jobs_legacy_v0')").fetchall()
        ]
        rows = execute("SELECT * FROM midnight_oil_jobs_legacy_v0").fetchall()
        for legacy_row in rows:
            source = dict(zip(legacy_columns, legacy_row, strict=True))
            payload_value = source.get("payload_json", "{}")
            try:
                payload = json.loads(str(payload_value))
            except json.JSONDecodeError as exc:
                raise InvalidStoredJob("legacy payload is malformed") from exc
            if not isinstance(payload, dict):
                raise InvalidStoredJob("legacy payload is not an object")
            approved = source.get("approved_ceiling_cents")
            if approved is None:
                # Validate the legacy display value without elevating an unsigned
                # float into spend authority. Consent issuance publishes cents.
                _legacy_usd_to_cents(source.get("approved_ceiling_usd"))
            state_value = source.get("operation_state", OperationState.NONE.value)
            if state_value == "ready":
                legacy_authority = (
                    source.get("approved_ceiling_cents"),
                    source.get("consent_receipt_id"),
                    source.get("consent_config_hash"),
                    source.get("consent_claimed_at_ms"),
                    source.get("operation_id"),
                    source.get("dispatch_started_at_ms"),
                    source.get("dispatched_at_ms"),
                    source.get("completed_at_ms"),
                )
                if any(value is not None for value in legacy_authority):
                    raise InvalidStoredJob("legacy ready row carries ambiguous authority")
                state_value = OperationState.NONE.value
            elif state_value not in {OperationState.NONE.value}:
                raise InvalidStoredJob("active legacy operation requires reconciliation")
            migrated = OwnerJob(
                owner_user_id=str(source["owner_user_id"]),
                job_id=str(source["job_id"]),
                state_version=int(source.get("state_version", 0)),
                approved_ceiling_cents=None,
                consent_receipt_id=None,
                consent_config_hash=None,
                consent_issued_at_ms=None,
                consent_expires_at_ms=None,
                consent_claimed_at_ms=None,
                operation_id=None,
                operation_state=_state(state_value),
                dispatch_started_at_ms=None,
                dispatched_at_ms=None,
                completed_at_ms=None,
                payload=payload,
            )
            execute(
                f"INSERT INTO midnight_oil_jobs ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                list(_row(migrated)),
            )
        execute("DROP TABLE midnight_oil_jobs_legacy_v0")

    def put_job(self, job: OwnerJob) -> None:
        values = _row(job)
        with self._coordinator.acquire_write_context("midnight_oil.job_store") as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                existing = connection.execute(
                    "SELECT 1 FROM midnight_oil_jobs WHERE owner_user_id = ? AND job_id = ?",
                    [values[0], values[1]],
                ).fetchone()
                if existing is not None:
                    raise ValueError("job already exists; use compare_and_set")
                connection.execute(
                    f"INSERT INTO midnight_oil_jobs ({', '.join(_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                    list(values),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def get_job(self, *, owner_user_id: str, job_id: str) -> OwnerJob | None:
        owner = _text(owner_user_id, "owner_user_id")
        jid = _text(job_id, "job_id")
        connection = connect_read(str(self.path))
        try:
            row = connection.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM midnight_oil_jobs "
                "WHERE owner_user_id = ? AND job_id = ?",
                [owner, jid],
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _decode(tuple(row))

    def delete_uninitialized_job(self, *, owner_user_id: str, job_id: str) -> bool:
        """Compensate a failed detail-store create, but never erase authority."""
        owner = _text(owner_user_id, "owner_user_id")
        jid = _text(job_id, "job_id")
        with self._coordinator.acquire_write_context("midnight_oil.job_store") as connection:
            changed = connection.execute(
                "DELETE FROM midnight_oil_jobs WHERE owner_user_id = ? AND job_id = ? "
                "AND state_version = 0 AND operation_state = ? AND operation_id IS NULL "
                "AND consent_receipt_id IS NULL RETURNING job_id",
                [owner, jid, OperationState.NONE.value],
            ).fetchone()
            return changed is not None

    def publish_consent(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        expected_version: int,
        operation_id: str,
        approved_ceiling_cents: int,
        consent_receipt_id: str,
        consent_config_hash: str,
        consent_issued_at_ms: int,
        consent_expires_at_ms: int,
    ) -> CompareAndSetResult:
        owner = _text(owner_user_id, "owner_user_id")
        jid = _text(job_id, "job_id")
        operation = _text(operation_id, "operation_id")
        ceiling = _ceiling(approved_ceiling_cents)
        receipt = _text(consent_receipt_id, "consent_receipt_id")
        config_hash = _text(consent_config_hash, "consent_config_hash")
        issued = _optional_nonnegative_int(consent_issued_at_ms, "consent_issued_at_ms")
        expiry = _positive_int(consent_expires_at_ms, "consent_expires_at_ms")
        if ceiling is None or issued is None or expiry <= issued:
            raise ValueError("complete consent authority is required")
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        with self._coordinator.acquire_write_context("midnight_oil.job_store") as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                current = connection.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM midnight_oil_jobs "
                    "WHERE owner_user_id = ? AND job_id = ?",
                    [owner, jid],
                ).fetchone()
                if current is None:
                    connection.execute("COMMIT")
                    return CompareAndSetResult(applied=False, job=None)
                decoded = _decode(tuple(current))
                if (
                    decoded.state_version != expected_version
                    or decoded.operation_state is not OperationState.NONE
                ):
                    connection.execute("COMMIT")
                    return CompareAndSetResult(applied=False, job=decoded)
                changed = connection.execute(
                    "UPDATE midnight_oil_jobs SET state_version = ?, approved_ceiling_cents = ?, "
                    "consent_receipt_id = ?, consent_config_hash = ?, consent_issued_at_ms = ?, "
                    "consent_expires_at_ms = ?, "
                    "operation_id = ?, operation_state = ? "
                    "WHERE owner_user_id = ? AND job_id = ? AND state_version = ? "
                    "AND operation_state = ? RETURNING state_version",
                    [
                        expected_version + 1,
                        ceiling,
                        receipt,
                        config_hash,
                        issued,
                        expiry,
                        operation,
                        OperationState.CONSENT_ISSUED.value,
                        owner,
                        jid,
                        expected_version,
                        OperationState.NONE.value,
                    ],
                ).fetchone()
                if changed is None:
                    connection.execute("ROLLBACK")
                    return CompareAndSetResult(applied=False, job=decoded)
                updated = connection.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM midnight_oil_jobs "
                    "WHERE owner_user_id = ? AND job_id = ?",
                    [owner, jid],
                ).fetchone()
                if updated is None:
                    raise InvalidStoredJob("job disappeared during consent publication")
                result = _decode(tuple(updated))
                connection.execute("COMMIT")
                return CompareAndSetResult(applied=True, job=result)
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def compare_and_set(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        expected_version: int,
        expected_state: OperationState,
        operation_id: str,
        next_state: OperationState,
        consent_claimed_at_ms: int | None = None,
        dispatch_started_at_ms: int | None = None,
        dispatched_at_ms: int | None = None,
        completed_at_ms: int | None = None,
    ) -> CompareAndSetResult:
        owner = _text(owner_user_id, "owner_user_id")
        jid = _text(job_id, "job_id")
        operation = _text(operation_id, "operation_id")
        before = _state(expected_state)
        after = _state(next_state)
        _transition(before, after)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        timestamps = _transition_timestamps(
            before,
            after,
            consent_claimed_at_ms=consent_claimed_at_ms,
            dispatch_started_at_ms=dispatch_started_at_ms,
            dispatched_at_ms=dispatched_at_ms,
            completed_at_ms=completed_at_ms,
        )
        with self._coordinator.acquire_write_context("midnight_oil.job_store") as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                current = connection.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM midnight_oil_jobs "
                    "WHERE owner_user_id = ? AND job_id = ?",
                    [owner, jid],
                ).fetchone()
                if current is None:
                    connection.execute("COMMIT")
                    return CompareAndSetResult(applied=False, job=None)
                decoded = _decode(tuple(current))
                operation_matches = decoded.operation_id in (None, operation)
                if (
                    decoded.state_version != expected_version
                    or decoded.operation_state is not before
                    or not operation_matches
                ):
                    connection.execute("COMMIT")
                    return CompareAndSetResult(applied=False, job=decoded)
                changed = connection.execute(
                    "UPDATE midnight_oil_jobs SET state_version = ?, operation_id = ?, "
                    "operation_state = ?, consent_claimed_at_ms = COALESCE(?, consent_claimed_at_ms), "
                    "dispatch_started_at_ms = COALESCE(?, dispatch_started_at_ms), "
                    "dispatched_at_ms = COALESCE(?, dispatched_at_ms), "
                    "completed_at_ms = COALESCE(?, completed_at_ms) "
                    "WHERE owner_user_id = ? AND job_id = ? AND state_version = ? "
                    "AND operation_state = ? AND (operation_id IS NULL OR operation_id = ?) "
                    "RETURNING state_version",
                    [
                        expected_version + 1,
                        operation,
                        after.value,
                        *timestamps,
                        owner,
                        jid,
                        expected_version,
                        before.value,
                        operation,
                    ],
                ).fetchone()
                if changed is None:
                    connection.execute("ROLLBACK")
                    return CompareAndSetResult(applied=False, job=decoded)
                updated = connection.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM midnight_oil_jobs "
                    "WHERE owner_user_id = ? AND job_id = ?",
                    [owner, jid],
                ).fetchone()
                if updated is None:
                    raise InvalidStoredJob("job disappeared during transition")
                decoded_updated = _decode(tuple(updated))
                connection.execute("COMMIT")
                return CompareAndSetResult(applied=True, job=decoded_updated)
            except Exception:
                connection.execute("ROLLBACK")
                raise


class TestOnlyInMemoryOwnerJobStore:
    """Deterministic unit-test adapter; production construction rejects it."""

    _test_only: Final = True

    def __init__(self) -> None:
        import threading

        self._jobs: dict[tuple[str, str], OwnerJob] = {}
        self._lock = threading.Lock()

    def put_job(self, job: OwnerJob) -> None:
        checked = _validate(job)
        key = (checked.owner_user_id, checked.job_id)
        with self._lock:
            if key in self._jobs:
                raise ValueError("job already exists; use compare_and_set")
            if any(existing_job_id == checked.job_id for _, existing_job_id in self._jobs):
                raise ValueError("job_id must be globally unique")
            self._jobs[key] = checked

    def get_job(self, *, owner_user_id: str, job_id: str) -> OwnerJob | None:
        key = (_text(owner_user_id, "owner_user_id"), _text(job_id, "job_id"))
        with self._lock:
            job = self._jobs.get(key)
            return None if job is None else replace_payload(job)

    def delete_uninitialized_job(self, *, owner_user_id: str, job_id: str) -> bool:
        key = (_text(owner_user_id, "owner_user_id"), _text(job_id, "job_id"))
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return False
            if (
                job.state_version != 0
                or job.operation_state is not OperationState.NONE
                or job.operation_id is not None
                or job.consent_receipt_id is not None
            ):
                return False
            del self._jobs[key]
            return True

    def publish_consent(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        expected_version: int,
        operation_id: str,
        approved_ceiling_cents: int,
        consent_receipt_id: str,
        consent_config_hash: str,
        consent_issued_at_ms: int,
        consent_expires_at_ms: int,
    ) -> CompareAndSetResult:
        key = (_text(owner_user_id, "owner_user_id"), _text(job_id, "job_id"))
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        with self._lock:
            current = self._jobs.get(key)
            if current is None:
                return CompareAndSetResult(applied=False, job=None)
            if (
                current.state_version != expected_version
                or current.operation_state is not OperationState.NONE
            ):
                return CompareAndSetResult(applied=False, job=replace_payload(current))
            updated = OwnerJob(
                **{
                    **current.__dict__,
                    "state_version": expected_version + 1,
                    "approved_ceiling_cents": approved_ceiling_cents,
                    "consent_receipt_id": consent_receipt_id,
                    "consent_config_hash": consent_config_hash,
                    "consent_issued_at_ms": consent_issued_at_ms,
                    "consent_expires_at_ms": consent_expires_at_ms,
                    "operation_id": operation_id,
                    "operation_state": OperationState.CONSENT_ISSUED,
                }
            )
            self._jobs[key] = _validate(updated)
            return CompareAndSetResult(applied=True, job=replace_payload(self._jobs[key]))

    def compare_and_set(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        expected_version: int,
        expected_state: OperationState,
        operation_id: str,
        next_state: OperationState,
        consent_claimed_at_ms: int | None = None,
        dispatch_started_at_ms: int | None = None,
        dispatched_at_ms: int | None = None,
        completed_at_ms: int | None = None,
    ) -> CompareAndSetResult:
        key = (_text(owner_user_id, "owner_user_id"), _text(job_id, "job_id"))
        operation = _text(operation_id, "operation_id")
        before = _state(expected_state)
        after = _state(next_state)
        _transition(before, after)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        timestamps = _transition_timestamps(
            before,
            after,
            consent_claimed_at_ms=consent_claimed_at_ms,
            dispatch_started_at_ms=dispatch_started_at_ms,
            dispatched_at_ms=dispatched_at_ms,
            completed_at_ms=completed_at_ms,
        )
        with self._lock:
            current = self._jobs.get(key)
            if current is None:
                return CompareAndSetResult(applied=False, job=None)
            if (
                current.state_version != expected_version
                or current.operation_state is not before
                or current.operation_id not in (None, operation)
            ):
                return CompareAndSetResult(applied=False, job=replace_payload(current))
            updated = OwnerJob(
                **{
                    **current.__dict__,
                    "state_version": expected_version + 1,
                    "operation_id": operation,
                    "operation_state": after,
                    "consent_claimed_at_ms": timestamps[0]
                    if timestamps[0] is not None
                    else current.consent_claimed_at_ms,
                    "dispatch_started_at_ms": timestamps[1]
                    if timestamps[1] is not None
                    else current.dispatch_started_at_ms,
                    "dispatched_at_ms": timestamps[2]
                    if timestamps[2] is not None
                    else current.dispatched_at_ms,
                    "completed_at_ms": timestamps[3]
                    if timestamps[3] is not None
                    else current.completed_at_ms,
                }
            )
            self._jobs[key] = _validate(updated)
            return CompareAndSetResult(applied=True, job=replace_payload(self._jobs[key]))


def replace_payload(job: OwnerJob) -> OwnerJob:
    """Return a snapshot whose payload cannot mutate in-memory authority."""
    return OwnerJob(**{**job.__dict__, "payload": deepcopy(job.payload)})


def construct_job_store(
    *, durable_path: str | Path | None, production: bool = True
) -> OwnerJobStore:
    """Construct authority explicitly; production never falls back to memory."""
    if durable_path is None:
        if production:
            raise StoreConstructionError("production Midnight Oil requires a durable job path")
        return TestOnlyInMemoryOwnerJobStore()
    return DurableOwnerJobStore(durable_path)


__all__ = [
    "CompareAndSetResult",
    "DurableOwnerJobStore",
    "InvalidStoredJob",
    "MAX_APPROVED_CEILING_CENTS",
    "OperationState",
    "OwnerJob",
    "OwnerJobStore",
    "SCHEMA_VERSION",
    "StoreConstructionError",
    "TestOnlyInMemoryOwnerJobStore",
    "construct_job_store",
]

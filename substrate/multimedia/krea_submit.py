"""Authorized one-shot Krea submission orchestration."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from integrations.krea.catalog import (
    Imagen3Request,
    KreaQuote,
    PreparedKreaRequest,
    RunwayGen45Request,
    prepare_request,
    verify_quote,
)
from integrations.krea.client import KreaClient, KreaClientError
from runtime.db_lock import FlockWriteCoordinator, WriteContext, connect_read
from substrate.midnight_oil.budget_ledger import CallHold

from .execution_authorization import (
    ExecutionAuthorizationIntegrityError,
    MultimediaExecutionAuthorizationV2,
    verify_async_execution_authorization,
)
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionRecord,
    ProviderExecutionStatus,
    begin_reserved_provider_submission,
    bind_provider_job_with_mutation,
    charge_and_mark_submission_unknown,
    get_provider_execution,
)

_ATTEMPT_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_krea_submission_attempts (
    execution_id TEXT PRIMARY KEY,
    hold_id TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    request_body_digest TEXT NOT NULL,
    send_started_at TEXT,
    finished_at TEXT,
    outcome TEXT NOT NULL,
    provider_status TEXT,
    failure_kind TEXT,
    http_status INTEGER,
    attempt_mac TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class KreaSubmissionAttempt:
    execution_id: str
    hold_id: str
    endpoint: str
    request_body_digest: str
    send_started_at: str | None
    finished_at: str | None
    outcome: str
    provider_status: str | None
    failure_kind: str | None
    http_status: int | None


def submit_krea_job(
    *,
    db_path: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    now: datetime,
    request: Imagen3Request | RunwayGen45Request,
    quote: KreaQuote,
    client: KreaClient,
) -> ProviderExecutionRecord:
    """Verify, reserve, and send one Krea POST with no automatic retry."""
    prepared = prepare_request(request)
    _verify_prepared(
        authorization,
        prepared,
        quote=quote,
        signing_key=signing_key,
        now=now,
    )
    existing = _existing_execution(
        db_path=db_path,
        authorization=authorization,
        signing_key=signing_key,
    )
    if existing is not None and existing.status is not ProviderExecutionStatus.SUBMITTING:
        return existing
    execution, hold = begin_reserved_provider_submission(
        db_path=db_path,
        authorization=authorization,
        signing_key=signing_key,
        now=now,
        mutation=lambda connection, record, reserved_hold: _ensure_attempt_in_context(
            connection,
            execution_id=record.execution_id,
            hold=reserved_hold,
            prepared=prepared,
            signing_key=signing_key,
        ),
    )
    if not _mark_send_started(
        db_path=db_path,
        execution_id=execution.execution_id,
        signing_key=signing_key,
        now=now,
    ):
        return get_provider_execution(
            db_path=db_path, execution_id=execution.execution_id, signing_key=signing_key
        )
    try:
        response = client.submit(endpoint=prepared.endpoint, body=prepared.body)
    except KreaClientError as exc:
        unknown = charge_and_mark_submission_unknown(
            db_path=db_path,
            execution_id=execution.execution_id,
            hold=hold,
            signing_key=signing_key,
            now=now,
        )
        _finish_attempt(
            db_path=db_path,
            execution_id=execution.execution_id,
            outcome="outcome_unknown",
            provider_status=None,
            failure_kind=exc.kind,
            http_status=exc.status_code,
            signing_key=signing_key,
            now=now,
        )
        return unknown
    return bind_provider_job_with_mutation(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id=response.job_id,
        signing_key=signing_key,
        now=now,
        mutation=lambda connection: _finish_attempt_in_context(
            connection,
            execution_id=execution.execution_id,
            outcome="job_bound",
            provider_status=response.status,
            failure_kind=None,
            http_status=response.http_status,
            signing_key=signing_key,
            timestamp=_timestamp(now),
        ),
    )


def recover_stale_krea_submission(
    *,
    db_path: str,
    execution_id: str,
    signing_key: bytes,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ProviderExecutionRecord:
    """Charge and quarantine a stale send marker without issuing another POST."""
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    attempt = get_krea_submission_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    if attempt.send_started_at is None:
        raise ProviderExecutionIntegrityError("submission has no durable send marker")
    if attempt.outcome != "sending":
        return get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
    started = _parse_timestamp(attempt.send_started_at)
    if _aware(now) - started < stale_after:
        raise ProviderExecutionIntegrityError("submission send marker is not stale")
    execution = get_provider_execution(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    hold = CallHold(
        hold_id=attempt.hold_id,
        run_id=execution.authorization_id,
        role=f"multimedia:{execution.provider}",
        projected_max_cents=(execution.approved_ceiling_microdollars + 9_999) // 10_000,
    )
    unknown = charge_and_mark_submission_unknown(
        db_path=db_path,
        execution_id=execution_id,
        hold=hold,
        signing_key=signing_key,
        now=now,
    )
    _finish_attempt(
        db_path=db_path,
        execution_id=execution_id,
        outcome="outcome_unknown",
        provider_status=None,
        failure_kind="stale_send_marker",
        http_status=None,
        signing_key=signing_key,
        now=now,
    )
    return unknown


def get_krea_submission_attempt(
    *, db_path: str, execution_id: str, signing_key: bytes
) -> KreaSubmissionAttempt:
    with connect_read(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM multimedia_krea_submission_attempts WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
    if row is None:
        raise ProviderExecutionIntegrityError("Krea submission attempt does not exist")
    return _attempt(row, signing_key=signing_key)


def _verify_prepared(
    authorization: MultimediaExecutionAuthorizationV2,
    prepared: PreparedKreaRequest,
    *,
    quote: KreaQuote,
    signing_key: bytes,
    now: datetime,
) -> None:
    try:
        verify_quote(
            quote,
            signing_key=signing_key,
            prepared=prepared,
            expected_quote_id=authorization.quote_id,
            expected_expires_at=authorization.quote_expires_at,
            expected_ceiling_microdollars=authorization.approved_ceiling_microdollars,
            now=now,
        )
    except ValueError as exc:
        raise ExecutionAuthorizationIntegrityError("Krea quote integrity mismatch") from exc
    verify_async_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=authorization.operator_id,
        asset_id=authorization.asset_id,
        revision_id=authorization.revision_id,
        provider="krea",
        route_policy=authorization.route_policy,
        model=prepared.model,
        endpoint_capability=prepared.endpoint_capability,
        catalog_version=prepared.catalog_version,
        catalog_digest=prepared.catalog_digest,
        quote_id=authorization.quote_id,
        recovery_authority_id=authorization.recovery_authority_id,
        recovery_verification_key_digest=authorization.recovery_verification_key_digest,
        approved_ceiling_microdollars=authorization.approved_ceiling_microdollars,
        request_body_digest=prepared.body_digest,
        now=now,
    )


def _existing_execution(
    *,
    db_path: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
) -> ProviderExecutionRecord | None:
    execution_id = "mmexec_" + hashlib.sha256(
        f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
    ).hexdigest()
    if not Path(db_path).exists():
        return None
    try:
        result = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
    except ProviderExecutionIntegrityError as exc:
        if str(exc) == "provider execution does not exist":
            return None
        raise
    fields = (
        (result.authorization_id, authorization.authorization_id),
        (result.model, authorization.model),
        (result.catalog_digest, authorization.catalog_digest),
        (result.request_body_digest, authorization.request_body_digest),
    )
    if any(actual != expected for actual, expected in fields):
        raise ProviderExecutionIntegrityError("persisted execution conflicts with authorization")
    return result


def _ensure_attempt_in_context(
    connection: WriteContext,
    *,
    execution_id: str,
    hold: CallHold,
    prepared: PreparedKreaRequest,
    signing_key: bytes,
) -> None:
    connection.execute(_ATTEMPT_DDL)
    row = connection.execute(
        "SELECT * FROM multimedia_krea_submission_attempts WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is not None:
        result = _attempt(row, signing_key=signing_key)
        if (
            result.hold_id != hold.hold_id
            or result.endpoint != prepared.endpoint
            or result.request_body_digest != prepared.body_digest
        ):
            raise ProviderExecutionIntegrityError("Krea submission intent conflicts")
        return
    values: list[object] = [
        execution_id,
        hold.hold_id,
        prepared.endpoint,
        prepared.body_digest,
        None,
        None,
        "intent",
        None,
        None,
        None,
    ]
    connection.execute(
        "INSERT INTO multimedia_krea_submission_attempts "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [*values, _attempt_mac(signing_key, values)],
    )


def _mark_send_started(
    *, db_path: str, execution_id: str, signing_key: bytes, now: datetime
) -> bool:
    timestamp = _timestamp(now)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.krea_submit.send_started") as connection:
        row = connection.execute(
            "SELECT * FROM multimedia_krea_submission_attempts WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
        if row is None:
            raise ProviderExecutionIntegrityError("Krea submission intent disappeared")
        current = _attempt(row, signing_key=signing_key)
        if current.send_started_at is not None:
            return False
        values: list[object] = [*row[:4], timestamp, None, "sending", None, None, None]
        updated = connection.execute(
            "UPDATE multimedia_krea_submission_attempts SET send_started_at = ?, outcome = ?, "
            "provider_status = NULL, failure_kind = NULL, http_status = NULL, attempt_mac = ? "
            "WHERE execution_id = ? AND send_started_at IS NULL RETURNING 1",
            [timestamp, "sending", _attempt_mac(signing_key, values), execution_id],
        ).fetchone()
        return updated is not None


def _finish_attempt(
    *,
    db_path: str,
    execution_id: str,
    outcome: str,
    provider_status: str | None,
    failure_kind: str | None,
    http_status: int | None,
    signing_key: bytes,
    now: datetime,
) -> None:
    if outcome not in {"job_bound", "outcome_unknown"}:
        raise ValueError("invalid terminal Krea submission outcome")
    timestamp = _timestamp(now)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.krea_submit.finish") as connection:
        _finish_attempt_in_context(
            connection,
            execution_id=execution_id,
            outcome=outcome,
            provider_status=provider_status,
            failure_kind=failure_kind,
            http_status=http_status,
            signing_key=signing_key,
            timestamp=timestamp,
        )


def _finish_attempt_in_context(
    connection: WriteContext,
    *,
    execution_id: str,
    outcome: str,
    provider_status: str | None,
    failure_kind: str | None,
    http_status: int | None,
    signing_key: bytes,
    timestamp: str,
) -> None:
    if outcome not in {"job_bound", "outcome_unknown"}:
        raise ValueError("invalid terminal Krea submission outcome")
    row = connection.execute(
        "SELECT * FROM multimedia_krea_submission_attempts WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is None:
        raise ProviderExecutionIntegrityError("Krea submission intent disappeared")
    current = _attempt(row, signing_key=signing_key)
    if current.finished_at is not None:
        if (
            current.outcome != outcome
            or current.provider_status != provider_status
            or current.failure_kind != failure_kind
            or current.http_status != http_status
        ):
            raise ProviderExecutionIntegrityError("Krea submission outcome conflicts")
        return
    values: list[object] = [
        *row[:5],
        timestamp,
        outcome,
        provider_status,
        failure_kind,
        http_status,
    ]
    connection.execute(
        "UPDATE multimedia_krea_submission_attempts SET finished_at = ?, outcome = ?, "
        "provider_status = ?, failure_kind = ?, http_status = ?, attempt_mac = ? "
        "WHERE execution_id = ? AND finished_at IS NULL",
        [
            timestamp,
            outcome,
            provider_status,
            failure_kind,
            http_status,
            _attempt_mac(signing_key, values),
            execution_id,
        ],
    )


def _attempt(row: tuple[object, ...], *, signing_key: bytes) -> KreaSubmissionAttempt:
    if len(row) != 11 or not isinstance(row[10], str):
        raise ProviderExecutionIntegrityError("Krea submission attempt shape is invalid")
    if not hmac.compare_digest(row[10], _attempt_mac(signing_key, list(row[:10]))):
        raise ProviderExecutionIntegrityError("Krea submission attempt signature is invalid")
    if row[9] is not None and (isinstance(row[9], bool) or not isinstance(row[9], int)):
        raise ProviderExecutionIntegrityError("Krea submission HTTP status is invalid")
    result = KreaSubmissionAttempt(
        execution_id=str(row[0]),
        hold_id=str(row[1]),
        endpoint=str(row[2]),
        request_body_digest=str(row[3]),
        send_started_at=str(row[4]) if row[4] is not None else None,
        finished_at=str(row[5]) if row[5] is not None else None,
        outcome=str(row[6]),
        provider_status=str(row[7]) if row[7] is not None else None,
        failure_kind=str(row[8]) if row[8] is not None else None,
        http_status=row[9] if isinstance(row[9], int) and not isinstance(row[9], bool) else None,
    )
    if result.outcome not in {"intent", "sending", "job_bound", "outcome_unknown"}:
        raise ProviderExecutionIntegrityError("Krea submission outcome is invalid")
    if result.send_started_at is not None:
        _parse_timestamp(result.send_started_at)
    if result.finished_at is not None:
        _parse_timestamp(result.finished_at)
    if result.outcome == "intent" and any(
        value is not None
        for value in (
            result.send_started_at,
            result.finished_at,
            result.provider_status,
            result.failure_kind,
            result.http_status,
        )
    ):
        raise ProviderExecutionIntegrityError("Krea submission intent state is contradictory")
    if result.outcome == "sending" and (
        result.send_started_at is None
        or result.finished_at is not None
        or result.provider_status is not None
        or result.failure_kind is not None
        or result.http_status is not None
    ):
        raise ProviderExecutionIntegrityError("Krea sending state is contradictory")
    if result.outcome == "job_bound" and (
        result.send_started_at is None
        or result.finished_at is None
        or result.provider_status is None
        or result.failure_kind is not None
        or result.http_status != 200
    ):
        raise ProviderExecutionIntegrityError("Krea bound state is contradictory")
    if result.outcome == "outcome_unknown" and (
        result.send_started_at is None
        or result.finished_at is None
        or result.provider_status is not None
        or result.failure_kind is None
    ):
        raise ProviderExecutionIntegrityError("Krea unknown state is contradictory")
    return result


def _attempt_mac(signing_key: bytes, values: list[object]) -> str:
    payload = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hmac.new(signing_key, payload, hashlib.sha256).hexdigest()


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderExecutionIntegrityError("Krea submission timestamp is invalid") from exc
    if _timestamp(parsed) != value:
        raise ProviderExecutionIntegrityError("Krea submission timestamp is not canonical")
    return parsed


__all__ = [
    "KreaSubmissionAttempt",
    "get_krea_submission_attempt",
    "recover_stale_krea_submission",
    "submit_krea_job",
]

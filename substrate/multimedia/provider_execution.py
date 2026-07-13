"""Durable provider-neutral lifecycle for asynchronous multimedia execution.

This module deliberately has no transport, provider SDK, environment, or secret
surface. It records authority consumption and verified state observations so a
later edge adapter can submit exactly once and recover without implicit retry.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from runtime.db_lock import FlockWriteCoordinator, WriteContext, connect_read
from substrate.midnight_oil.budget_ledger import BudgetLedger, CallHold

from .execution_authorization import (
    ExecutionAuthorizationConsumed,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationRevoked,
    MultimediaExecutionAuthorizationV2,
    verify_async_execution_authorization,
    verify_async_revocation_record,
)


class ProviderExecutionIntegrityError(RuntimeError):
    """Persisted async execution state is missing, corrupt, or contradictory."""


class ProviderExecutionStatus(StrEnum):
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    CANCEL_ACKNOWLEDGED = "cancel_acknowledged"
    OUTCOME_UNKNOWN = "outcome_unknown"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {
        ProviderExecutionStatus.SUCCEEDED,
        ProviderExecutionStatus.FAILED,
        ProviderExecutionStatus.CANCELLED,
    }
)

_ALLOWED_TRANSITIONS = {
    ProviderExecutionStatus.SUBMITTING: frozenset(
        {ProviderExecutionStatus.SUBMITTED, ProviderExecutionStatus.OUTCOME_UNKNOWN}
    ),
    ProviderExecutionStatus.SUBMITTED: frozenset(
        {
            ProviderExecutionStatus.RUNNING,
            ProviderExecutionStatus.CANCEL_REQUESTED,
            ProviderExecutionStatus.SUCCEEDED,
            ProviderExecutionStatus.FAILED,
            ProviderExecutionStatus.CANCELLED,
            ProviderExecutionStatus.OUTCOME_UNKNOWN,
        }
    ),
    ProviderExecutionStatus.RUNNING: frozenset(
        {
            ProviderExecutionStatus.CANCEL_REQUESTED,
            ProviderExecutionStatus.SUCCEEDED,
            ProviderExecutionStatus.FAILED,
            ProviderExecutionStatus.CANCELLED,
            ProviderExecutionStatus.OUTCOME_UNKNOWN,
        }
    ),
    ProviderExecutionStatus.CANCEL_REQUESTED: frozenset(
        {
            ProviderExecutionStatus.CANCEL_ACKNOWLEDGED,
            ProviderExecutionStatus.RUNNING,
            ProviderExecutionStatus.SUCCEEDED,
            ProviderExecutionStatus.FAILED,
            ProviderExecutionStatus.CANCELLED,
            ProviderExecutionStatus.OUTCOME_UNKNOWN,
        }
    ),
    ProviderExecutionStatus.CANCEL_ACKNOWLEDGED: frozenset(
        {
            ProviderExecutionStatus.SUCCEEDED,
            ProviderExecutionStatus.FAILED,
            ProviderExecutionStatus.CANCELLED,
            ProviderExecutionStatus.OUTCOME_UNKNOWN,
        }
    ),
    ProviderExecutionStatus.OUTCOME_UNKNOWN: frozenset(
        {
            ProviderExecutionStatus.SUBMITTED,
            ProviderExecutionStatus.RUNNING,
            ProviderExecutionStatus.SUCCEEDED,
            ProviderExecutionStatus.FAILED,
            ProviderExecutionStatus.CANCELLED,
        }
    ),
    ProviderExecutionStatus.SUCCEEDED: frozenset(),
    ProviderExecutionStatus.FAILED: frozenset(),
    ProviderExecutionStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class ProviderExecutionRecord:
    execution_id: str
    authorization_id: str
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
    approved_ceiling_microdollars: int
    request_body_digest: str
    status: ProviderExecutionStatus
    provider_job_id: str | None
    created_at: str
    updated_at: str
    recovery_authority_id: str
    recovery_verification_key_digest: str


@dataclass(frozen=True)
class ProviderStatusObservation:
    observation_id: str
    execution_id: str
    provider_job_id: str
    status: ProviderExecutionStatus
    evidence_digest: str
    observed_at: str


@dataclass(frozen=True)
class ExternalRecoveryEvidence:
    execution_id: str
    provider_job_id: str
    source: str
    evidence_digest: str
    recorded_at: str
    external_signature: str


@dataclass(frozen=True)
class ProviderArtifactCandidate:
    execution_id: str
    ordinal: int
    source_locator_digest: str
    declared_media_type: str


_AUTHORIZATION_CLAIMS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_execution_authorization_claims (
    authorization_id TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    status TEXT NOT NULL,
    actual_cents BIGINT,
    claimed_at TIMESTAMP NOT NULL,
    settled_at TIMESTAMP
)
"""

_REVOCATIONS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_execution_authorization_revocations (
    authorization_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    revoked_at TEXT NOT NULL
)
"""

_ASYNC_REVOCATIONS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_async_execution_authorization_revocations (
    authorization_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    authorization_signature TEXT NOT NULL,
    revoked_at TEXT NOT NULL,
    revocation_mac TEXT NOT NULL
)
"""

_EXECUTIONS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_provider_executions (
    execution_id TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL UNIQUE,
    authorization_signature TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    route_policy TEXT NOT NULL,
    model TEXT NOT NULL,
    endpoint_capability TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    catalog_digest TEXT NOT NULL,
    quote_id TEXT NOT NULL,
    approved_ceiling_microdollars BIGINT NOT NULL,
    request_body_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    provider_job_id TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    recovery_authority_id TEXT NOT NULL,
    recovery_verification_key_digest TEXT NOT NULL
    ,record_mac TEXT NOT NULL
)
"""

_OBSERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_provider_execution_observations (
    observation_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    provider_job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_digest TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    observation_mac TEXT NOT NULL
)
"""

_RECONCILIATIONS_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_provider_reconciliations (
    observation_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL,
    provider TEXT NOT NULL, provider_job_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL, request_body_digest TEXT NOT NULL,
    account_identity_digest TEXT NOT NULL, source TEXT NOT NULL,
    raw_payload_digest TEXT NOT NULL, status TEXT NOT NULL,
    evidence_json TEXT NOT NULL, observed_at TEXT NOT NULL,
    observation_mac TEXT NOT NULL,
    UNIQUE(execution_id, source, raw_payload_digest)
)
"""

_ARTIFACT_CANDIDATES_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_provider_artifact_candidates (
    candidate_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL, source_locator_digest TEXT NOT NULL,
    declared_media_type TEXT NOT NULL,
    candidate_mac TEXT NOT NULL, UNIQUE(execution_id, ordinal)
)
"""

_RECOVERY_EVIDENCE_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_provider_external_recovery_evidence (
    execution_id TEXT PRIMARY KEY,
    provider_job_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    evidence_digest TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    external_signature TEXT NOT NULL,
    evidence_mac TEXT NOT NULL
)
"""


def begin_provider_submission(
    *,
    db_path: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    now: datetime,
) -> ProviderExecutionRecord:
    """Atomically consume v2 authority and persist a recoverable submit intent."""
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context("multimedia.provider_execution.begin") as ctx:
        _ensure_schema(ctx)
        ctx.execute("BEGIN TRANSACTION")
        try:
            record = _begin_in_context(
                ctx,
                authorization=authorization,
                signing_key=signing_key,
                now=now,
            )
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return record


def begin_reserved_provider_submission(
    *,
    db_path: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    now: datetime,
    mutation: Callable[[WriteContext, ProviderExecutionRecord, CallHold], None] | None = None,
) -> tuple[ProviderExecutionRecord, CallHold]:
    """Atomically persist submit intent and reserve its complete spend band."""
    ceiling_cents = (authorization.approved_ceiling_microdollars + 9_999) // 10_000
    role = f"multimedia:{authorization.provider}"
    hold_id = (
        "mmhold_"
        + hashlib.sha256(
            f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
        ).hexdigest()
    )
    ledger = BudgetLedger(_db_path(db_path))
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context("multimedia.provider_execution.begin_reserved") as ctx:
        _ensure_schema(ctx)
        ctx.execute("BEGIN TRANSACTION")
        try:
            record = _begin_in_context(
                ctx,
                authorization=authorization,
                signing_key=signing_key,
                now=now,
            )
            hold = ledger.initialize_and_hold_in_context(
                ctx,
                run_id=authorization.authorization_id,
                role=role,
                approved_ceiling_cents=ceiling_cents,
                hold_id=hold_id,
            )
            if mutation is not None:
                mutation(ctx, record, hold)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return record, hold


def begin_reserved_provider_submission_set(
    *,
    db_path: str,
    authorizations: tuple[MultimediaExecutionAuthorizationV2, ...],
    signing_key: bytes,
    now: datetime,
    mutation: Callable[
        [WriteContext, tuple[tuple[ProviderExecutionRecord, CallHold], ...]], None
    ]
    | None = None,
) -> tuple[tuple[ProviderExecutionRecord, CallHold], ...]:
    """Atomically consume and reserve a complete signed provider-call set.

    This is the admission boundary for multi-call products. Either every exact
    authorization and full spend band is durable, or the transaction rolls all
    of them back before any caller can reach provider transport.
    """
    if not authorizations:
        raise ValueError("provider submission set cannot be empty")
    ids = tuple(row.authorization_id for row in authorizations)
    if len(set(ids)) != len(ids):
        raise ValueError("provider submission set authorization ids must be unique")
    ledger = BudgetLedger(_db_path(db_path))
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context(
        "multimedia.provider_execution.begin_reserved_set"
    ) as ctx:
        _ensure_schema(ctx)
        ctx.execute("BEGIN TRANSACTION")
        results: list[tuple[ProviderExecutionRecord, CallHold]] = []
        try:
            for authorization in authorizations:
                record = _begin_in_context(
                    ctx,
                    authorization=authorization,
                    signing_key=signing_key,
                    now=now,
                )
                ceiling_cents = (
                    authorization.approved_ceiling_microdollars + 9_999
                ) // 10_000
                hold_id = "mmhold_" + hashlib.sha256(
                    f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
                ).hexdigest()
                hold = ledger.initialize_and_hold_in_context(
                    ctx,
                    run_id=authorization.authorization_id,
                    role=f"multimedia:{authorization.provider}",
                    approved_ceiling_cents=ceiling_cents,
                    hold_id=hold_id,
                )
                results.append((record, hold))
            frozen = tuple(results)
            if mutation is not None:
                mutation(ctx, frozen)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return frozen


def _begin_in_context(
    ctx: WriteContext,
    *,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    now: datetime,
) -> ProviderExecutionRecord:
    existing = ctx.execute(
        "SELECT * FROM multimedia_provider_executions WHERE authorization_id = ?",
        [authorization.authorization_id],
    ).fetchone()
    if existing is not None:
        _verify_self(
            authorization,
            signing_key=signing_key,
            now=_authorization_issued_at(authorization),
        )
        record = _record(existing, signing_key=signing_key)
        _verify_record_matches(record, authorization)
        return record
    _verify_self(authorization, signing_key=signing_key, now=now)
    revoked = ctx.execute(
        "SELECT operator_id, authorization_signature, revoked_at, revocation_mac "
        "FROM multimedia_async_execution_authorization_revocations "
        "WHERE authorization_id = ?",
        [authorization.authorization_id],
    ).fetchone()
    if revoked is not None:
        verify_async_revocation_record(
            authorization,
            signing_key=signing_key,
            operator_id=revoked[0],
            authorization_signature=revoked[1],
            revoked_at=revoked[2],
            revocation_mac=revoked[3],
        )
        raise ExecutionAuthorizationRevoked(
            f"authorization {authorization.authorization_id} was revoked"
        )
    claimed = ctx.execute(
        "INSERT INTO multimedia_execution_authorization_claims "
        "(authorization_id, signature, status, actual_cents, claimed_at, settled_at) "
        "VALUES (?, ?, 'claimed', NULL, CURRENT_TIMESTAMP, NULL) "
        "ON CONFLICT DO NOTHING RETURNING authorization_id",
        [authorization.authorization_id, authorization.signature],
    ).fetchone()
    if claimed is None:
        raise ExecutionAuthorizationConsumed(
            f"authorization {authorization.authorization_id} was already consumed"
        )
    timestamp = _timestamp(now)
    execution_id = (
        "mmexec_"
        + hashlib.sha256(
            f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
        ).hexdigest()
    )
    values = [
        execution_id,
        authorization.authorization_id,
        authorization.signature,
        authorization.operator_id,
        authorization.asset_id,
        authorization.revision_id,
        authorization.provider,
        authorization.route_policy,
        authorization.model,
        authorization.endpoint_capability,
        authorization.catalog_version,
        authorization.catalog_digest,
        authorization.quote_id,
        authorization.approved_ceiling_microdollars,
        authorization.request_body_digest,
        ProviderExecutionStatus.SUBMITTING.value,
        None,
        timestamp,
        timestamp,
        authorization.recovery_authority_id,
        authorization.recovery_verification_key_digest,
    ]
    values.append(_record_mac(signing_key, values))
    ctx.execute(
        "INSERT INTO multimedia_provider_executions VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        values,
    )
    row = ctx.execute(
        "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is None:
        raise ProviderExecutionIntegrityError("submission intent disappeared")
    return _record(row, signing_key=signing_key)


def bind_provider_job(
    *,
    db_path: str,
    execution_id: str,
    provider_job_id: str,
    signing_key: bytes,
    now: datetime,
) -> ProviderExecutionRecord:
    """Bind the one provider job returned by a successful submission response."""
    return _transition(
        db_path=db_path,
        execution_id=execution_id,
        target=ProviderExecutionStatus.SUBMITTED,
        provider_job_id=_identifier("provider_job_id", provider_job_id),
        evidence_digest=None,
        signing_key=signing_key,
        now=now,
    )


def bind_provider_job_with_mutation(
    *,
    db_path: str,
    execution_id: str,
    provider_job_id: str,
    signing_key: bytes,
    now: datetime,
    mutation: Callable[[WriteContext], None],
) -> ProviderExecutionRecord:
    """Bind a returned/recovered job and caller-owned receipt atomically.

    An ``outcome_unknown`` execution requires previously authenticated external
    recovery evidence for this exact provider job ID.
    """
    execution_id = _identifier("execution_id", execution_id)
    provider_job_id = _identifier("provider_job_id", provider_job_id)
    timestamp = _timestamp(now)
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context(
        "multimedia.provider_execution.bind_with_mutation"
    ) as ctx:
        _ensure_schema(ctx)
        ctx.execute("BEGIN TRANSACTION")
        try:
            row = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if row is None:
                raise ProviderExecutionIntegrityError("provider execution does not exist")
            current = _record(row, signing_key=signing_key)
            if current.provider_job_id is not None and current.provider_job_id != provider_job_id:
                raise ProviderExecutionIntegrityError("provider job binding conflicts")
            if current.status not in {
                ProviderExecutionStatus.SUBMITTING,
                ProviderExecutionStatus.SUBMITTED,
                ProviderExecutionStatus.OUTCOME_UNKNOWN,
            }:
                raise ProviderExecutionIntegrityError("provider job binding state is invalid")
            if current.status is ProviderExecutionStatus.OUTCOME_UNKNOWN:
                _verify_external_recovery_evidence(
                    ctx,
                    execution_id=execution_id,
                    provider_job_id=provider_job_id,
                    signing_key=signing_key,
                )
            if current.status in {
                ProviderExecutionStatus.SUBMITTING,
                ProviderExecutionStatus.OUTCOME_UNKNOWN,
            }:
                if datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ) < datetime.fromisoformat(current.updated_at.replace("Z", "+00:00")):
                    raise ProviderExecutionIntegrityError(
                        "provider job binding predates current execution state"
                    )
                mutable_values = list(row[:15]) + [
                    ProviderExecutionStatus.SUBMITTED.value,
                    provider_job_id,
                    row[17],
                    timestamp,
                    row[19],
                    row[20],
                ]
                ctx.execute(
                    "UPDATE multimedia_provider_executions SET status = ?, provider_job_id = ?, "
                    "updated_at = ?, record_mac = ? WHERE execution_id = ?",
                    [
                        ProviderExecutionStatus.SUBMITTED.value,
                        provider_job_id,
                        timestamp,
                        _record_mac(signing_key, mutable_values),
                        execution_id,
                    ],
                )
            mutation(ctx)
            updated = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if updated is None:
                raise ProviderExecutionIntegrityError("provider execution disappeared")
            result = _record(updated, signing_key=signing_key)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return result


def record_provider_observation(
    *,
    db_path: str,
    execution_id: str,
    provider_job_id: str,
    status: ProviderExecutionStatus,
    evidence_digest: str,
    signing_key: bytes,
    observed_at: datetime,
) -> ProviderExecutionRecord:
    """Apply one authenticated provider observation idempotently."""
    if status in {ProviderExecutionStatus.SUBMITTING, ProviderExecutionStatus.SUBMITTED}:
        raise ValueError("provider observation status is not allowed")
    return _transition(
        db_path=db_path,
        execution_id=execution_id,
        target=status,
        provider_job_id=_identifier("provider_job_id", provider_job_id),
        evidence_digest=_digest("evidence_digest", evidence_digest),
        signing_key=signing_key,
        now=observed_at,
    )


def request_provider_cancellation(
    *, db_path: str, execution_id: str, signing_key: bytes, now: datetime
) -> ProviderExecutionRecord:
    """Persist cancellation intent without any outbound provider I/O."""
    return _transition(
        db_path=db_path,
        execution_id=execution_id,
        target=ProviderExecutionStatus.CANCEL_REQUESTED,
        provider_job_id=None,
        evidence_digest=None,
        signing_key=signing_key,
        now=now,
    )


def record_external_recovery_evidence(
    *,
    db_path: str,
    execution_id: str,
    provider_job_id: str,
    source: str,
    evidence_digest: str,
    signing_key: bytes,
    evidence_verification_key: bytes,
    external_signature: str,
    recorded_at: datetime,
    verified_at: datetime | None = None,
) -> ExternalRecoveryEvidence:
    """Authorize one job-ID recovery for an ambiguous job-less submission."""
    execution_id = _identifier("execution_id", execution_id)
    provider_job_id = _identifier("provider_job_id", provider_job_id)
    source = _identifier("source", source)
    evidence_digest = _digest("evidence_digest", evidence_digest)
    timestamp = _timestamp(recorded_at)
    external_signature = _digest("external_signature", external_signature)
    _verify_external_signature(
        evidence_verification_key,
        execution_id=execution_id,
        provider_job_id=provider_job_id,
        source=source,
        evidence_digest=evidence_digest,
        recorded_at=timestamp,
        external_signature=external_signature,
    )
    values: list[object] = [
        execution_id,
        provider_job_id,
        source,
        evidence_digest,
        timestamp,
        external_signature,
    ]
    evidence_mac = _evidence_mac(signing_key, values)
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context(
        "multimedia.provider_execution.external_evidence"
    ) as ctx:
        _ensure_schema(ctx)
        current_row = ctx.execute(
            "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
        if current_row is None:
            raise ProviderExecutionIntegrityError("provider execution does not exist")
        current = _record(current_row, signing_key=signing_key)
        if (
            source != current.recovery_authority_id
            or hashlib.sha256(evidence_verification_key).hexdigest()
            != current.recovery_verification_key_digest
        ):
            raise ProviderExecutionIntegrityError(
                "external recovery authority does not match signed authorization"
            )
        if (
            current.status is not ProviderExecutionStatus.OUTCOME_UNKNOWN
            or current.provider_job_id is not None
        ):
            raise ProviderExecutionIntegrityError(
                "external evidence requires a job-less unknown execution"
            )
        checked_at = _timestamp(verified_at) if verified_at is not None else timestamp
        if datetime.fromisoformat(timestamp.replace("Z", "+00:00")) > datetime.fromisoformat(
            checked_at.replace("Z", "+00:00")
        ):
            raise ProviderExecutionIntegrityError(
                "external recovery evidence postdates verification"
            )
        if datetime.fromisoformat(checked_at.replace("Z", "+00:00")) < datetime.fromisoformat(
            current.updated_at.replace("Z", "+00:00")
        ):
            raise ProviderExecutionIntegrityError(
                "external recovery evidence predates unknown execution state"
            )
        existing = ctx.execute(
            "SELECT provider_job_id, source, evidence_digest, recorded_at, "
            "external_signature, evidence_mac "
            "FROM multimedia_provider_external_recovery_evidence WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
        if existing is not None:
            stored_values: list[object] = [execution_id, *existing[:5]]
            if (
                existing[:5]
                != (
                    provider_job_id,
                    source,
                    evidence_digest,
                    timestamp,
                    external_signature,
                )
                or not isinstance(existing[5], str)
                or not hmac.compare_digest(existing[5], _evidence_mac(signing_key, stored_values))
            ):
                raise ProviderExecutionIntegrityError(
                    "external recovery evidence conflicts or is corrupt"
                )
            timestamp = str(existing[3])
        else:
            ctx.execute(
                "INSERT INTO multimedia_provider_external_recovery_evidence "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    execution_id,
                    provider_job_id,
                    source,
                    evidence_digest,
                    timestamp,
                    external_signature,
                    evidence_mac,
                ],
            )
    return ExternalRecoveryEvidence(
        execution_id=execution_id,
        provider_job_id=provider_job_id,
        source=source,
        evidence_digest=evidence_digest,
        recorded_at=timestamp,
        external_signature=external_signature,
    )


def mark_submission_outcome_unknown(
    *, db_path: str, execution_id: str, signing_key: bytes, now: datetime
) -> ProviderExecutionRecord:
    """Quarantine an ambiguous or stale submission without enabling retry."""
    return _transition(
        db_path=db_path,
        execution_id=execution_id,
        target=ProviderExecutionStatus.OUTCOME_UNKNOWN,
        provider_job_id=None,
        evidence_digest=None,
        signing_key=signing_key,
        now=now,
    )


def charge_and_mark_submission_unknown(
    *,
    db_path: str,
    execution_id: str,
    hold: CallHold,
    signing_key: bytes,
    now: datetime,
) -> ProviderExecutionRecord:
    """Atomically charge the full hold and quarantine an ambiguous submission."""
    timestamp = _timestamp(now)
    execution_id = _identifier("execution_id", execution_id)
    ledger = BudgetLedger(_db_path(db_path))
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context("multimedia.provider_execution.charge_unknown") as ctx:
        _ensure_schema(ctx)
        ledger.ensure_schema_in_context(ctx)
        ctx.execute("BEGIN TRANSACTION")
        try:
            row = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if row is None:
                raise ProviderExecutionIntegrityError("provider execution does not exist")
            current = _record(row, signing_key=signing_key)
            if current.authorization_id != hold.run_id:
                raise ProviderExecutionIntegrityError("call hold belongs to another authorization")
            if current.status not in {
                ProviderExecutionStatus.SUBMITTING,
                ProviderExecutionStatus.OUTCOME_UNKNOWN,
            }:
                raise ProviderExecutionIntegrityError(
                    "only an unbound submission can be charged as unknown"
                )
            if current.provider_job_id is not None:
                raise ProviderExecutionIntegrityError(
                    "job-bound execution cannot use submission-unknown accounting"
                )
            ledger.charge_full_hold_in_context(ctx, hold)
            if current.status is ProviderExecutionStatus.OUTCOME_UNKNOWN:
                result = current
            else:
                if datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ) < datetime.fromisoformat(current.updated_at.replace("Z", "+00:00")):
                    raise ProviderExecutionIntegrityError(
                        "unknown outcome predates current execution state"
                    )
                mutable_values = list(row[:15]) + [
                    ProviderExecutionStatus.OUTCOME_UNKNOWN.value,
                    None,
                    row[17],
                    timestamp,
                    row[19],
                    row[20],
                ]
                ctx.execute(
                    "UPDATE multimedia_provider_executions SET status = ?, updated_at = ?, "
                    "record_mac = ? WHERE execution_id = ?",
                    [
                        ProviderExecutionStatus.OUTCOME_UNKNOWN.value,
                        timestamp,
                        _record_mac(signing_key, mutable_values),
                        execution_id,
                    ],
                )
                updated = ctx.execute(
                    "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
                    [execution_id],
                ).fetchone()
                if updated is None:
                    raise ProviderExecutionIntegrityError("provider execution disappeared")
                result = _record(updated, signing_key=signing_key)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return result


def get_provider_execution(
    *, db_path: str, execution_id: str, signing_key: bytes
) -> ProviderExecutionRecord:
    with connect_read(_db_path(db_path)) as ctx:
        row = ctx.execute(
            "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
            [_identifier("execution_id", execution_id)],
        ).fetchone()
    if row is None:
        raise ProviderExecutionIntegrityError("provider execution does not exist")
    return _record(row, signing_key=signing_key)


def _transition(
    *,
    db_path: str,
    execution_id: str,
    target: ProviderExecutionStatus,
    provider_job_id: str | None,
    evidence_digest: str | None,
    signing_key: bytes,
    now: datetime,
) -> ProviderExecutionRecord:
    if not isinstance(target, ProviderExecutionStatus):
        raise ValueError("target must be ProviderExecutionStatus")
    timestamp = _timestamp(now)
    execution_id = _identifier("execution_id", execution_id)
    coordinator = FlockWriteCoordinator(_db_path(db_path))
    with coordinator.acquire_write_context("multimedia.provider_execution.transition") as ctx:
        _ensure_schema(ctx)
        ctx.execute("BEGIN TRANSACTION")
        try:
            row = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if row is None:
                raise ProviderExecutionIntegrityError("provider execution does not exist")
            current = _record(row, signing_key=signing_key)
            bound_job = current.provider_job_id
            if (
                bound_job is not None
                and provider_job_id is not None
                and bound_job != provider_job_id
            ):
                raise ProviderExecutionIntegrityError("provider job binding conflicts")
            same_state = target is current.status
            if same_state and evidence_digest is None:
                ctx.execute("COMMIT")
                return current
            next_job: str | None
            if target is ProviderExecutionStatus.SUBMITTED:
                if provider_job_id is None:
                    raise ValueError("submitted execution requires provider_job_id")
                if current.status is ProviderExecutionStatus.OUTCOME_UNKNOWN:
                    _verify_external_recovery_evidence(
                        ctx,
                        execution_id=execution_id,
                        provider_job_id=provider_job_id,
                        signing_key=signing_key,
                    )
                next_job = provider_job_id
            else:
                next_job = bound_job
                if current.status is not ProviderExecutionStatus.SUBMITTING and next_job is None:
                    raise ProviderExecutionIntegrityError("provider execution has no job binding")
            observation_id = None
            if evidence_digest is not None:
                if next_job is None:
                    raise ProviderExecutionIntegrityError("provider observation has no job binding")
                observation_id = (
                    "mmobs_"
                    + hashlib.sha256(
                        json.dumps(
                            [execution_id, next_job, target.value, evidence_digest],
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                )
                existing_observation = ctx.execute(
                    "SELECT observation_id, execution_id, provider_job_id, status, evidence_digest, "
                    "observed_at, observation_mac "
                    "FROM multimedia_provider_execution_observations "
                    "WHERE observation_id = ?",
                    [observation_id],
                ).fetchone()
                if existing_observation is not None:
                    expected_observation_values: list[object] = [
                        observation_id,
                        execution_id,
                        next_job,
                        target.value,
                        evidence_digest,
                        existing_observation[5],
                    ]
                    if (
                        existing_observation[:5] != tuple(expected_observation_values[:5])
                        or not isinstance(existing_observation[6], str)
                        or not hmac.compare_digest(
                            existing_observation[6],
                            _evidence_mac(signing_key, expected_observation_values),
                        )
                    ):
                        raise ProviderExecutionIntegrityError(
                            "provider observation identity is corrupt"
                        )
                    ctx.execute("COMMIT")
                    return current
            if same_state and current.status in TERMINAL_STATUSES:
                raise ProviderExecutionIntegrityError(
                    "terminal provider execution evidence conflicts with stored observation"
                )
            if not same_state and target not in _ALLOWED_TRANSITIONS[current.status]:
                raise ProviderExecutionIntegrityError(
                    f"provider execution transition {current.status.value}->{target.value} is invalid"
                )
            if datetime.fromisoformat(timestamp.replace("Z", "+00:00")) < datetime.fromisoformat(
                current.updated_at.replace("Z", "+00:00")
            ):
                raise ProviderExecutionIntegrityError(
                    "provider observation predates current execution state"
                )
            mutable_values = list(row[:15]) + [
                target.value,
                next_job,
                row[17],
                timestamp,
                row[19],
                row[20],
            ]
            updated_mac = _record_mac(signing_key, mutable_values)
            ctx.execute(
                "UPDATE multimedia_provider_executions SET status = ?, provider_job_id = ?, "
                "updated_at = ?, record_mac = ? WHERE execution_id = ?",
                [target.value, next_job, timestamp, updated_mac, execution_id],
            )
            if observation_id is not None and next_job is not None:
                observation_values: list[object] = [
                    observation_id,
                    execution_id,
                    next_job,
                    target.value,
                    evidence_digest,
                    timestamp,
                ]
                ctx.execute(
                    "INSERT INTO multimedia_provider_execution_observations "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [*observation_values, _evidence_mac(signing_key, observation_values)],
                )
            updated = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if updated is None:
                raise ProviderExecutionIntegrityError("provider execution disappeared")
            result = _record(updated, signing_key=signing_key)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return result


def _ensure_schema(ctx: WriteContext) -> None:
    ctx.execute(_AUTHORIZATION_CLAIMS_DDL)
    ctx.execute(_REVOCATIONS_DDL)
    ctx.execute(_ASYNC_REVOCATIONS_DDL)
    ctx.execute(_EXECUTIONS_DDL)
    ctx.execute(_OBSERVATIONS_DDL)
    ctx.execute(_RECONCILIATIONS_DDL)
    ctx.execute(_ARTIFACT_CANDIDATES_DDL)
    ctx.execute(_RECOVERY_EVIDENCE_DDL)


def _record(row: tuple[object, ...], *, signing_key: bytes) -> ProviderExecutionRecord:
    try:
        if len(row) != 22 or not isinstance(row[21], str):
            raise ValueError("provider execution row shape is invalid")
        expected_mac = _record_mac(signing_key, list(row[:21]))
        if not hmac.compare_digest(row[21], expected_mac):
            raise ValueError("provider execution signature is invalid")
        status = ProviderExecutionStatus(str(row[15]))
        record = ProviderExecutionRecord(
            execution_id=str(row[0]),
            authorization_id=str(row[1]),
            operator_id=str(row[3]),
            asset_id=str(row[4]),
            revision_id=str(row[5]),
            provider=str(row[6]),
            route_policy=str(row[7]),
            model=str(row[8]),
            endpoint_capability=str(row[9]),
            catalog_version=str(row[10]),
            catalog_digest=_digest("catalog_digest", row[11]),
            quote_id=str(row[12]),
            approved_ceiling_microdollars=_microdollars(row[13]),
            request_body_digest=_digest("request_body_digest", row[14]),
            status=status,
            provider_job_id=str(row[16]) if row[16] is not None else None,
            created_at=_canonical_timestamp(row[17]),
            updated_at=_canonical_timestamp(row[18]),
            recovery_authority_id=_identifier("recovery_authority_id", row[19]),
            recovery_verification_key_digest=_digest("recovery_verification_key_digest", row[20]),
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise ProviderExecutionIntegrityError("provider execution row is corrupt") from exc
    expected_id = (
        "mmexec_"
        + hashlib.sha256(
            f"{record.authorization_id}:{record.request_body_digest}".encode()
        ).hexdigest()
    )
    if record.execution_id != expected_id:
        raise ProviderExecutionIntegrityError("provider execution identity is corrupt")
    return record


def _record_mac(signing_key: bytes, values: list[object]) -> str:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    canonical = json.dumps(
        values,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hmac.new(signing_key, canonical, hashlib.sha256).hexdigest()


def _evidence_mac(signing_key: bytes, values: list[object]) -> str:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    canonical = json.dumps(
        values,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hmac.new(signing_key, canonical, hashlib.sha256).hexdigest()


def _verify_external_signature(
    evidence_verification_key: bytes,
    *,
    execution_id: str,
    provider_job_id: str,
    source: str,
    evidence_digest: str,
    recorded_at: str,
    external_signature: str,
) -> None:
    values: list[object] = [
        execution_id,
        provider_job_id,
        source,
        evidence_digest,
        recorded_at,
    ]
    expected = _evidence_mac(evidence_verification_key, values)
    if not hmac.compare_digest(external_signature, expected):
        raise ProviderExecutionIntegrityError("external recovery evidence signature is invalid")


def _verify_external_recovery_evidence(
    ctx: WriteContext,
    *,
    execution_id: str,
    provider_job_id: str,
    signing_key: bytes,
) -> None:
    row = ctx.execute(
        "SELECT execution_id, provider_job_id, source, evidence_digest, recorded_at, "
        "external_signature, evidence_mac "
        "FROM multimedia_provider_external_recovery_evidence "
        "WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is None or row[1] != provider_job_id or not isinstance(row[6], str):
        raise ProviderExecutionIntegrityError(
            "provider job recovery lacks matching external evidence"
        )
    if not hmac.compare_digest(row[6], _evidence_mac(signing_key, list(row[:6]))):
        raise ProviderExecutionIntegrityError("external recovery evidence is corrupt")


def _authorization_issued_at(
    authorization: MultimediaExecutionAuthorizationV2,
) -> datetime:
    try:
        value = datetime.fromisoformat(authorization.issued_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ExecutionAuthorizationIntegrityError(
            "malformed asynchronous authorization timestamp"
        ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ExecutionAuthorizationIntegrityError("malformed asynchronous authorization timestamp")
    return value


def _verify_self(
    authorization: MultimediaExecutionAuthorizationV2,
    *,
    signing_key: bytes,
    now: datetime,
) -> None:
    verify_async_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=authorization.operator_id,
        asset_id=authorization.asset_id,
        revision_id=authorization.revision_id,
        provider=authorization.provider,
        route_policy=authorization.route_policy,
        model=authorization.model,
        endpoint_capability=authorization.endpoint_capability,
        catalog_version=authorization.catalog_version,
        catalog_digest=authorization.catalog_digest,
        quote_id=authorization.quote_id,
        recovery_authority_id=authorization.recovery_authority_id,
        recovery_verification_key_digest=(authorization.recovery_verification_key_digest),
        approved_ceiling_microdollars=authorization.approved_ceiling_microdollars,
        request_body_digest=authorization.request_body_digest,
        now=now,
    )


def _verify_record_matches(
    record: ProviderExecutionRecord,
    authorization: MultimediaExecutionAuthorizationV2,
) -> None:
    expected = (
        authorization.authorization_id,
        authorization.operator_id,
        authorization.asset_id,
        authorization.revision_id,
        authorization.provider,
        authorization.route_policy,
        authorization.model,
        authorization.endpoint_capability,
        authorization.catalog_version,
        authorization.catalog_digest,
        authorization.quote_id,
        authorization.approved_ceiling_microdollars,
        authorization.request_body_digest,
        authorization.recovery_authority_id,
        authorization.recovery_verification_key_digest,
    )
    actual = (
        record.authorization_id,
        record.operator_id,
        record.asset_id,
        record.revision_id,
        record.provider,
        record.route_policy,
        record.model,
        record.endpoint_capability,
        record.catalog_version,
        record.catalog_digest,
        record.quote_id,
        record.approved_ceiling_microdollars,
        record.request_body_digest,
        record.recovery_authority_id,
        record.recovery_verification_key_digest,
    )
    if actual != expected:
        raise ProviderExecutionIntegrityError("provider execution conflicts with authorization")


def _db_path(value: object) -> str:
    return _identifier("db_path", value)


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty canonical string")
    return value


def _digest(name: str, value: object) -> str:
    text = _identifier(name, value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return text


def _microdollars(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("approved_ceiling_microdollars must be a positive integer")
    if value > 9_223_372_036_854_775_807:
        raise ValueError("approved_ceiling_microdollars exceeds signed-BIGINT")
    return value


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_timestamp(value: object) -> str:
    text = _identifier("timestamp", value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or _timestamp(parsed) != text:
        raise ValueError("timestamp is not canonical UTC")
    return text


__all__ = [
    "ExternalRecoveryEvidence",
    "ProviderArtifactCandidate",
    "ProviderExecutionIntegrityError",
    "ProviderExecutionRecord",
    "ProviderExecutionStatus",
    "ProviderStatusObservation",
    "TERMINAL_STATUSES",
    "begin_provider_submission",
    "begin_reserved_provider_submission",
    "begin_reserved_provider_submission_set",
    "bind_provider_job",
    "bind_provider_job_with_mutation",
    "charge_and_mark_submission_unknown",
    "get_provider_execution",
    "mark_submission_outcome_unknown",
    "record_external_recovery_evidence",
    "record_provider_observation",
    "request_provider_cancellation",
]

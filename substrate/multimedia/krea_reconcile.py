"""Single durable Krea reconciliation authority."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from integrations.krea.client import KreaClient
from integrations.krea.reconciliation import normalize_poll
from runtime.db_lock import FlockWriteCoordinator, WriteContext
from substrate.midnight_oil.budget_ledger import BudgetLedger

from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionRecord,
    ProviderExecutionStatus,
    _ensure_schema,
    _evidence_mac,
    _record,
    _record_mac,
    _timestamp,
    get_provider_execution,
)


@dataclass(frozen=True)
class _ReconciliationObservation:
    provider: str
    provider_job_id: str
    authorization_id: str
    request_body_digest: str
    account_identity_digest: str
    source: str
    raw_payload_digest: str
    status: ProviderExecutionStatus
    result_locators: tuple[str, ...] = ()


def observe_provider_job(
    *,
    db_path: str,
    execution_id: str,
    client: KreaClient,
    signing_key: bytes,
    observed_at: datetime,
    before_commit: Callable[[WriteContext], None] | None = None,
) -> ProviderExecutionRecord:
    """Load signed authority, perform exactly one authenticated poll, then reconcile."""
    current = get_provider_execution(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    if current.provider != "krea" or current.provider_job_id is None:
        raise ProviderExecutionIntegrityError("execution is not a bound Krea job")
    normalized = normalize_poll(client.poll(current.provider_job_id))
    observation = _ReconciliationObservation(
        provider=current.provider,
        provider_job_id=normalized.provider_job_id,
        authorization_id=current.authorization_id,
        request_body_digest=current.request_body_digest,
        account_identity_digest=normalized.account_identity_digest,
        source=normalized.source,
        raw_payload_digest=normalized.raw_payload_digest,
        status=ProviderExecutionStatus(normalized.status),
        result_locators=normalized.result_locators,
    )
    return _apply_observation(
        db_path=db_path,
        execution_id=execution_id,
        observation=observation,
        signing_key=signing_key,
        observed_at=observed_at,
        before_commit=before_commit,
    )


def _apply_observation(
    *,
    db_path: str,
    execution_id: str,
    observation: _ReconciliationObservation,
    signing_key: bytes,
    observed_at: datetime,
    before_commit: Callable[[WriteContext], None] | None = None,
) -> ProviderExecutionRecord:
    """Private transactional observer for internally normalized poll evidence."""
    _validate_observation(observation)
    timestamp = _timestamp(observed_at)
    evidence = json.dumps(
        {
            "result_digests": [
                hashlib.sha256(item.encode()).hexdigest() for item in observation.result_locators
            ]
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    identity = [
        execution_id,
        observation.provider,
        observation.provider_job_id,
        observation.authorization_id,
        observation.request_body_digest,
        observation.account_identity_digest,
        observation.source,
        observation.raw_payload_digest,
    ]
    observation_id = (
        "mmrecon_"
        + hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    )
    coordinator = FlockWriteCoordinator(db_path)
    ledger = BudgetLedger(db_path)
    with coordinator.acquire_write_context("multimedia.krea.reconcile") as ctx:
        _ensure_schema(ctx)
        ledger.ensure_schema_in_context(ctx)
        ctx.execute("BEGIN TRANSACTION")
        try:
            row = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id=?", [execution_id]
            ).fetchone()
            if row is None:
                raise ProviderExecutionIntegrityError("provider execution does not exist")
            current = _record(row, signing_key=signing_key)
            _verify_bindings(current, observation)
            values: list[object] = [
                observation_id,
                execution_id,
                *identity[1:],
                observation.status.value,
                evidence,
                timestamp,
            ]
            existing = ctx.execute(
                "SELECT * FROM multimedia_provider_reconciliations WHERE observation_id=?",
                [observation_id],
            ).fetchone()
            if existing is not None:
                stored = list(existing[:-1])
                if (
                    stored[:-1] != values[:-1]
                    or not isinstance(existing[-1], str)
                    or not hmac.compare_digest(existing[-1], _evidence_mac(signing_key, stored))
                ):
                    raise ProviderExecutionIntegrityError("reconciliation replay conflicts")
                _verify_terminal_accounting(ctx, current, authorization_signature=str(row[2]))
                ctx.execute("COMMIT")
                return current
            account = ctx.execute(
                "SELECT account_identity_digest FROM multimedia_provider_reconciliations "
                "WHERE execution_id=? LIMIT 1",
                [execution_id],
            ).fetchone()
            if account is not None and account[0] != observation.account_identity_digest:
                raise ProviderExecutionIntegrityError("provider account binding conflicts")
            target = observation.status
            if current.status in {
                ProviderExecutionStatus.SUCCEEDED,
                ProviderExecutionStatus.FAILED,
                ProviderExecutionStatus.CANCELLED,
            }:
                if current.status is not target:
                    raise ProviderExecutionIntegrityError("terminal provider outcome conflicts")
                _verify_terminal_accounting(ctx, current, authorization_signature=str(row[2]))
                ctx.execute(
                    "INSERT INTO multimedia_provider_reconciliations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [*values, _evidence_mac(signing_key, values)],
                )
                ctx.execute("COMMIT")
                return current
            ranks = {
                ProviderExecutionStatus.SUBMITTED: 1,
                ProviderExecutionStatus.RUNNING: 2,
                ProviderExecutionStatus.CANCEL_REQUESTED: 2,
                ProviderExecutionStatus.CANCEL_ACKNOWLEDGED: 2,
                ProviderExecutionStatus.OUTCOME_UNKNOWN: 0,
                ProviderExecutionStatus.SUCCEEDED: 3,
                ProviderExecutionStatus.FAILED: 3,
                ProviderExecutionStatus.CANCELLED: 3,
            }
            cancellation_poll = current.status in {
                ProviderExecutionStatus.CANCEL_REQUESTED,
                ProviderExecutionStatus.CANCEL_ACKNOWLEDGED,
            } and target in {
                ProviderExecutionStatus.SUBMITTED,
                ProviderExecutionStatus.RUNNING,
                ProviderExecutionStatus.OUTCOME_UNKNOWN,
            }
            if not cancellation_poll and ranks.get(target, -1) < ranks.get(current.status, -1):
                raise ProviderExecutionIntegrityError("provider observation regresses state")
            expected = (current.approved_ceiling_microdollars + 9_999) // 10_000
            if target in {ProviderExecutionStatus.FAILED, ProviderExecutionStatus.CANCELLED}:
                hold = ctx.execute(
                    "SELECT projected_max_cents, state FROM midnight_oil_call_holds "
                    "WHERE run_id=?",
                    [current.authorization_id],
                ).fetchone()
                balance = ctx.execute(
                    "SELECT spent_cents, held_cents FROM midnight_oil_reservations WHERE run_id=?",
                    [current.authorization_id],
                ).fetchone()
                if hold != (expected, "open") or balance != (0, expected):
                    raise ProviderExecutionIntegrityError("terminal hold retention conflicts")
            ctx.execute(
                "INSERT INTO multimedia_provider_reconciliations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [*values, _evidence_mac(signing_key, values)],
            )
            effective = target
            if cancellation_poll:
                effective = current.status
            if effective != current.status:
                mutable = list(row[:15]) + [
                    effective.value,
                    row[16],
                    row[17],
                    timestamp,
                    row[19],
                    row[20],
                ]
                ctx.execute(
                    "UPDATE multimedia_provider_executions SET status=?, updated_at=?, "
                    "record_mac=? WHERE execution_id=?",
                    [effective.value, timestamp, _record_mac(signing_key, mutable), execution_id],
                )
            if target is ProviderExecutionStatus.SUCCEEDED:
                hold = ctx.execute(
                    "SELECT hold_id, projected_max_cents, state FROM "
                    "midnight_oil_call_holds WHERE run_id=?",
                    [current.authorization_id],
                ).fetchone()
                if hold is None:
                    raise ProviderExecutionIntegrityError("authorized call hold is missing")
                if hold[1] != expected:
                    raise ProviderExecutionIntegrityError("call hold ceiling conflicts")
                if hold[2] == "open":
                    ledger.settle_in_context(ctx, hold_id=hold[0], actual_cents=expected)
                elif hold[2] == "settled":
                    balance = ctx.execute(
                        "SELECT spent_cents, held_cents FROM midnight_oil_reservations "
                        "WHERE run_id=?",
                        [current.authorization_id],
                    ).fetchone()
                    if balance != (expected, 0):
                        raise ProviderExecutionIntegrityError("call hold was not ceiling-settled")
                else:
                    raise ProviderExecutionIntegrityError("call hold was not ceiling-settled")
                _insert_candidates(ctx, execution_id, observation.result_locators, signing_key)
            if target in {
                ProviderExecutionStatus.SUCCEEDED,
                ProviderExecutionStatus.FAILED,
                ProviderExecutionStatus.CANCELLED,
            }:
                _close_authorization_claim(
                    ctx,
                    authorization_id=current.authorization_id,
                    authorization_signature=str(row[2]),
                    status=target,
                    expected_cents=expected,
                    timestamp=timestamp,
                )
            if before_commit is not None:
                before_commit(ctx)
            updated = ctx.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id=?", [execution_id]
            ).fetchone()
            assert updated is not None
            result = _record(updated, signing_key=signing_key)
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return result


def _verify_bindings(record: ProviderExecutionRecord, obs: _ReconciliationObservation) -> None:
    if (
        record.provider != obs.provider
        or record.provider_job_id != obs.provider_job_id
        or record.authorization_id != obs.authorization_id
        or record.request_body_digest != obs.request_body_digest
    ):
        raise ProviderExecutionIntegrityError("reconciliation binding conflicts")
    if obs.source != "poll":
        raise ProviderExecutionIntegrityError("only authenticated polling may transition state")


def _verify_terminal_accounting(
    ctx: WriteContext, record: ProviderExecutionRecord, *, authorization_signature: str
) -> None:
    if record.status not in {
        ProviderExecutionStatus.SUCCEEDED,
        ProviderExecutionStatus.FAILED,
        ProviderExecutionStatus.CANCELLED,
    }:
        return
    expected = (record.approved_ceiling_microdollars + 9_999) // 10_000
    hold = ctx.execute(
        "SELECT projected_max_cents, state FROM midnight_oil_call_holds WHERE run_id=?",
        [record.authorization_id],
    ).fetchone()
    balance = ctx.execute(
        "SELECT spent_cents, held_cents FROM midnight_oil_reservations WHERE run_id=?",
        [record.authorization_id],
    ).fetchone()
    claim = ctx.execute(
        "SELECT signature, status, actual_cents, settled_at "
        "FROM multimedia_execution_authorization_claims "
        "WHERE authorization_id=?",
        [record.authorization_id],
    ).fetchone()
    required = (
        (
            (expected, "settled"),
            (expected, 0),
            authorization_signature,
            "settled",
            expected,
            True,
        )
        if record.status is ProviderExecutionStatus.SUCCEEDED
        else (
            (expected, "open"),
            (0, expected),
            authorization_signature,
            "reconciliation_required",
            None,
            False,
        )
    )
    observed = (
        hold,
        balance,
        claim[0] if claim else None,
        claim[1] if claim else None,
        claim[2] if claim else None,
        bool(claim and claim[3] is not None),
    )
    if observed != required:
        raise ProviderExecutionIntegrityError("terminal accounting conflicts")


def _close_authorization_claim(
    ctx: WriteContext,
    *,
    authorization_id: str,
    authorization_signature: str,
    status: ProviderExecutionStatus,
    expected_cents: int,
    timestamp: str,
) -> None:
    if status is ProviderExecutionStatus.SUCCEEDED:
        updated = ctx.execute(
            "UPDATE multimedia_execution_authorization_claims SET status='settled', "
            "actual_cents=?, settled_at=? WHERE authorization_id=? AND signature=? "
            "AND status='claimed' "
            "AND actual_cents IS NULL AND settled_at IS NULL RETURNING 1",
            [expected_cents, timestamp, authorization_id, authorization_signature],
        ).fetchone()
    else:
        updated = ctx.execute(
            "UPDATE multimedia_execution_authorization_claims SET status='reconciliation_required' "
            "WHERE authorization_id=? AND signature=? AND status='claimed' AND actual_cents IS NULL "
            "AND settled_at IS NULL RETURNING 1",
            [authorization_id, authorization_signature],
        ).fetchone()
    if updated is None:
        raise ProviderExecutionIntegrityError("authorization claim terminalization conflicts")


def _validate_observation(obs: _ReconciliationObservation) -> None:
    if not isinstance(obs.status, ProviderExecutionStatus) or obs.status in {
        ProviderExecutionStatus.SUBMITTING,
        ProviderExecutionStatus.CANCEL_REQUESTED,
        ProviderExecutionStatus.CANCEL_ACKNOWLEDGED,
    }:
        raise ValueError("status is not a provider poll outcome")
    for value in (obs.account_identity_digest, obs.raw_payload_digest, obs.request_body_digest):
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("observation digest is invalid")
    if len(obs.result_locators) > 8 or any(len(x) > 4096 for x in obs.result_locators):
        raise ValueError("artifact result locators are not bounded")


def _insert_candidates(
    ctx: WriteContext, execution_id: str, locators: Sequence[str], signing_key: bytes
) -> None:
    for ordinal, locator in enumerate(locators):
        digest = hashlib.sha256(locator.encode()).hexdigest()
        candidate_id = (
            "mmcandidate_"
            + hashlib.sha256(f"{execution_id}:{ordinal}:{digest}".encode()).hexdigest()
        )
        values: list[object] = [candidate_id, execution_id, ordinal, digest, "unknown"]
        ctx.execute(
            "INSERT INTO multimedia_provider_artifact_candidates VALUES "
            "(?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [*values, _evidence_mac(signing_key, values)],
        )


__all__ = ["observe_provider_job"]

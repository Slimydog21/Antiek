"""Operator-only commands and redacted status for chapter TTS recovery."""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from runtime.db_lock import connect_read

from .chapter_tts_production import (
    ChapterTTSAttempt,
    get_chapter_tts_attempt,
    get_chapter_tts_seal_lease,
)
from .execution_authorization import MultimediaExecutionAuthorizationV2
from .operations import MultimediaExecutionUnavailable
from .provider_execution import ProviderExecutionStatus, get_provider_execution
from .reconciliation_read_model import ChapterTTSReconciliationView, ReconciliationAction
from .tts_reconciliation import (
    ChapterTTSRecoveryAuthorization,
    quarantine_stale_send,
    recover_unknown_send,
    release_stale_seal,
)

_MAX_AUDIO_BYTES = 64 * 1024 * 1024


def get_chapter_tts_reconciliation(
    *,
    db_path: str,
    execution_id: str,
    authenticated_operator_id: str,
    signing_key: bytes,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSReconciliationView:
    """Return recovery state without paths, signatures, keys, or audio bytes."""
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    checked_at = _aware(now)
    try:
        execution = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
        if execution.operator_id != authenticated_operator_id:
            raise ValueError
        attempt = get_chapter_tts_attempt(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MultimediaExecutionUnavailable("multimedia execution is unavailable") from None

    age = _send_age(attempt, checked_at)
    seal_age, seal_lease_id = _seal_state(
        db_path=db_path,
        execution_id=execution_id,
        signing_key=signing_key,
        now=checked_at,
        required=attempt.status == "sealing",
    )
    raw_present, raw_valid = _raw_state(attempt)
    charged_cents = _validated_charged_cents(
        db_path=db_path,
        execution_id=execution.execution_id,
        authorization_id=execution.authorization_id,
        ceiling_cents=(execution.approved_ceiling_microdollars + 9_999) // 10_000,
        attempt_status=attempt.status,
        provider_status=execution.status,
    )
    action, eligible = _next_action(
        attempt,
        execution.status,
        age=age,
        seal_age=seal_age,
        stale_after=stale_after,
        raw_valid=raw_valid,
    )
    return ChapterTTSReconciliationView(
        execution_id=execution.execution_id,
        asset_id=execution.asset_id,
        revision_id=execution.revision_id,
        attempt_status=attempt.status,
        provider_status=execution.status,
        next_action=action,
        action_eligible=eligible,
        send_age_seconds=age,
        seal_age_seconds=seal_age,
        seal_lease_id=seal_lease_id,
        charged_cents=charged_cents,
        full_ceiling_charged=charged_cents
        == (execution.approved_ceiling_microdollars + 9_999) // 10_000,
        raw_audio_present=raw_present,
        raw_audio_hash_valid=raw_valid,
        requires_signed_operator_authority=action
        in {"quarantine_send", "recover_unknown", "release_seal"},
        requires_external_provider_evidence=action == "recover_unknown",
        parent_resume_eligible=action == "resume_narration",
        safe_error_code=(
            "raw_audio_invalid"
            if attempt.raw_path is not None and not raw_valid
            else "seal_lease_fresh"
            if attempt.status == "sealing" and not eligible
            else "provider_observation_pending"
            if attempt.status == "received"
            and execution.status is ProviderExecutionStatus.SUBMITTED
            else None
        ),
    )


def operator_quarantine_stale_send(
    *,
    authority: ChapterTTSRecoveryAuthorization,
    recovery_key: bytes,
    authenticated_operator_id: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    db_path: str,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSReconciliationView:
    _assert_owned(
        db_path=db_path,
        execution_id=authority.execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
    )
    quarantine_stale_send(
        authority=authority,
        recovery_key=recovery_key,
        operator_id=authenticated_operator_id,
        authorization=authorization,
        signing_key=signing_key,
        db_path=db_path,
        now=now,
        stale_after=stale_after,
    )
    return get_chapter_tts_reconciliation(
        db_path=db_path,
        execution_id=authority.execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
        now=now,
        stale_after=stale_after,
    )


def operator_recover_unknown_send(
    *,
    authority: ChapterTTSRecoveryAuthorization,
    recovery_key: bytes,
    authenticated_operator_id: str,
    signing_key: bytes,
    db_path: str,
    output_dir: str,
    provider_request_id: str,
    audio_bytes: bytes,
    evidence_source: str,
    evidence_verification_key: bytes,
    external_signature: str,
    recorded_at: datetime,
    verified_at: datetime | None = None,
) -> ChapterTTSReconciliationView:
    _assert_owned(
        db_path=db_path,
        execution_id=authority.execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
    )
    recover_unknown_send(
        authority=authority,
        recovery_key=recovery_key,
        operator_id=authenticated_operator_id,
        signing_key=signing_key,
        db_path=db_path,
        output_dir=output_dir,
        provider_request_id=provider_request_id,
        audio_bytes=audio_bytes,
        evidence_source=evidence_source,
        evidence_verification_key=evidence_verification_key,
        external_signature=external_signature,
        recorded_at=recorded_at,
        verified_at=verified_at,
    )
    return get_chapter_tts_reconciliation(
        db_path=db_path,
        execution_id=authority.execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
        now=verified_at or recorded_at,
    )


def operator_release_stale_seal(
    *,
    authority: ChapterTTSRecoveryAuthorization,
    recovery_key: bytes,
    authenticated_operator_id: str,
    signing_key: bytes,
    db_path: str,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSReconciliationView:
    _assert_owned(
        db_path=db_path,
        execution_id=authority.execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
    )
    release_stale_seal(
        authority=authority,
        recovery_key=recovery_key,
        operator_id=authenticated_operator_id,
        signing_key=signing_key,
        db_path=db_path,
        now=now,
        stale_after=stale_after,
    )
    return get_chapter_tts_reconciliation(
        db_path=db_path,
        execution_id=authority.execution_id,
        authenticated_operator_id=authenticated_operator_id,
        signing_key=signing_key,
        now=now,
        stale_after=stale_after,
    )


def _next_action(
    attempt: ChapterTTSAttempt,
    provider_status: ProviderExecutionStatus,
    *,
    age: int | None,
    seal_age: int | None,
    stale_after: timedelta,
    raw_valid: bool,
) -> tuple[ReconciliationAction, bool]:
    if attempt.status == "sending":
        eligible = age is not None and age >= int(stale_after.total_seconds())
        return ("quarantine_send" if eligible else "wait"), eligible
    if attempt.status == "outcome_unknown":
        return "recover_unknown", True
    if attempt.status == "received" and provider_status is ProviderExecutionStatus.SUBMITTED:
        return "recover_unknown", True
    if attempt.status == "sealing":
        eligible = (
            raw_valid and seal_age is not None and seal_age >= int(stale_after.total_seconds())
        )
        return ("release_seal", True) if eligible else ("wait", False)
    if attempt.status == "received":
        return ("resume_narration", True) if raw_valid else ("wait", False)
    return "none", False


def _send_age(attempt: ChapterTTSAttempt, now: datetime) -> int | None:
    if attempt.send_started_at is None:
        return None
    try:
        started = datetime.fromisoformat(attempt.send_started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((now - started.astimezone(UTC)).total_seconds()))


def _seal_state(
    *,
    db_path: str,
    execution_id: str,
    signing_key: bytes,
    now: datetime,
    required: bool,
) -> tuple[int | None, str | None]:
    if not required:
        return None, None
    try:
        lease = get_chapter_tts_seal_lease(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
        if lease.state != "active":
            raise ValueError
        acquired = datetime.fromisoformat(lease.acquired_at.replace("Z", "+00:00"))
        if now < acquired:
            raise ValueError
        return int((now - acquired).total_seconds()), lease.lease_id
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MultimediaExecutionUnavailable("multimedia execution is unavailable") from None


def _raw_state(attempt: ChapterTTSAttempt) -> tuple[bool, bool]:
    if attempt.raw_path is None:
        return False, False
    path = Path(attempt.raw_path)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_AUDIO_BYTES:
            return True, False
        if attempt.raw_sha256 is None:
            return True, False
        digest_state = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest_state.update(chunk)
        digest = digest_state.hexdigest()
        return True, digest == attempt.raw_sha256
    except OSError:
        return False, False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _assert_owned(
    *, db_path: str, execution_id: str, authenticated_operator_id: str, signing_key: bytes
) -> None:
    try:
        execution = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
        if execution.operator_id != authenticated_operator_id:
            raise ValueError
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MultimediaExecutionUnavailable("multimedia execution is unavailable") from None


def _validated_charged_cents(
    *,
    db_path: str,
    execution_id: str,
    authorization_id: str,
    ceiling_cents: int,
    attempt_status: str,
    provider_status: ProviderExecutionStatus,
) -> int:
    try:
        with connect_read(db_path) as connection:
            row = connection.execute(
                "SELECT r.spent_cents, r.held_cents, r.ceiling_cents, r.status, "
                "c.signature, c.status, c.actual_cents, e.authorization_signature "
                "FROM midnight_oil_reservations r "
                "JOIN multimedia_execution_authorization_claims c ON c.authorization_id=r.run_id "
                "JOIN multimedia_provider_executions e ON e.authorization_id=r.run_id "
                "WHERE r.run_id=? AND e.execution_id=?",
                [authorization_id, execution_id],
            ).fetchone()
        if row is None or len(row) != 8:
            raise ValueError
        spent, held, ceiling = int(row[0]), int(row[1]), int(row[2])
        if (
            min(spent, held) < 0
            or ceiling != ceiling_cents
            or spent + held > ceiling
            or row[4] != row[7]
        ):
            raise ValueError
        unknown_charged = attempt_status in {"outcome_unknown", "received", "sealing", "sealed"}
        if unknown_charged and (spent, held, row[3], row[5], row[6]) == (
            ceiling,
            0,
            "exhausted",
            "claimed",
            None,
        ):
            return spent
        if provider_status is ProviderExecutionStatus.SUCCEEDED and (
            spent,
            held,
            row[3],
            row[5],
            row[6],
        ) == (ceiling, 0, "exhausted", "settled", ceiling):
            return spent
        if not unknown_charged and (spent, held, row[5], row[6]) == (0, ceiling, "claimed", None):
            return spent
        raise ValueError
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MultimediaExecutionUnavailable("multimedia execution is unavailable") from None


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "get_chapter_tts_reconciliation",
    "operator_quarantine_stale_send",
    "operator_recover_unknown_send",
    "operator_release_stale_seal",
]

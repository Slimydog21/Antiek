"""Signed operator authority for chapter TTS crash reconciliation."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from .chapter_tts_production import (
    ChapterTTSAttempt,
    quarantine_stale_chapter_tts_send,
    recover_unknown_chapter_tts_audio,
    release_stale_chapter_tts_seal,
)
from .execution_authorization import MultimediaExecutionAuthorizationV2

RecoveryAction = Literal["quarantine_send", "recover_unknown", "release_seal"]
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_LIFETIME = timedelta(hours=1)


class ChapterTTSReconciliationError(RuntimeError):
    """A recovery authorization is invalid, expired, or bound elsewhere."""


@dataclass(frozen=True)
class ChapterTTSRecoveryAuthorization:
    schema_version: Literal["antiek.chapter-tts-recovery.v2"]
    authorization_id: str
    operator_id: str
    execution_id: str
    action: RecoveryAction
    lease_id: str | None
    issued_at: str
    expires_at: str
    signature: str


def issue_chapter_tts_recovery_authorization(
    *,
    recovery_key: bytes,
    operator_id: str,
    execution_id: str,
    action: RecoveryAction,
    issued_at: datetime,
    expires_at: datetime,
    lease_id: str | None = None,
) -> ChapterTTSRecoveryAuthorization:
    _key(recovery_key)
    operator_id = _identifier("operator_id", operator_id)
    execution_id = _identifier("execution_id", execution_id)
    if action not in {"quarantine_send", "recover_unknown", "release_seal"}:
        raise ValueError("invalid chapter TTS recovery action")
    if action == "release_seal":
        lease_id = _identifier("lease_id", lease_id) if lease_id is not None else None
        if lease_id is None:
            raise ValueError("release_seal authority requires lease_id")
    elif lease_id is not None:
        raise ValueError("lease_id is only valid for release_seal authority")
    issued = _timestamp(issued_at)
    expires = _timestamp(expires_at)
    if not timedelta(0) < _parse(expires) - _parse(issued) <= _MAX_LIFETIME:
        raise ValueError("recovery authorization lifetime must be positive and at most one hour")
    fields: dict[str, object] = {
        "schema_version": "antiek.chapter-tts-recovery.v2",
        "operator_id": operator_id,
        "execution_id": execution_id,
        "action": action,
        "lease_id": lease_id,
        "issued_at": issued,
        "expires_at": expires,
    }
    authorization_id = "mmttsrec_" + hashlib.sha256(_canonical(fields)).hexdigest()
    signed = {**fields, "authorization_id": authorization_id}
    return ChapterTTSRecoveryAuthorization(
        schema_version="antiek.chapter-tts-recovery.v2",
        authorization_id=authorization_id,
        operator_id=operator_id,
        execution_id=execution_id,
        action=action,
        lease_id=lease_id,
        issued_at=issued,
        expires_at=expires,
        signature=hmac.new(recovery_key, _canonical(signed), hashlib.sha256).hexdigest(),
    )


def quarantine_stale_send(
    *,
    authority: ChapterTTSRecoveryAuthorization,
    recovery_key: bytes,
    operator_id: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    db_path: str,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSAttempt:
    _verify(
        authority,
        recovery_key=recovery_key,
        operator_id=operator_id,
        action="quarantine_send",
        now=now,
    )
    execution_id = _execution_id(authorization)
    if authority.execution_id != execution_id:
        raise ChapterTTSReconciliationError("recovery authority belongs to another execution")
    return quarantine_stale_chapter_tts_send(
        db_path=db_path,
        authorization=authorization,
        signing_key=signing_key,
        now=now,
        stale_after=stale_after,
    )


def recover_unknown_send(
    *,
    authority: ChapterTTSRecoveryAuthorization,
    recovery_key: bytes,
    operator_id: str,
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
) -> ChapterTTSAttempt:
    _verify(
        authority,
        recovery_key=recovery_key,
        operator_id=operator_id,
        action="recover_unknown",
        now=verified_at or recorded_at,
    )
    return recover_unknown_chapter_tts_audio(
        db_path=db_path,
        execution_id=authority.execution_id,
        signing_key=signing_key,
        output_dir=output_dir,
        provider_request_id=provider_request_id,
        audio_bytes=audio_bytes,
        evidence_source=evidence_source,
        evidence_verification_key=evidence_verification_key,
        external_signature=external_signature,
        recorded_at=recorded_at,
        verified_at=verified_at,
    )


def release_stale_seal(
    *,
    authority: ChapterTTSRecoveryAuthorization,
    recovery_key: bytes,
    operator_id: str,
    signing_key: bytes,
    db_path: str,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSAttempt:
    _verify(
        authority,
        recovery_key=recovery_key,
        operator_id=operator_id,
        action="release_seal",
        now=now,
    )
    if authority.lease_id is None:
        raise ChapterTTSReconciliationError("seal recovery authority has no lease")
    return release_stale_chapter_tts_seal(
        db_path=db_path,
        execution_id=authority.execution_id,
        signing_key=signing_key,
        lease_id=authority.lease_id,
        now=now,
        stale_after=stale_after,
    )


def sign_provider_recovery_evidence(
    *,
    evidence_key: bytes,
    execution_id: str,
    provider_request_id: str,
    evidence_source: str,
    audio_bytes: bytes,
    recorded_at: datetime,
) -> str:
    """Create the exact external signature expected by provider recovery."""
    _key(evidence_key)
    payload = json.dumps(
        [
            _identifier("execution_id", execution_id),
            _identifier("provider_request_id", provider_request_id),
            _identifier("evidence_source", evidence_source),
            hashlib.sha256(audio_bytes).hexdigest(),
            _timestamp(recorded_at),
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hmac.new(evidence_key, payload, hashlib.sha256).hexdigest()


def _verify(
    authority: ChapterTTSRecoveryAuthorization,
    *,
    recovery_key: bytes,
    operator_id: str,
    action: RecoveryAction,
    now: datetime,
) -> None:
    _key(recovery_key)
    expected = issue_chapter_tts_recovery_authorization(
        recovery_key=recovery_key,
        operator_id=authority.operator_id,
        execution_id=authority.execution_id,
        action=authority.action,
        lease_id=authority.lease_id,
        issued_at=_parse(authority.issued_at),
        expires_at=_parse(authority.expires_at),
    )
    if (
        authority.schema_version != expected.schema_version
        or not hmac.compare_digest(authority.authorization_id, expected.authorization_id)
        or not hmac.compare_digest(authority.signature, expected.signature)
    ):
        raise ChapterTTSReconciliationError("chapter TTS recovery signature is invalid")
    if authority.operator_id != _identifier("operator_id", operator_id):
        raise ChapterTTSReconciliationError("chapter TTS recovery operator mismatch")
    if authority.action != action:
        raise ChapterTTSReconciliationError("chapter TTS recovery action mismatch")
    checked = _parse(_timestamp(now))
    if checked < _parse(authority.issued_at) or checked >= _parse(authority.expires_at):
        raise ChapterTTSReconciliationError("chapter TTS recovery authority is not active")


def _execution_id(authorization: MultimediaExecutionAuthorizationV2) -> str:
    return (
        "mmexec_"
        + hashlib.sha256(
            f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
        ).hexdigest()
    )


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def _identifier(field: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _key(value: bytes) -> None:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("recovery key must contain at least 32 bytes")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ChapterTTSReconciliationError("recovery timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or _timestamp(parsed) != value:
        raise ChapterTTSReconciliationError("recovery timestamp is not canonical UTC")
    return parsed


__all__ = [
    "ChapterTTSReconciliationError",
    "ChapterTTSRecoveryAuthorization",
    "issue_chapter_tts_recovery_authorization",
    "quarantine_stale_send",
    "recover_unknown_send",
    "release_stale_seal",
    "sign_provider_recovery_evidence",
]

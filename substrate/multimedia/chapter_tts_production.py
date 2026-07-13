"""Deterministic authority boundary for synchronous chapter TTS production.

The paid execution state machine is built on the request produced here. Keeping
request preparation pure makes it possible to quote, approve, and sign the exact
provider call before any budget claim or network-capable callback is reachable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from runtime.db_lock import FlockWriteCoordinator, WriteContext
from substrate.contracts.multimedia import GeneratedFile
from substrate.midnight_oil.budget_ledger import BudgetLedger, CallHold

from .audio_assembly import ChapterAudio
from .execution_authorization import (
    MultimediaExecutionAuthorizationV2,
    verify_async_execution_authorization,
)
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .narration import NarrationParagraph, normalize_script
from .narration_production import NarrationProductionArtifact, produce_narration_track
from .planner import MultimediaPlan
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    begin_reserved_provider_submission,
    bind_provider_job_with_mutation,
    charge_and_mark_submission_unknown,
    get_provider_execution,
    record_external_recovery_evidence,
    record_provider_observation,
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_TEXT_BYTES = 256 * 1024
_MAX_AUDIO_BYTES = 64 * 1024 * 1024


class ChapterTTSProductionError(RuntimeError):
    """A durable TTS attempt cannot safely continue automatically."""


@dataclass(frozen=True)
class ChapterTTSSynthesisResult:
    audio_bytes: bytes
    provider_request_id: str


@dataclass(frozen=True)
class ChapterTTSAttempt:
    execution_id: str
    hold_id: str
    request_body_digest: str
    status: str
    send_started_at: str | None
    provider_request_id: str | None
    raw_path: str | None
    raw_sha256: str | None
    artifact_json: str | None
    attempt_mac: str


@dataclass(frozen=True)
class ChapterTTSSealLease:
    execution_id: str
    lease_id: str
    acquired_at: str
    state: str
    resolved_at: str | None
    lease_mac: str


_ATTEMPT_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_chapter_tts_attempts (
    execution_id TEXT PRIMARY KEY,
    hold_id TEXT NOT NULL UNIQUE,
    request_body_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    send_started_at TEXT,
    provider_request_id TEXT,
    raw_path TEXT,
    raw_sha256 TEXT,
    artifact_json TEXT,
    attempt_mac TEXT NOT NULL
)
"""

_SEAL_LEASE_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_chapter_tts_seal_leases (
    execution_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL UNIQUE,
    acquired_at TEXT NOT NULL,
    state TEXT NOT NULL,
    resolved_at TEXT,
    lease_mac TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class PreparedChapterTTSRequest:
    """The canonical, provider-independent body authorized for one TTS call."""

    schema_version: Literal["antiek.chapter-tts-request.v1"]
    asset_id: str
    revision_id: str
    chapter_id: str
    title: str
    route_policy: str
    provider: str
    model: str
    endpoint_capability: Literal["text-to-speech"]
    voice: str
    speed: float
    sample_rate_hz: int
    channels: Literal[1, 2]
    text: str
    script_line_ids: tuple[str, ...]
    paragraph_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]

    @property
    def body_json(self) -> str:
        return json.dumps(
            {
                "asset_id": self.asset_id,
                "channels": self.channels,
                "chapter_id": self.chapter_id,
                "endpoint_capability": self.endpoint_capability,
                "model": self.model,
                "paragraph_ids": list(self.paragraph_ids),
                "provider": self.provider,
                "revision_id": self.revision_id,
                "route_policy": self.route_policy,
                "sample_rate_hz": self.sample_rate_hz,
                "schema_version": self.schema_version,
                "script_line_ids": list(self.script_line_ids),
                "source_chunk_ids": list(self.source_chunk_ids),
                "speed": self.speed,
                "text": self.text,
                "title": self.title,
                "voice": self.voice,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @property
    def body_digest(self) -> str:
        return hashlib.sha256(self.body_json.encode("ascii")).hexdigest()


def prepare_chapter_tts_request(
    plan: MultimediaPlan,
    *,
    asset_id: str,
    revision_id: str,
    provider: str,
    model: str,
    chapter_id: str | None = None,
    voice: str = "narrator",
    speed: float = 1.0,
    sample_rate_hz: int = 24_000,
    channels: Literal[1, 2] = 1,
) -> PreparedChapterTTSRequest:
    """Prepare exactly one spoken chapter or fail before paid execution.

    A multi-chapter plan is rejected in v1 because sequential synchronous calls
    cannot be made crash-safe without a parent authorization-set receipt.
    """
    asset_id = _identifier("asset_id", asset_id)
    revision_id = _identifier("revision_id", revision_id)
    provider = _identifier("provider", provider)
    model = _identifier("model", model)
    voice = _identifier("voice", voice)
    if not math.isfinite(speed) or speed < 0.25 or speed > 4:
        raise ValueError("speed must be finite and in [0.25, 4]")
    if not 8_000 <= sample_rate_hz <= 48_000 or channels not in {1, 2}:
        raise ValueError("chapter TTS audio shape is invalid")

    chapter_ids = {chapter.chapter_id for chapter in plan.chapters}
    paragraphs = normalize_script(
        tuple(
            line for line in plan.script_lines if line.line_id.split("-line-", 1)[0] in chapter_ids
        )
    )
    grouped: dict[str, list[NarrationParagraph]] = {}
    for paragraph in paragraphs:
        grouped.setdefault(paragraph.line_id.split("-line-", 1)[0], []).append(paragraph)
    spoken = tuple(chapter for chapter in plan.chapters if grouped.get(chapter.chapter_id))
    if chapter_id is None:
        if len(spoken) != 1:
            raise ValueError("chapter TTS v1 requires exactly one non-empty spoken chapter")
        chapter = spoken[0]
    else:
        chapter_id = _identifier("chapter_id", chapter_id)
        selected = tuple(chapter for chapter in spoken if chapter.chapter_id == chapter_id)
        if len(selected) != 1:
            raise ValueError("chapter_id is not exactly one non-empty spoken chapter")
        chapter = selected[0]
    rows = grouped[chapter.chapter_id]
    text = " ".join(str(row.text) for row in rows)
    if not text or len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError("chapter TTS text is empty or exceeds its byte ceiling")
    source_ids = tuple(
        dict.fromkeys(
            (
                *(chunk for row in rows for chunk in row.source_chunk_ids),
                *chapter.source_chunk_ids,
            )
        )
    )
    return PreparedChapterTTSRequest(
        schema_version="antiek.chapter-tts-request.v1",
        asset_id=asset_id,
        revision_id=revision_id,
        chapter_id=_identifier("chapter_id", chapter.chapter_id),
        title=chapter.title,
        route_policy=plan.request.route_policy,
        provider=provider,
        model=model,
        endpoint_capability="text-to-speech",
        voice=voice,
        speed=round(float(speed), 3),
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        text=text,
        script_line_ids=tuple(str(row.line_id) for row in rows),
        paragraph_ids=tuple(str(row.para_id) for row in rows),
        source_chunk_ids=source_ids,
    )


def verify_chapter_tts_authorization(
    authorization: MultimediaExecutionAuthorizationV2,
    prepared: PreparedChapterTTSRequest,
    *,
    signing_key: bytes,
    operator_id: str,
    catalog_version: str,
    catalog_digest: str,
    quote_id: str,
    recovery_authority_id: str,
    recovery_verification_key_digest: str,
    approved_ceiling_microdollars: int,
    now: datetime,
) -> None:
    """Verify the signature and every execution-time binding against the body."""
    verify_async_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=operator_id,
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        provider=prepared.provider,
        route_policy=prepared.route_policy,
        model=prepared.model,
        endpoint_capability=prepared.endpoint_capability,
        catalog_version=catalog_version,
        catalog_digest=catalog_digest,
        quote_id=quote_id,
        recovery_authority_id=recovery_authority_id,
        recovery_verification_key_digest=recovery_verification_key_digest,
        approved_ceiling_microdollars=approved_ceiling_microdollars,
        request_body_digest=prepared.body_digest,
        now=now,
    )


def produce_chapter_narration(
    *,
    plan: MultimediaPlan,
    prepared: PreparedChapterTTSRequest,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    integrity_key: bytes,
    operator_id: str,
    catalog_version: str,
    catalog_digest: str,
    quote_id: str,
    recovery_authority_id: str,
    recovery_verification_key_digest: str,
    approved_ceiling_microdollars: int,
    db_path: str,
    output_dir: str,
    now: datetime,
    synthesize: Callable[[PreparedChapterTTSRequest], ChapterTTSSynthesisResult],
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    timeout_seconds: int = 300,
) -> NarrationProductionArtifact:
    """Execute one authorized synchronous TTS call and seal its narration.

    The provider callback runs only after a durable send marker. A returned
    provider request ID and raw bytes are persisted before local rendering, so
    rendering can resume without repeating paid synthesis.
    """
    expected = prepare_chapter_tts_request(
        plan,
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        provider=prepared.provider,
        model=prepared.model,
        chapter_id=prepared.chapter_id,
        voice=prepared.voice,
        speed=prepared.speed,
        sample_rate_hz=prepared.sample_rate_hz,
        channels=prepared.channels,
    )
    if expected != prepared:
        raise ValueError("prepared chapter TTS request conflicts with plan")
    verify_chapter_tts_authorization(
        authorization,
        prepared,
        signing_key=signing_key,
        operator_id=operator_id,
        catalog_version=catalog_version,
        catalog_digest=catalog_digest,
        quote_id=quote_id,
        recovery_authority_id=recovery_authority_id,
        recovery_verification_key_digest=recovery_verification_key_digest,
        approved_ceiling_microdollars=approved_ceiling_microdollars,
        now=now,
    )
    root = _private_directory(output_dir)
    existing = _attempt_for_authorization(db_path, authorization, signing_key)
    if existing is not None and existing.status == "sealed":
        return _reopen_attempt(existing, prepared, integrity_key)
    if existing is not None and existing.status == "received":
        return _seal_received(
            attempt=existing,
            prepared=prepared,
            signing_key=signing_key,
            integrity_key=integrity_key,
            db_path=db_path,
            output_dir=str(root),
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            timeout_seconds=timeout_seconds,
            now=now,
        )
    if existing is not None and existing.status in {"sending", "sealing", "outcome_unknown"}:
        raise ChapterTTSProductionError(
            f"chapter TTS attempt is {existing.status}; automatic retry is forbidden"
        )

    try:
        execution, hold = begin_reserved_provider_submission(
            db_path=db_path,
            authorization=authorization,
            signing_key=signing_key,
            now=now,
            mutation=lambda ctx, record, reserved: _ensure_attempt(
                ctx, record.execution_id, reserved, prepared, signing_key
            ),
        )
    except RuntimeError as exc:
        raced = _attempt_for_authorization(db_path, authorization, signing_key)
        if raced is None:
            raise
        if raced.status == "sealed":
            return _reopen_attempt(raced, prepared, integrity_key)
        if raced.status == "received":
            return _seal_received(
                attempt=raced,
                prepared=prepared,
                signing_key=signing_key,
                integrity_key=integrity_key,
                db_path=db_path,
                output_dir=str(root),
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                timeout_seconds=timeout_seconds,
                now=now,
            )
        raise ChapterTTSProductionError("chapter TTS send is already in flight") from exc
    attempt = get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution.execution_id, signing_key=signing_key
    )
    if attempt.status == "sealed":
        return _reopen_attempt(attempt, prepared, integrity_key)
    if attempt.status == "received":
        return _seal_received(
            attempt=attempt,
            prepared=prepared,
            signing_key=signing_key,
            integrity_key=integrity_key,
            db_path=db_path,
            output_dir=str(root),
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            timeout_seconds=timeout_seconds,
            now=now,
        )
    if not _mark_send_started(db_path, execution.execution_id, signing_key, now):
        raise ChapterTTSProductionError("chapter TTS send is already in flight")

    try:
        result = synthesize(prepared)
        _validate_synthesis_result(result, authorization)
        raw_path, raw_sha = _persist_raw(root, execution.execution_id, result.audio_bytes)
    except Exception:
        charge_and_mark_submission_unknown(
            db_path=db_path,
            execution_id=execution.execution_id,
            hold=hold,
            signing_key=signing_key,
            now=now,
        )
        _mark_unknown(db_path, execution.execution_id, signing_key)
        raise

    actual_cents = (authorization.approved_ceiling_microdollars + 9_999) // 10_000
    try:
        bind_provider_job_with_mutation(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id=result.provider_request_id,
            signing_key=signing_key,
            now=now,
            mutation=lambda ctx: _receive_in_context(
                ctx,
                execution_id=execution.execution_id,
                provider_request_id=result.provider_request_id,
                raw_path=raw_path,
                raw_sha256=raw_sha,
                hold=hold,
                actual_cents=actual_cents,
                signing_key=signing_key,
            ),
        )
    except Exception:
        charge_and_mark_submission_unknown(
            db_path=db_path,
            execution_id=execution.execution_id,
            hold=hold,
            signing_key=signing_key,
            now=now,
        )
        _mark_unknown(db_path, execution.execution_id, signing_key)
        raise
    record_provider_observation(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id=result.provider_request_id,
        status=ProviderExecutionStatus.SUCCEEDED,
        evidence_digest=raw_sha,
        signing_key=signing_key,
        observed_at=now,
    )
    received = get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution.execution_id, signing_key=signing_key
    )
    if received.status == "sealed":
        return _reopen_attempt(received, prepared, integrity_key)
    if received.status == "sealing":
        raise ChapterTTSProductionError("chapter TTS seal is already in flight")
    return _seal_received(
        attempt=received,
        prepared=prepared,
        signing_key=signing_key,
        integrity_key=integrity_key,
        db_path=db_path,
        output_dir=str(root),
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        timeout_seconds=timeout_seconds,
        now=now,
    )


def get_chapter_tts_attempt(
    *, db_path: str, execution_id: str, signing_key: bytes
) -> ChapterTTSAttempt:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.read") as connection:
        connection.execute(_ATTEMPT_DDL)
        row = connection.execute(
            "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
    if row is None:
        raise ProviderExecutionIntegrityError("chapter TTS attempt does not exist")
    return _attempt(row, signing_key)


def quarantine_stale_chapter_tts_send(
    *,
    db_path: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSAttempt:
    """Charge and quarantine a stale send marker without provider retry."""
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    execution_id = (
        "mmexec_"
        + hashlib.sha256(
            f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
        ).hexdigest()
    )
    attempt = get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    if attempt.status == "outcome_unknown":
        return attempt
    if attempt.status != "sending" or attempt.send_started_at is None:
        raise ChapterTTSProductionError("chapter TTS attempt has no stale send to quarantine")
    started = datetime.fromisoformat(attempt.send_started_at.replace("Z", "+00:00"))
    if now.astimezone(UTC) - started < stale_after:
        raise ChapterTTSProductionError("chapter TTS send marker is not stale")
    ceiling_cents = (authorization.approved_ceiling_microdollars + 9_999) // 10_000
    hold = CallHold(
        hold_id=attempt.hold_id,
        run_id=authorization.authorization_id,
        role=f"multimedia:{authorization.provider}",
        projected_max_cents=ceiling_cents,
    )
    charge_and_mark_submission_unknown(
        db_path=db_path,
        execution_id=execution_id,
        hold=hold,
        signing_key=signing_key,
        now=now,
    )
    _mark_unknown(db_path, execution_id, signing_key)
    return get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )


def recover_unknown_chapter_tts_audio(
    *,
    db_path: str,
    execution_id: str,
    signing_key: bytes,
    output_dir: str,
    provider_request_id: str,
    audio_bytes: bytes,
    evidence_source: str,
    evidence_verification_key: bytes,
    external_signature: str,
    recorded_at: datetime,
    verified_at: datetime | None = None,
) -> ChapterTTSAttempt:
    """Bind authenticated provider recovery evidence and returned audio bytes."""
    transition_at = verified_at or recorded_at
    attempt = get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    if attempt.status == "received":
        expected_digest = hashlib.sha256(audio_bytes).hexdigest()
        if (
            attempt.provider_request_id != provider_request_id
            or attempt.raw_path is None
            or attempt.raw_sha256 != expected_digest
            or _hash_private_file(Path(attempt.raw_path)) != expected_digest
        ):
            raise ChapterTTSProductionError("recovered chapter TTS receipt conflicts")
        execution = get_provider_execution(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
        if execution.status is ProviderExecutionStatus.SUBMITTED:
            record_provider_observation(
                db_path=db_path,
                execution_id=execution_id,
                provider_job_id=provider_request_id,
                status=ProviderExecutionStatus.SUCCEEDED,
                evidence_digest=expected_digest,
                signing_key=signing_key,
                observed_at=transition_at,
            )
        elif execution.status is not ProviderExecutionStatus.SUCCEEDED:
            raise ChapterTTSProductionError("recovered provider execution state conflicts")
        return attempt
    if attempt.status != "outcome_unknown":
        raise ChapterTTSProductionError("chapter TTS recovery requires outcome_unknown")
    result = ChapterTTSSynthesisResult(
        audio_bytes=audio_bytes, provider_request_id=provider_request_id
    )
    if not 0 < len(result.audio_bytes) <= _MAX_AUDIO_BYTES:
        raise ValueError("recovered TTS bytes are empty or exceed the byte ceiling")
    evidence_digest = hashlib.sha256(audio_bytes).hexdigest()
    record_external_recovery_evidence(
        db_path=db_path,
        execution_id=execution_id,
        provider_job_id=provider_request_id,
        source=evidence_source,
        evidence_digest=evidence_digest,
        signing_key=signing_key,
        evidence_verification_key=evidence_verification_key,
        external_signature=external_signature,
        recorded_at=recorded_at,
        verified_at=verified_at,
    )
    raw_path, raw_sha = _persist_raw(_private_directory(output_dir), execution_id, audio_bytes)
    bind_provider_job_with_mutation(
        db_path=db_path,
        execution_id=execution_id,
        provider_job_id=provider_request_id,
        signing_key=signing_key,
        now=transition_at,
        mutation=lambda ctx: _recover_received_in_context(
            ctx,
            execution_id=execution_id,
            provider_request_id=provider_request_id,
            raw_path=raw_path,
            raw_sha256=raw_sha,
            signing_key=signing_key,
        ),
    )
    record_provider_observation(
        db_path=db_path,
        execution_id=execution_id,
        provider_job_id=provider_request_id,
        status=ProviderExecutionStatus.SUCCEEDED,
        evidence_digest=raw_sha,
        signing_key=signing_key,
        observed_at=transition_at,
    )
    return get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )


def release_stale_chapter_tts_seal(
    *,
    db_path: str,
    execution_id: str,
    signing_key: bytes,
    lease_id: str,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=5),
) -> ChapterTTSAttempt:
    """Reset a local-only sealing claim to received; never touches provider spend."""
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    attempt = get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    lease = get_chapter_tts_seal_lease(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )
    checked_at = datetime.fromisoformat(_timestamp(now).replace("Z", "+00:00"))
    acquired_at = datetime.fromisoformat(lease.acquired_at.replace("Z", "+00:00"))
    if (
        attempt.status != "sealing"
        or lease.state != "active"
        or lease.lease_id != lease_id
        or checked_at < acquired_at
        or checked_at - acquired_at < stale_after
        or attempt.raw_path is None
        or attempt.raw_sha256 is None
        or _hash_private_file(Path(attempt.raw_path)) != attempt.raw_sha256
    ):
        raise ChapterTTSProductionError("stale seal has no valid durable received bytes")
    _release_seal(
        db_path, execution_id, signing_key, lease_id=lease.lease_id, resolved_at=now
    )
    return get_chapter_tts_attempt(
        db_path=db_path, execution_id=execution_id, signing_key=signing_key
    )


def get_chapter_tts_seal_lease(
    *, db_path: str, execution_id: str, signing_key: bytes
) -> ChapterTTSSealLease:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.seal_lease.read") as ctx:
        ctx.execute(_SEAL_LEASE_DDL)
        row = ctx.execute(
            "SELECT * FROM multimedia_chapter_tts_seal_leases WHERE execution_id=?",
            [execution_id],
        ).fetchone()
    if row is None:
        raise ProviderExecutionIntegrityError("chapter TTS seal lease does not exist")
    return _seal_lease(row, signing_key)


def _ensure_attempt(
    ctx: WriteContext,
    execution_id: str,
    hold: CallHold,
    prepared: PreparedChapterTTSRequest,
    signing_key: bytes,
) -> None:
    ctx.execute(_ATTEMPT_DDL)
    row = ctx.execute(
        "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is not None:
        current = _attempt(row, signing_key)
        if current.hold_id != hold.hold_id or current.request_body_digest != prepared.body_digest:
            raise ProviderExecutionIntegrityError("chapter TTS attempt conflicts")
        return
    values: list[object] = [
        execution_id,
        hold.hold_id,
        prepared.body_digest,
        "intent",
        None,
        None,
        None,
        None,
        None,
    ]
    ctx.execute(
        "INSERT INTO multimedia_chapter_tts_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [*values, _attempt_mac(values, signing_key)],
    )


def _mark_send_started(db_path: str, execution_id: str, signing_key: bytes, now: datetime) -> bool:
    timestamp = _timestamp(now)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.send") as ctx:
        row = ctx.execute(
            "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
        if row is None:
            raise ProviderExecutionIntegrityError("chapter TTS attempt disappeared")
        current = _attempt(row, signing_key)
        if current.status != "intent" or current.send_started_at is not None:
            return False
        values: list[object] = [*row[:3], "sending", timestamp, *row[5:9]]
        hit = ctx.execute(
            "UPDATE multimedia_chapter_tts_attempts SET status='sending', send_started_at=?, "
            "attempt_mac=? WHERE execution_id=? AND status='intent' RETURNING 1",
            [timestamp, _attempt_mac(values, signing_key), execution_id],
        ).fetchone()
        return hit is not None


def _receive_in_context(
    ctx: WriteContext,
    *,
    execution_id: str,
    provider_request_id: str,
    raw_path: str,
    raw_sha256: str,
    hold: CallHold,
    actual_cents: int,
    signing_key: bytes,
) -> None:
    row = ctx.execute(
        "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is None or _attempt(row, signing_key).status != "sending":
        raise ProviderExecutionIntegrityError("chapter TTS receive state is invalid")
    BudgetLedger(":memory:").settle_in_context(ctx, hold_id=hold.hold_id, actual_cents=actual_cents)
    values: list[object] = [
        *row[:3],
        "received",
        row[4],
        provider_request_id,
        raw_path,
        raw_sha256,
        None,
    ]
    ctx.execute(
        "UPDATE multimedia_chapter_tts_attempts SET status='received', provider_request_id=?, "
        "raw_path=?, raw_sha256=?, attempt_mac=? WHERE execution_id=?",
        [
            provider_request_id,
            raw_path,
            raw_sha256,
            _attempt_mac(values, signing_key),
            execution_id,
        ],
    )


def _recover_received_in_context(
    ctx: WriteContext,
    *,
    execution_id: str,
    provider_request_id: str,
    raw_path: str,
    raw_sha256: str,
    signing_key: bytes,
) -> None:
    row = ctx.execute(
        "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
        [execution_id],
    ).fetchone()
    if row is None or _attempt(row, signing_key).status != "outcome_unknown":
        raise ProviderExecutionIntegrityError("chapter TTS recovered receive state is invalid")
    values: list[object] = [
        *row[:3],
        "received",
        row[4],
        provider_request_id,
        raw_path,
        raw_sha256,
        None,
    ]
    ctx.execute(
        "UPDATE multimedia_chapter_tts_attempts SET status='received', provider_request_id=?, "
        "raw_path=?, raw_sha256=?, attempt_mac=? WHERE execution_id=?",
        [
            provider_request_id,
            raw_path,
            raw_sha256,
            _attempt_mac(values, signing_key),
            execution_id,
        ],
    )


def _mark_unknown(db_path: str, execution_id: str, signing_key: bytes) -> None:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.unknown") as ctx:
        row = ctx.execute(
            "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
            [execution_id],
        ).fetchone()
        if row is None:
            return
        _attempt(row, signing_key)
        values: list[object] = [*row[:3], "outcome_unknown", *row[4:9]]
        ctx.execute(
            "UPDATE multimedia_chapter_tts_attempts SET status='outcome_unknown', attempt_mac=? "
            "WHERE execution_id=?",
            [_attempt_mac(values, signing_key), execution_id],
        )


def _seal_received(
    *,
    attempt: ChapterTTSAttempt,
    prepared: PreparedChapterTTSRequest,
    signing_key: bytes,
    integrity_key: bytes,
    db_path: str,
    output_dir: str,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout_seconds: int,
    now: datetime,
) -> NarrationProductionArtifact:
    if attempt.status != "received" or attempt.raw_path is None or attempt.raw_sha256 is None:
        raise ChapterTTSProductionError("chapter TTS has no durable received audio")
    raw = Path(attempt.raw_path)
    if _hash_private_file(raw) != attempt.raw_sha256:
        raise ChapterTTSProductionError("chapter TTS raw audio digest is invalid")
    lease = _claim_seal(db_path, attempt.execution_id, signing_key, acquired_at=now)
    if lease is None:
        raise ChapterTTSProductionError("chapter TTS seal is already in flight")
    staging = Path(tempfile.mkdtemp(prefix=".tts-normalize-", dir=output_dir))
    try:
        os.chmod(staging, 0o700)
        wav = staging / "chapter.wav"
        _run(
            [
                _executable(ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(raw),
                "-ar",
                str(prepared.sample_rate_hz),
                "-ac",
                str(prepared.channels),
                "-c:a",
                "pcm_s16le",
                str(wav),
            ],
            timeout_seconds,
        )
        os.chmod(wav, 0o600)
        duration = _probe_duration(_executable(ffprobe_path), wav, timeout_seconds)
        durable_wav = Path(attempt.raw_path).with_name(
            f"{Path(attempt.raw_path).stem}.{lease.lease_id}.wav"
        )
        os.replace(wav, durable_wav)
        os.chmod(durable_wav, 0o600)
        wav = durable_wav
        audio_id = f"audio-{prepared.chapter_id}"
        chapter = ChapterAudio(
            chapter_id=prepared.chapter_id,
            title=prepared.title,
            sequence=0,
            audio_file_id=audio_id,
            duration_seconds=duration,
            start_offset_seconds=0.0,
            script_line_ids=prepared.script_line_ids,
            source_chunk_ids=prepared.source_chunk_ids,
            paragraph_ids=prepared.paragraph_ids,
            recap_prompt="Recall the evidence.",
        )
        generated = GeneratedFile(
            file_id=audio_id,
            kind="audio",
            storage_uri=f"antiek-mm://{prepared.asset_id}/{prepared.revision_id}/{audio_id}.wav",
            sha256=_hash_private_file(wav),
            mime="audio/wav",
            provider=prepared.provider,
            duration_seconds=duration,
        )
        artifact = produce_narration_track(
            asset_id=prepared.asset_id,
            revision_id=prepared.revision_id,
            chapters=(chapter,),
            generated_files=(generated,),
            chapter_paths={audio_id: str(wav)},
            output_dir=output_dir,
            integrity_key=integrity_key,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            sample_rate_hz=prepared.sample_rate_hz,
            channels=prepared.channels,
            timeout_seconds=timeout_seconds,
            publication_id=lease.lease_id,
        )
    except Exception:
        _release_seal(
            db_path,
            attempt.execution_id,
            signing_key,
            lease_id=lease.lease_id,
            resolved_at=now,
        )
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    try:
        _mark_sealed(
            db_path,
            attempt.execution_id,
            artifact,
            signing_key,
            lease_id=lease.lease_id,
            resolved_at=now,
        )
    except Exception:
        shutil.rmtree(Path(artifact.manifest.output_path).parent, ignore_errors=True)
        durable_wav.unlink(missing_ok=True)
        raise
    return NarrationProductionArtifact.reopen(artifact.to_json(), integrity_key)


def _mark_sealed(
    db_path: str,
    execution_id: str,
    artifact: NarrationProductionArtifact,
    signing_key: bytes,
    lease_id: str,
    resolved_at: datetime,
) -> None:
    payload = artifact.to_json()
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.seal") as ctx:
        ctx.execute(_SEAL_LEASE_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            lease_row = ctx.execute(
                "SELECT * FROM multimedia_chapter_tts_seal_leases WHERE execution_id=?",
                [execution_id],
            ).fetchone()
            if lease_row is None:
                raise ProviderExecutionIntegrityError("chapter TTS seal lease is invalid")
            lease = _seal_lease(lease_row, signing_key)
            if lease.state != "active" or lease.lease_id != lease_id:
                raise ProviderExecutionIntegrityError("chapter TTS seal lease is invalid")
            timestamp = _timestamp(resolved_at)
            lease_values: list[object] = [
                lease.execution_id, lease.lease_id, lease.acquired_at, "sealed", timestamp
            ]
            ctx.execute(
                "UPDATE multimedia_chapter_tts_seal_leases SET state='sealed', resolved_at=?, "
                "lease_mac=? WHERE execution_id=? AND lease_id=? AND state='active'",
                [
                    timestamp,
                    _seal_lease_mac(lease_values, signing_key),
                    execution_id,
                    lease_id,
                ],
            )
            row = ctx.execute(
                "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if row is None or _attempt(row, signing_key).status != "sealing":
                raise ProviderExecutionIntegrityError("chapter TTS seal state is invalid")
            values: list[object] = [*row[:3], "sealed", *row[4:8], payload]
            ctx.execute(
                "UPDATE multimedia_chapter_tts_attempts SET status='sealed', artifact_json=?, "
                "attempt_mac=? WHERE execution_id=?",
                [payload, _attempt_mac(values, signing_key), execution_id],
            )
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")


def _claim_seal(
    db_path: str, execution_id: str, signing_key: bytes, *, acquired_at: datetime
) -> ChapterTTSSealLease | None:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.claim_seal") as ctx:
        ctx.execute(_SEAL_LEASE_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            row = ctx.execute(
                "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if row is None:
                raise ProviderExecutionIntegrityError("chapter TTS attempt disappeared")
            current = _attempt(row, signing_key)
            if current.status != "received":
                ctx.execute("ROLLBACK")
                return None
            timestamp = _timestamp(acquired_at)
            existing = ctx.execute(
                "SELECT * FROM multimedia_chapter_tts_seal_leases WHERE execution_id=?",
                [execution_id],
            ).fetchone()
            if existing is not None:
                lease = _seal_lease(existing, signing_key)
                if lease.state == "active":
                    raise ProviderExecutionIntegrityError("chapter TTS seal lease is active")
            prior_lease_id = "initial" if existing is None else lease.lease_id
            lease_id = "mmttslease_" + hashlib.sha256(
                f"{execution_id}:{timestamp}:{prior_lease_id}".encode("ascii")
            ).hexdigest()
            lease_values: list[object] = [execution_id, lease_id, timestamp, "active", None]
            lease_mac = _seal_lease_mac(lease_values, signing_key)
            if existing is None:
                ctx.execute(
                    "INSERT INTO multimedia_chapter_tts_seal_leases VALUES (?, ?, ?, ?, ?, ?)",
                    [*lease_values, lease_mac],
                )
            else:
                ctx.execute(
                    "UPDATE multimedia_chapter_tts_seal_leases SET lease_id=?, acquired_at=?, "
                    "state='active', resolved_at=NULL, lease_mac=? WHERE execution_id=?",
                    [lease_id, timestamp, lease_mac, execution_id],
                )
            values: list[object] = [*row[:3], "sealing", *row[4:9]]
            hit = ctx.execute(
                "UPDATE multimedia_chapter_tts_attempts SET status='sealing', attempt_mac=? "
                "WHERE execution_id=? AND status='received' RETURNING 1",
                [_attempt_mac(values, signing_key), execution_id],
            ).fetchone()
            if hit is None:
                raise ProviderExecutionIntegrityError("chapter TTS seal claim raced")
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return ChapterTTSSealLease(
                execution_id=execution_id,
                lease_id=lease_id,
                acquired_at=timestamp,
                state="active",
                resolved_at=None,
                lease_mac=lease_mac,
            )


def _release_seal(
    db_path: str,
    execution_id: str,
    signing_key: bytes,
    *,
    lease_id: str,
    resolved_at: datetime,
) -> None:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.chapter_tts.release_seal") as ctx:
        ctx.execute(_SEAL_LEASE_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            lease_row = ctx.execute(
                "SELECT * FROM multimedia_chapter_tts_seal_leases WHERE execution_id=?",
                [execution_id],
            ).fetchone()
            if lease_row is None:
                raise ProviderExecutionIntegrityError("chapter TTS seal lease is invalid")
            lease = _seal_lease(lease_row, signing_key)
            if lease.state != "active" or lease.lease_id != lease_id:
                raise ProviderExecutionIntegrityError("chapter TTS seal lease is invalid")
            row = ctx.execute(
                "SELECT * FROM multimedia_chapter_tts_attempts WHERE execution_id = ?",
                [execution_id],
            ).fetchone()
            if row is None:
                raise ProviderExecutionIntegrityError("chapter TTS attempt disappeared")
            current = _attempt(row, signing_key)
            if current.status != "sealing":
                raise ProviderExecutionIntegrityError("chapter TTS seal release state is invalid")
            values: list[object] = [*row[:3], "received", *row[4:9]]
            ctx.execute(
                "UPDATE multimedia_chapter_tts_attempts SET status='received', attempt_mac=? "
                "WHERE execution_id=? AND status='sealing'",
                [_attempt_mac(values, signing_key), execution_id],
            )
            timestamp = _timestamp(resolved_at)
            lease_values: list[object] = [
                lease.execution_id, lease.lease_id, lease.acquired_at, "released", timestamp
            ]
            ctx.execute(
                "UPDATE multimedia_chapter_tts_seal_leases SET state='released', resolved_at=?, "
                "lease_mac=? WHERE execution_id=? AND lease_id=? AND state='active'",
                [
                    timestamp,
                    _seal_lease_mac(lease_values, signing_key),
                    execution_id,
                    lease_id,
                ],
            )
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")


def _attempt_for_authorization(
    db_path: str,
    authorization: MultimediaExecutionAuthorizationV2,
    signing_key: bytes,
) -> ChapterTTSAttempt | None:
    if not Path(db_path).exists():
        return None
    execution_id = (
        "mmexec_"
        + hashlib.sha256(
            f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
        ).hexdigest()
    )
    try:
        return get_chapter_tts_attempt(
            db_path=db_path, execution_id=execution_id, signing_key=signing_key
        )
    except ProviderExecutionIntegrityError as exc:
        if str(exc) == "chapter TTS attempt does not exist":
            return None
        raise


def _reopen_attempt(
    attempt: ChapterTTSAttempt,
    prepared: PreparedChapterTTSRequest,
    integrity_key: bytes,
) -> NarrationProductionArtifact:
    if attempt.artifact_json is None or attempt.request_body_digest != prepared.body_digest:
        raise ProviderExecutionIntegrityError("sealed chapter TTS attempt conflicts")
    artifact = NarrationProductionArtifact.reopen(attempt.artifact_json, integrity_key)
    if (
        artifact.manifest.asset_id != prepared.asset_id
        or artifact.manifest.revision_id != prepared.revision_id
        or tuple(row.chapter_id for row in artifact.manifest.sources) != (prepared.chapter_id,)
    ):
        raise ProviderExecutionIntegrityError("sealed chapter TTS artifact conflicts")
    return artifact


def _validate_synthesis_result(
    result: ChapterTTSSynthesisResult,
    authorization: MultimediaExecutionAuthorizationV2,
) -> None:
    if not isinstance(result, ChapterTTSSynthesisResult):
        raise TypeError("synthesize must return ChapterTTSSynthesisResult")
    if not 0 < len(result.audio_bytes) <= _MAX_AUDIO_BYTES:
        raise ValueError("TTS response bytes are empty or exceed the byte ceiling")
    _identifier("provider_request_id", result.provider_request_id)


def _persist_raw(root: Path, execution_id: str, payload: bytes) -> tuple[str, str]:
    receipt_root = root / ".chapter-tts-receipts"
    receipt_root.mkdir(mode=0o700, exist_ok=True)
    info = receipt_root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("chapter TTS receipt directory must be private")
    destination = receipt_root / f"{execution_id}.audio"
    expected = hashlib.sha256(payload).hexdigest()
    if destination.exists() or destination.is_symlink():
        if _hash_private_file(destination) != expected:
            raise ChapterTTSProductionError("persisted TTS response conflicts with recovered bytes")
        return str(destination), expected
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return str(destination), expected


def _attempt(row: tuple[object, ...], signing_key: bytes) -> ChapterTTSAttempt:
    if len(row) != 10 or not isinstance(row[9], str):
        raise ProviderExecutionIntegrityError("chapter TTS attempt shape is invalid")
    if not hmac.compare_digest(row[9], _attempt_mac(list(row[:9]), signing_key)):
        raise ProviderExecutionIntegrityError("chapter TTS attempt MAC is invalid")
    if row[3] not in {"intent", "sending", "received", "sealing", "sealed", "outcome_unknown"}:
        raise ProviderExecutionIntegrityError("chapter TTS attempt status is invalid")
    return ChapterTTSAttempt(
        execution_id=str(row[0]),
        hold_id=str(row[1]),
        request_body_digest=str(row[2]),
        status=str(row[3]),
        send_started_at=str(row[4]) if row[4] else None,
        provider_request_id=str(row[5]) if row[5] else None,
        raw_path=str(row[6]) if row[6] else None,
        raw_sha256=str(row[7]) if row[7] else None,
        artifact_json=str(row[8]) if row[8] else None,
        attempt_mac=row[9],
    )


def _attempt_mac(values: list[object], signing_key: bytes) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hmac.new(signing_key, payload, hashlib.sha256).hexdigest()


def _seal_lease(row: tuple[object, ...], signing_key: bytes) -> ChapterTTSSealLease:
    if len(row) != 6 or not isinstance(row[5], str):
        raise ProviderExecutionIntegrityError("chapter TTS seal lease shape is invalid")
    if not hmac.compare_digest(row[5], _seal_lease_mac(list(row[:5]), signing_key)):
        raise ProviderExecutionIntegrityError("chapter TTS seal lease MAC is invalid")
    if row[3] not in {"active", "released", "sealed"}:
        raise ProviderExecutionIntegrityError("chapter TTS seal lease state is invalid")
    acquired_at = _timestamp(datetime.fromisoformat(str(row[2]).replace("Z", "+00:00")))
    resolved_at = None
    if row[4] is not None:
        resolved_at = _timestamp(datetime.fromisoformat(str(row[4]).replace("Z", "+00:00")))
    if acquired_at != row[2] or (row[4] is not None and resolved_at != row[4]):
        raise ProviderExecutionIntegrityError("chapter TTS seal lease timestamp is invalid")
    if (row[3] == "active") != (resolved_at is None):
        raise ProviderExecutionIntegrityError("chapter TTS seal lease resolution is invalid")
    if resolved_at is not None and resolved_at < acquired_at:
        raise ProviderExecutionIntegrityError("chapter TTS seal lease chronology is invalid")
    return ChapterTTSSealLease(
        execution_id=str(row[0]),
        lease_id=str(row[1]),
        acquired_at=acquired_at,
        state=str(row[3]),
        resolved_at=resolved_at,
        lease_mac=row[5],
    )


def _seal_lease_mac(values: list[object], signing_key: bytes) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hmac.new(signing_key, payload, hashlib.sha256).hexdigest()


def _private_directory(value: str) -> Path:
    root = Path(value)
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("chapter TTS output directory must be private")
    return root.resolve()


def _executable(value: str) -> str:
    path = Path(value).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("chapter TTS media executable is invalid")
    return str(path)


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise ChapterTTSProductionError("chapter TTS media process failed") from None


def _probe_duration(ffprobe: str, path: Path, timeout: int) -> float:
    result = _run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        timeout,
    )
    try:
        duration = round(float(json.loads(result.stdout)["format"]["duration"]), 3)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ChapterTTSProductionError("chapter TTS probe is invalid") from None
    if not math.isfinite(duration) or duration <= 0:
        raise ChapterTTSProductionError("chapter TTS duration is invalid")
    return duration


def _hash_private_file(path: Path) -> str:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
        or not 0 < info.st_size <= _MAX_AUDIO_BYTES
    ):
        raise ChapterTTSProductionError("chapter TTS file is not private and bounded")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _identifier(field: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


__all__ = [
    "ChapterTTSAttempt",
    "ChapterTTSSealLease",
    "ChapterTTSProductionError",
    "ChapterTTSSynthesisResult",
    "PreparedChapterTTSRequest",
    "get_chapter_tts_attempt",
    "get_chapter_tts_seal_lease",
    "prepare_chapter_tts_request",
    "produce_chapter_narration",
    "quarantine_stale_chapter_tts_send",
    "recover_unknown_chapter_tts_audio",
    "release_stale_chapter_tts_seal",
    "verify_chapter_tts_authorization",
]

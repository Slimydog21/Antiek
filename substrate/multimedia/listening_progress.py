"""Private owner-bound listening progress persistence for multimedia audio.

Listening progress is private user preference state — not media authority.
It selects a playback position only after the current local or paid playback
chain has independently reopened and verified the exact asset, revision,
audio digest, duration, and chapter timeline.
"""

from __future__ import annotations

import fcntl
import hashlib
import math
import os
import re
import secrets
import stat
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_OWNER_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_MAX_PROGRESS_BYTES = 4 * 1024
_COMPLETION_THRESHOLD_MS = 5_000
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MultimediaListeningProgress(_Base):
    """Durable listening progress envelope for one owner+asset+revision+audio."""

    schema_version: Literal["antiek.listening-progress.v1"] = "antiek.listening-progress.v1"
    owner_identity_digest: str = Field(pattern=_OWNER_DIGEST.pattern)
    asset_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    revision_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_milliseconds: int = Field(ge=0)
    duration_milliseconds: int = Field(gt=0)
    completed: bool = False
    session_id: str = Field(min_length=16, max_length=128, pattern=_SESSION_ID.pattern)
    sequence: int = Field(ge=0)
    updated_at: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_position_and_completion(self) -> MultimediaListeningProgress:
        if self.position_milliseconds > self.duration_milliseconds:
            raise ValueError("position_milliseconds exceeds duration_milliseconds")
        expected_completed = (
            self.duration_milliseconds - self.position_milliseconds
            <= _COMPLETION_THRESHOLD_MS
        )
        if self.completed is not expected_completed:
            raise ValueError("listening progress completion conflicts")
        return self


class ListeningProgressProjection(_Base):
    """Wire response for the listening progress API."""

    resume_available: bool
    asset_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    revision_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_milliseconds: int = Field(ge=0)
    duration_milliseconds: int = Field(gt=0)
    completed: bool = False
    session_id: str = Field(max_length=128)
    sequence: int = Field(ge=0)
    updated_at: float = Field(ge=0)
    applied: bool | None = None

    @model_validator(mode="after")
    def validate_presence(self) -> ListeningProgressProjection:
        if self.position_milliseconds > self.duration_milliseconds:
            raise ValueError("listening progress position exceeds duration")
        expected_completed = (
            self.duration_milliseconds - self.position_milliseconds
            <= _COMPLETION_THRESHOLD_MS
        )
        if self.resume_available and self.completed is not expected_completed:
            raise ValueError("listening progress completion conflicts")
        if self.resume_available:
            if not _SESSION_ID.fullmatch(self.session_id) or self.updated_at <= 0:
                raise ValueError("available listening progress is incomplete")
        elif (
            self.position_milliseconds != 0
            or self.completed
            or self.session_id
            or self.sequence != 0
            or self.updated_at != 0
        ):
            raise ValueError("absent listening progress carries state")
        return self


class ListeningProgressCheckpointRequest(_Base):
    """PUT body for a listening progress checkpoint."""

    revision_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    position_milliseconds: int = Field(ge=0, le=_MAX_SAFE_INTEGER, strict=True)
    session_id: str = Field(min_length=16, max_length=128, pattern=_SESSION_ID.pattern)
    sequence: int = Field(ge=0, le=_MAX_SAFE_INTEGER, strict=True)


@dataclass(frozen=True)
class AudioIdentity:
    """Server-derived audio identity for progress validation."""

    revision_id: str
    audio_sha256: str
    duration_seconds: float
    kind: str
    mode: str


class ListeningProgressError(ValueError):
    """Base error for listening progress operations."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ListeningProgressIntegrityConflict(ListeningProgressError):
    """Malformed or unsafe sidecar — integrity conflict, never absence."""


class ListeningProgressStore:
    """JSON-backed listening progress store.

    Progress lives in a ``listening-progress/`` subdirectory beneath the
    existing private account-digest directory. Each file is named by the
    asset ID and contains the full MultimediaListeningProgress envelope.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._root = Path(root)
        if self._root.is_symlink():
            raise ValueError("listening progress root cannot be a symlink")
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._root, 0o700)
        self._accounts = self._root / "accounts"
        if self._accounts.is_symlink():
            raise ValueError("listening progress account root cannot be a symlink")
        self._accounts.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self._accounts, 0o700)
        self._lock_path = self._root / ".listening-progress.lock"
        self._clock = clock
        self._thread_lock = threading.RLock()

    def read(
        self,
        asset_id: str,
        *,
        owner_id: str,
        revision_id: str,
        audio_identity: AudioIdentity,
    ) -> ListeningProgressProjection:
        """Read current progress for the authenticated owner and exact audio identity.

        Returns ``resume_available=False`` when no progress exists.
        Raises on stale revision, integrity conflict, or identity mismatch.
        """
        owner_digest = _owner_digest(owner_id)
        _validate_audio_identity(audio_identity, revision_id)
        with self._locked(exclusive=False):
            try:
                path = self._progress_path(owner_digest, asset_id)
            except KeyError:
                return ListeningProgressProjection(
                    resume_available=False,
                    asset_id=asset_id,
                    revision_id=revision_id,
                    audio_sha256=audio_identity.audio_sha256,
                    position_milliseconds=0,
                    duration_milliseconds=_duration_ms(audio_identity),
                    completed=False,
                    session_id="",
                    sequence=0,
                    updated_at=0.0,
                    applied=None,
                )
            if not path.exists():
                return ListeningProgressProjection(
                    resume_available=False,
                    asset_id=asset_id,
                    revision_id=revision_id,
                    audio_sha256=audio_identity.audio_sha256,
                    position_milliseconds=0,
                    duration_milliseconds=_duration_ms(audio_identity),
                    completed=False,
                    session_id="",
                    sequence=0,
                    updated_at=0.0,
                    applied=None,
                )
            progress = self._load_progress(path, owner_digest, asset_id)
            if progress.revision_id != revision_id:
                # Historical-revision progress is never returned for a new revision.
                return ListeningProgressProjection(
                    resume_available=False,
                    asset_id=asset_id,
                    revision_id=revision_id,
                    audio_sha256=audio_identity.audio_sha256,
                    position_milliseconds=0,
                    duration_milliseconds=_duration_ms(audio_identity),
                    completed=False,
                    session_id="",
                    sequence=0,
                    updated_at=0.0,
                    applied=None,
                )
            if progress.audio_sha256 != audio_identity.audio_sha256:
                raise ListeningProgressIntegrityConflict(
                    "listening_progress_audio_digest_conflict"
                )
            if progress.duration_milliseconds != _duration_ms(audio_identity):
                raise ListeningProgressIntegrityConflict(
                    "listening_progress_duration_conflict"
                )
            return ListeningProgressProjection(
                resume_available=True,
                asset_id=progress.asset_id,
                revision_id=progress.revision_id,
                audio_sha256=progress.audio_sha256,
                position_milliseconds=progress.position_milliseconds,
                duration_milliseconds=progress.duration_milliseconds,
                completed=progress.completed,
                session_id=progress.session_id,
                sequence=progress.sequence,
                updated_at=progress.updated_at,
                applied=None,
            )

    def checkpoint(
        self,
        asset_id: str,
        request: ListeningProgressCheckpointRequest,
        *,
        owner_id: str,
        audio_identity: AudioIdentity,
    ) -> ListeningProgressProjection:
        """Write a listening progress checkpoint.

        Within one session, a sequence at or below the stored sequence is an
        idempotent stale write and cannot replace newer progress. A different
        session may replace progress by server arrival order.
        """
        owner_digest = _owner_digest(owner_id)
        _validate_audio_identity(audio_identity, request.revision_id)
        duration_ms = _duration_ms(audio_identity)
        if request.position_milliseconds < 0 or request.position_milliseconds > duration_ms:
            raise ListeningProgressError("listening_progress_position_out_of_range")

        # Determine completion.
        completed = duration_ms - request.position_milliseconds <= _COMPLETION_THRESHOLD_MS

        now = float(self._clock())
        if not math.isfinite(now) or now <= 0:
            raise ListeningProgressError("listening_progress_invalid_clock")

        with self._locked(exclusive=True):
            path = self._progress_path(owner_digest, asset_id, create=True)
            existing: MultimediaListeningProgress | None = None
            if path.exists():
                existing = self._load_progress(path, owner_digest, asset_id)
                if existing.revision_id != request.revision_id:
                    # New revision replaces historical progress.
                    existing = None
                elif existing.audio_sha256 != audio_identity.audio_sha256:
                    raise ListeningProgressIntegrityConflict(
                        "listening_progress_audio_digest_conflict"
                    )
                elif (
                    existing.session_id == request.session_id
                    and request.sequence <= existing.sequence
                ):
                    # Same session: sequence at or below stored is stale.
                    return ListeningProgressProjection(
                        resume_available=True,
                        asset_id=asset_id,
                        revision_id=request.revision_id,
                        audio_sha256=audio_identity.audio_sha256,
                        position_milliseconds=existing.position_milliseconds,
                        duration_milliseconds=existing.duration_milliseconds,
                        completed=existing.completed,
                        session_id=existing.session_id,
                        sequence=existing.sequence,
                        updated_at=existing.updated_at,
                        applied=False,
                    )

            progress = MultimediaListeningProgress(
                owner_identity_digest=owner_digest,
                asset_id=asset_id,
                revision_id=request.revision_id,
                audio_sha256=audio_identity.audio_sha256,
                position_milliseconds=request.position_milliseconds,
                duration_milliseconds=duration_ms,
                completed=completed,
                session_id=request.session_id,
                sequence=request.sequence,
                updated_at=now,
            )
            self._save_progress(progress, owner_digest)
            return ListeningProgressProjection(
                resume_available=True,
                asset_id=progress.asset_id,
                revision_id=progress.revision_id,
                audio_sha256=progress.audio_sha256,
                position_milliseconds=progress.position_milliseconds,
                duration_milliseconds=progress.duration_milliseconds,
                completed=progress.completed,
                session_id=progress.session_id,
                sequence=progress.sequence,
                updated_at=progress.updated_at,
                applied=True,
            )

    def _progress_path(self, owner_digest: str, asset_id: str, *, create: bool = False) -> Path:
        if not _OWNER_DIGEST.fullmatch(owner_digest) or not _ASSET_ID.fullmatch(asset_id):
            raise KeyError(asset_id)
        return self._account_progress_dir(owner_digest, create=create) / f"{asset_id}.json"

    def _account_progress_dir(self, owner_digest: str, *, create: bool) -> Path:
        if not _OWNER_DIGEST.fullmatch(owner_digest):
            raise ValueError("listening progress owner identity is invalid")
        account = self._accounts / owner_digest
        if account.is_symlink():
            raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
        if not account.exists():
            if not create:
                raise KeyError("listening progress account not found")
            account.mkdir(mode=0o700)
            _fsync_directory(self._accounts)
        if not account.is_dir():
            raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
        os.chmod(account, 0o700)
        progress_dir = account / "listening-progress"
        if progress_dir.is_symlink():
            raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
        if not progress_dir.exists():
            if not create:
                raise KeyError("listening progress directory not found")
            progress_dir.mkdir(mode=0o700)
            _fsync_directory(account)
        if not progress_dir.is_dir():
            raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
        os.chmod(progress_dir, 0o700)
        return progress_dir

    def _load_progress(
        self, path: Path, owner_digest: str, asset_id: str
    ) -> MultimediaListeningProgress:
        if path.is_symlink():
            raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
        raw = _read_bounded(path)
        try:
            envelope = _Envelope.model_validate_json(raw)
        except Exception as exc:
            raise ListeningProgressIntegrityConflict(
                "listening_progress_envelope_invalid"
            ) from exc
        if (
            envelope.owner_identity_digest != owner_digest
            or envelope.progress.owner_identity_digest != owner_digest
            or envelope.progress.asset_id != asset_id
        ):
            raise ListeningProgressIntegrityConflict(
                "listening_progress_identity_conflict"
            )
        return envelope.progress

    def _save_progress(
        self, progress: MultimediaListeningProgress, owner_digest: str
    ) -> None:
        if progress.owner_identity_digest != owner_digest:
            raise ValueError("listening progress owner conflicts")
        progress_dir = self._account_progress_dir(owner_digest, create=True)
        path = progress_dir / f"{progress.asset_id}.json"
        if path.is_symlink():
            raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
        if path.exists():
            _require_private_regular(path)
        envelope = _Envelope(
            schema_version="antiek.listening-progress.v1",
            owner_identity_digest=owner_digest,
            progress=progress,
        )
        payload = (
            envelope.model_dump_json(indent=2).encode("utf-8") + b"\n"
        )
        if len(payload) > _MAX_PROGRESS_BYTES:
            raise ListeningProgressError("listening_progress_record_too_large")
        temporary = progress_dir / f".{progress.asset_id}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
            _fsync_directory(progress_dir)
        finally:
            os.close(descriptor)
            with suppress(FileNotFoundError):
                temporary.unlink()

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        with self._thread_lock:
            try:
                descriptor = os.open(
                    self._lock_path,
                    os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except OSError as exc:
                raise ListeningProgressIntegrityConflict(
                    "listening_progress_lock_unsafe"
                ) from exc
            try:
                os.chmod(self._lock_path, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)


class _Envelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["antiek.listening-progress.v1"]
    owner_identity_digest: str = Field(pattern=_OWNER_DIGEST.pattern)
    progress: MultimediaListeningProgress


def _owner_digest(owner_id: str) -> str:
    if not isinstance(owner_id, str):
        raise ValueError("listening progress owner identity is invalid")
    encoded = owner_id.strip().encode("utf-8")
    if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError("listening progress owner identity is invalid")
    return hashlib.sha256(encoded).hexdigest()


def _duration_ms(identity: AudioIdentity) -> int:
    seconds = identity.duration_seconds
    if not math.isfinite(seconds) or seconds <= 0:
        raise ListeningProgressError("listening_progress_invalid_duration")
    return round(seconds * 1000)


def _validate_audio_identity(identity: AudioIdentity, expected_revision_id: str) -> None:
    if identity.revision_id != expected_revision_id:
        raise ListeningProgressError("listening_progress_revision_mismatch")
    if identity.kind != "audio_experience" or identity.mode != "audio":
        raise ListeningProgressError("listening_progress_not_audio_asset")
    if not _ASSET_ID.fullmatch(identity.revision_id):
        raise ListeningProgressError("listening_progress_invalid_revision")
    if not re.fullmatch(r"[0-9a-f]{64}", identity.audio_sha256):
        raise ListeningProgressError("listening_progress_invalid_audio_digest")


def _require_private_regular(path: Path) -> os.stat_result:
    if path.is_symlink():
        raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
    metadata = path.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ListeningProgressIntegrityConflict("listening_progress_path_unsafe")
    return metadata


def _read_bounded(path: Path) -> bytes:
    metadata = _require_private_regular(path)
    if not 0 < metadata.st_size <= _MAX_PROGRESS_BYTES:
        raise ListeningProgressIntegrityConflict("listening_progress_record_invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise ListeningProgressIntegrityConflict("listening_progress_changed_during_read")
        chunks: list[bytes] = []
        remaining = _MAX_PROGRESS_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw or len(raw) > _MAX_PROGRESS_BYTES or os.read(descriptor, 1):
            raise ListeningProgressIntegrityConflict("listening_progress_record_invalid")
        return raw
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def mint_session_id() -> str:
    """Generate a cryptographically random session ID."""
    return secrets.token_urlsafe(24)[:32]


__all__ = [
    "AudioIdentity",
    "ListeningProgressCheckpointRequest",
    "ListeningProgressError",
    "ListeningProgressIntegrityConflict",
    "ListeningProgressProjection",
    "ListeningProgressStore",
    "MultimediaListeningProgress",
    "mint_session_id",
]

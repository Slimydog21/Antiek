"""Unmounted account-owned audio registry and authenticated current selection.

The future settings mount supplies the trusted Request and explicit private state
root/master key. This module never reads operator defaults or sends audio. Selection
facts are valid only inside guard_selection; they convey no dispatch permission.
Lock order is registry, existing credential-store guard, then registration.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from interfaces.research.api.settings_models_admin import UserModelChoice, request_owner_user_id
from runtime.byok import store
from runtime.research_runner.audio_provider_catalog import AudioModelDescriptor, get_audio_model
from substrate.byot_usage.actions import checked_int
from substrate.byot_usage.ledger import ByotUsageLedger

_MAX_BYTES = 1_048_576
_MAX_RECORDS = 128
_ACCOUNT = re.compile(r"acct_[0-9a-f]{32}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_REGISTRY_LOCK = threading.RLock()


class AudioModelUnavailable(ValueError):
    """Value-free refusal, including corrupt or unconfirmed publication."""


class AudioPublicationError(AudioModelUnavailable):
    def __init__(self, *, cleanup_confirmed: bool) -> None:
        super().__init__("audio publication failed")
        self.cleanup_confirmed = cleanup_confirmed


def _owner(request: Request) -> str:
    owner = request_owner_user_id(request)
    if (
        _ACCOUNT.fullmatch(owner) is None
        or getattr(request.state, "account_subject", None) != owner
        or getattr(request.state, "auth_method", None) != "antiek_session_cookie"
    ):
        raise HTTPException(401, "canonical account required")
    return owner


def _prefix(owner: str) -> str:
    return "audio-" + hashlib.sha256(owner.encode()).hexdigest()[:16] + "-"


class UserAudioModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    id: str = Field(min_length=39, max_length=39)
    owner_user_id: str
    catalog_id: Literal["openai"] = "openai"
    model_id: Literal["whisper-1"] = "whisper-1"
    adapter_kind: Literal["audio_transcription"] = "audio_transcription"
    operation: Literal["transcribe"] = "transcribe"
    endpoint: Literal["https://api.openai.com"] = "https://api.openai.com"
    request_path: Literal["/v1/audio/transcriptions"] = "/v1/audio/transcriptions"
    display_name: str = Field(min_length=1, max_length=64)
    credential_id: str = Field(min_length=1, max_length=128, repr=False)
    credential_fingerprint: str = Field(repr=False)
    generation: str
    enabled: bool = True

    @model_validator(mode="after")
    def validate_identity(self) -> UserAudioModelRecord:
        if (
            _ACCOUNT.fullmatch(self.owner_user_id) is None
            or not self.id.startswith(_prefix(self.owner_user_id))
            or re.fullmatch(r"[0-9a-f]{16}", self.id[-16:]) is None
            or _HEX.fullmatch(self.credential_fingerprint) is None
            or re.fullmatch(r"[0-9a-f]{32}", self.generation) is None
        ):
            raise ValueError("invalid audio record")
        return self


@dataclass(frozen=True, slots=True)
class _Registration:
    record: UserAudioModelRecord
    generation: str


@dataclass(frozen=True, slots=True)
class AudioSelection:
    """Captured identity to revalidate, not an executable adapter or permission."""

    record: UserAudioModelRecord
    descriptor: AudioModelDescriptor
    registration: _Registration
    dispatch_authority: Literal["unbound"] = "unbound"


def _secure_file(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise AudioModelUnavailable("unsafe audio registry")
    return info


def _content_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise AudioModelUnavailable("duplicate audio registry field")
        result[key] = value
    return result


class AudioModelService:
    """Server-constructed service using explicitly selected state/key material.

    Registration is process-local and must be reauthenticated after restart.
    Durable rows alone never manufacture registration or send authority.
    """

    def __init__(
        self,
        *,
        state_root: Path,
        prepared_master_key: bytes,
        artifact_path: Path | None = None,
    ) -> None:
        artifact = (
            artifact_path if artifact_path is not None else state_root / "byok" / "credentials.enc"
        )
        if (
            not state_root.is_absolute()
            or ".." in state_root.parts
            or len(prepared_master_key) != 32
            or not isinstance(artifact, Path)
            or not artifact.is_absolute()
            or ".." in artifact.parts
        ):
            raise AudioModelUnavailable("invalid audio service configuration")
        self._root = state_root
        self._key = prepared_master_key
        self._artifact = str(artifact)
        self._registrations: dict[str, _Registration] = {}
        self._registration_lock = threading.RLock()

    @contextmanager
    def _directory(self) -> Iterator[int]:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in self._root.parts[1:]:
                next_fd = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = next_fd
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise AudioModelUnavailable("unsafe audio state root")
            with suppress(FileExistsError):
                os.mkdir("settings", 0o700, dir_fd=fd)
            settings = os.open("settings", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                info = os.fstat(settings)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise AudioModelUnavailable("unsafe audio settings directory")
                yield settings
            finally:
                os.close(settings)
        finally:
            os.close(fd)

    @contextmanager
    def _registry(self, *, exclusive: bool) -> Iterator[tuple[int, list[UserAudioModelRecord]]]:
        with _REGISTRY_LOCK, self._directory() as directory:
            fd = os.open(
                "audio-models.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory,
            )
            try:
                identity = _secure_file(fd)
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                if _content_identity(
                    os.stat("audio-models.lock", dir_fd=directory, follow_symlinks=False)
                ) != _content_identity(identity):
                    raise AudioModelUnavailable("replaced audio registry lock")
                yield directory, self._read(directory)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _read(self, directory: int) -> list[UserAudioModelRecord]:
        try:
            fd = os.open(
                "user_audio_models.json",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
        except FileNotFoundError:
            return []
        try:
            before = _secure_file(fd)
            if before.st_size > _MAX_BYTES:
                raise AudioModelUnavailable("audio registry limit exceeded")
            remaining = before.st_size
            body = bytearray()
            while remaining:
                chunk = os.read(fd, min(remaining, 65_536))
                if not chunk or len(chunk) > remaining:
                    raise AudioModelUnavailable("incomplete audio registry")
                body.extend(chunk)
                remaining -= len(chunk)
            if (
                os.read(fd, 1)
                or _content_identity(before) != _content_identity(os.fstat(fd))
                or _content_identity(before)
                != _content_identity(
                    os.stat("user_audio_models.json", dir_fd=directory, follow_symlinks=False)
                )
            ):
                raise AudioModelUnavailable("changed audio registry")
            raw = bytes(body)
        finally:
            os.close(fd)
        try:
            data = json.loads(raw, object_pairs_hook=_pairs)
            if not isinstance(data, list) or len(data) > _MAX_RECORDS:
                raise AudioModelUnavailable("invalid audio registry")
            records = [UserAudioModelRecord.model_validate(row) for row in data]
        except (
            ValueError,
            ValidationError,
            TypeError,
        ):
            raise AudioModelUnavailable("invalid audio registry") from None
        if len({record.id for record in records}) != len(records):
            raise AudioModelUnavailable("duplicate audio record")
        return records

    def _write(self, directory: int, records: list[UserAudioModelRecord]) -> None:
        raw = json.dumps([r.model_dump(mode="json") for r in records], sort_keys=True).encode()
        if len(raw) > _MAX_BYTES or len(records) > _MAX_RECORDS:
            raise AudioModelUnavailable("audio registry limit exceeded")
        name = ".audio-" + uuid.uuid4().hex
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                old_fd = os.open(
                    "user_audio_models.json",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory,
                )
            except FileNotFoundError:
                pass
            else:
                try:
                    _secure_file(old_fd)
                finally:
                    os.close(old_fd)
            os.replace(name, "user_audio_models.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(name, dir_fd=directory)

    @staticmethod
    def _metadata_matches(record: UserAudioModelRecord, metadata: store.CredentialMetadata) -> bool:
        return (
            metadata.binding_version == 3
            and metadata.owner_user_id == record.owner_user_id
            and metadata.pipeline_kind == "audio_model_provider"
            and metadata.account_handle == record.id
            and metadata.cred_id == record.credential_id
            and metadata.artifact_fingerprint == record.credential_fingerprint
        )

    @staticmethod
    def _owned(
        records: list[UserAudioModelRecord], owner: str, record_id: str
    ) -> UserAudioModelRecord:
        for record in records:
            if record.id == record_id and record.owner_user_id == owner:
                return record
        raise AudioModelUnavailable("audio record unavailable")

    def _projection(self, record: UserAudioModelRecord) -> dict[str, object]:
        with self._registration_lock:
            current = self._registrations.get(record.id)
            registered = isinstance(current, _Registration) and current.record == record
        return {
            "id": record.id,
            "display_name": record.display_name,
            "catalog_id": record.catalog_id,
            "model_id": record.model_id,
            "endpoint": record.endpoint,
            "operation": record.operation,
            "enabled": record.enabled,
            "registered": registered,
            "dispatch_authority": "unbound",
        }

    def list(self, request: Request) -> list[dict[str, object]]:
        owner = _owner(request)
        with self._registry(exclusive=False) as (_, records):
            metadata = {
                row.cred_id: row for row in store.list_credentials(artifact_path=self._artifact)
            }
            return [
                self._projection(row)
                for row in records
                if row.owner_user_id == owner
                and row.credential_id in metadata
                and self._metadata_matches(row, metadata[row.credential_id])
            ]

    def _budget(
        self,
        request: Request,
        record_id: str,
        *,
        limit_cents: int | None = None,
        on_mutation_started: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        owner = _owner(request)
        if limit_cents is not None:
            checked_int(limit_cents)
        with self._registry(exclusive=False) as (_, records):
            record = self._owned(records, owner, record_id)
            with store.guard_current_credential(
                record.credential_id, prepared_master_key=self._key, artifact_path=self._artifact
            ) as guarded:
                if not self._metadata_matches(record, guarded.metadata):
                    raise AudioModelUnavailable("audio credential unavailable")
                # The registry/store guards precede even ledger construction.
                # Disabled/unregistered rows retain their independent liabilities.
                ledger = ByotUsageLedger()
                if limit_cents is not None:
                    if on_mutation_started is not None:
                        on_mutation_started()
                    ledger.set_limit(record.id, owner, limit_cents)
                usage = ledger.key_usage(record.id, owner)
                if limit_cents is not None and (usage is None or usage.limit_cents != limit_cents):
                    raise AudioModelUnavailable("audio budget publication unconfirmed")
                limit = usage.limit_cents if usage is not None else None
                if limit is not None:
                    checked_int(limit)
                used = checked_int(usage.used_cents) if usage is not None else 0
                held = checked_int(usage.held_cents) if usage is not None else 0
                return {
                    "id": record.id,
                    "currency": "USD",
                    "basis": "local_byot_usage_ledger",
                    "approved": limit is not None,
                    "limit_cents": limit,
                    "used_cents": used,
                    "held_cents": held,
                    "available_cents": max(0, limit - used - held) if limit is not None else None,
                }

    def get_budget(self, request: Request, record_id: str) -> dict[str, object]:
        return self._budget(request, record_id)

    def set_budget(
        self,
        request: Request,
        record_id: str,
        limit_cents: int,
        *,
        on_mutation_started: Callable[[], None],
    ) -> dict[str, object]:
        _owner(request)
        checked_int(limit_cents)
        return self._budget(
            request,
            record_id,
            limit_cents=limit_cents,
            on_mutation_started=on_mutation_started,
        )

    def create(self, request: Request, payload: Mapping[str, object]) -> dict[str, object]:
        owner = _owner(request)
        if set(payload) != {"catalog_id", "model_id", "endpoint", "display_name", "api_key"}:
            raise AudioModelUnavailable("invalid audio model request")
        key = payload["api_key"]
        display = payload["display_name"]
        if (
            payload["catalog_id"] != "openai"
            or payload["model_id"] != "whisper-1"
            or payload["endpoint"] != "https://api.openai.com"
            or not isinstance(key, str)
            or not 8 <= len(key) <= 512
            or not isinstance(display, str)
            or not 1 <= len(display) <= 64
            or key in display
            or key in "https://api.openai.com whisper-1 openai"
        ):
            raise AudioModelUnavailable("invalid audio model request")
        with self._registry(exclusive=True) as (directory, records):
            if len(records) >= _MAX_RECORDS:
                raise AudioModelUnavailable("audio registry limit exceeded")
            record_id = _prefix(owner) + uuid.uuid4().hex[:16]
            metadata = store.store_credential_with_metadata(
                record_id,
                key,
                owner_user_id=owner,
                pipeline_kind="audio_model_provider",
                artifact_path=self._artifact,
                key_bytes=self._key,
            )
            try:
                record = UserAudioModelRecord(
                    id=record_id,
                    owner_user_id=owner,
                    display_name=display,
                    credential_id=metadata.cred_id,
                    credential_fingerprint=metadata.artifact_fingerprint,
                    generation=uuid.uuid4().hex,
                )
                with store.guard_current_credential(
                    metadata.cred_id, prepared_master_key=self._key, artifact_path=self._artifact
                ) as guarded:
                    if not self._metadata_matches(record, guarded.metadata):
                        raise AudioModelUnavailable("audio credential unavailable")
                    with self._registration_lock:
                        registration = _Registration(record, record.generation)
                        self._registrations[record_id] = registration
                        try:
                            self._write(directory, [*records, record])
                        except BaseException:
                            self._registrations.pop(record_id, None)
                            raise
                return self._projection(record)
            except BaseException:
                with self._registration_lock:
                    self._registrations.pop(record_id, None)
                # Retire any possibly published row before deleting its credential.
                cleanup = False
                try:
                    self._write(directory, records)
                    cleanup = store.delete_credential(
                        metadata.cred_id, artifact_path=self._artifact
                    )
                except (
                    OSError,
                    ValueError,
                ):
                    pass
                raise AudioPublicationError(cleanup_confirmed=cleanup) from None

    def disable(self, request: Request, record_id: str) -> None:
        owner = _owner(request)
        with self._registry(exclusive=True) as (directory, records):
            record = self._owned(records, owner, record_id)
            disabled = UserAudioModelRecord.model_validate(
                {**record.model_dump(), "enabled": False, "generation": uuid.uuid4().hex}
            )
            self._write(directory, [disabled if row.id == record_id else row for row in records])
            with self._registration_lock:
                self._registrations.pop(record_id, None)

    def delete(self, request: Request, record_id: str) -> bool:
        owner = _owner(request)
        with self._registry(exclusive=True) as (directory, records):
            record = self._owned(records, owner, record_id)
            self._write(directory, [row for row in records if row.id != record_id])
            with self._registration_lock:
                self._registrations.pop(record_id, None)
            return store.delete_credential(record.credential_id, artifact_path=self._artifact)

    def capture(self, request: Request, choice: UserModelChoice) -> AudioSelection:
        owner = _owner(request)
        try:
            choice = UserModelChoice.model_validate(choice.model_dump())
        except (
            AttributeError,
            ValidationError,
        ):
            raise AudioModelUnavailable("invalid audio choice") from None
        with self._registry(exclusive=False) as (_, records):
            record = self._owned(records, owner, choice.provider_id)
            descriptor = get_audio_model(record.catalog_id, choice.model_id)
            if not record.enabled or record.model_id != choice.model_id:
                raise AudioModelUnavailable("audio selection unavailable")
            with store.guard_current_credential(
                record.credential_id, prepared_master_key=self._key, artifact_path=self._artifact
            ) as guarded:
                if not self._metadata_matches(record, guarded.metadata):
                    raise AudioModelUnavailable("audio credential unavailable")
                with self._registration_lock:
                    registration = self._registrations.get(record.id)
                    if (
                        not isinstance(registration, _Registration)
                        or registration.record != record
                        or registration.generation != record.generation
                    ):
                        raise AudioModelUnavailable("audio registration unavailable")
                    return AudioSelection(record, descriptor, registration)

    @contextmanager
    def guard_selection(
        self, request: Request, selection: AudioSelection
    ) -> Iterator[AudioSelection]:
        owner = _owner(request)
        if not isinstance(selection, AudioSelection) or selection.dispatch_authority != "unbound":
            raise AudioModelUnavailable("invalid audio selection")
        with self._registry(exclusive=False) as (_, records):
            record = self._owned(records, owner, selection.record.id)
            if (
                not record.enabled
                or record != selection.record
                or get_audio_model(record.catalog_id, record.model_id) != selection.descriptor
            ):
                raise AudioModelUnavailable("stale audio selection")
            with store.guard_current_credential(
                record.credential_id, prepared_master_key=self._key, artifact_path=self._artifact
            ) as guarded:
                if not self._metadata_matches(record, guarded.metadata):
                    raise AudioModelUnavailable("audio credential unavailable")
                with self._registration_lock:
                    current = self._registrations.get(record.id)
                    if (
                        not isinstance(current, _Registration)
                        or current is not selection.registration
                        or current.record != record
                        or current.generation != record.generation
                    ):
                        raise AudioModelUnavailable("stale audio registration")
                    yield selection

    @contextmanager
    def guard_selected_credential(
        self, request: Request, selection: AudioSelection
    ) -> Iterator[store.GuardedCredential]:
        with (
            self.guard_selection(request, selection),
            store.guard_current_credential(
                selection.record.credential_id,
                prepared_master_key=self._key,
                artifact_path=self._artifact,
            ) as guarded,
        ):
            if not self._metadata_matches(selection.record, guarded.metadata):
                raise AudioModelUnavailable("audio credential unavailable")
            yield guarded

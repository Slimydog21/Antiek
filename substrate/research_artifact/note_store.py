"""Immutable UTF-8 note objects; typed events decide which objects are accepted."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import secrets
import stat
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from .paths import research_artifacts_dir

MAX_NOTE_BYTES = 64 * 1024
MAX_BATCH_NOTES = 256
MAX_BATCH_BYTES = 1024 * 1024
MAX_PERSISTED_NOTES = 4096
MAX_PERSISTED_BYTES = 256 * 1024
NOTE_INTENT_PREFIX = "research_artifact_agent_note_v2:"


class NotePersistenceError(ValueError):
    """The accepted-note contract could not be read or durably committed."""


class CorruptNoteError(NotePersistenceError):
    """A structurally safe object does not contain its accepted note bytes."""


class MissingNoteError(NotePersistenceError):
    """An accepted note has no object at its storage-derived path."""


def validate_investigation_id(value: str) -> str:
    # Match the event log's storage identity, not an arbitrary event path.
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}", value):
        raise NotePersistenceError("invalid note investigation id")
    return value


def _validate_digest(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise NotePersistenceError("invalid note content hash")
    return value


def note_path(investigation_id: str, digest: str) -> Path:
    return research_artifacts_dir() / "notes" / validate_investigation_id(investigation_id) / f"{_validate_digest(digest)}.txt"


def note_intent(investigation_id: str, digest: str) -> str:
    return f"{NOTE_INTENT_PREFIX}{validate_investigation_id(investigation_id)}:{_validate_digest(digest)}"


def note_event_id(investigation_id: str, digest: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, note_intent(investigation_id, digest)))


def note_artifact_id(investigation_id: str, digest: str) -> str:
    return "ran-" + note_event_id(investigation_id, digest)


@contextmanager
def _directory(investigation_id: str, *, create: bool) -> Iterator[int]:
    iid = validate_investigation_id(investigation_id)
    root = research_artifacts_dir()
    fd = -1
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        if create:
            root.mkdir(parents=True, exist_ok=True)
        fd = os.open(root, flags)
        for component in ("notes", iid):
            if create:
                with suppress(FileExistsError):
                    os.mkdir(component, 0o700, dir_fd=fd)
                os.fsync(fd)
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise NotePersistenceError("managed note storage is not a private directory")
        yield fd
    except FileNotFoundError as exc:
        raise MissingNoteError("accepted note object or directory is missing") from exc
    except OSError as exc:
        raise NotePersistenceError("note storage cannot be opened safely") from exc
    finally:
        if fd >= 0:
            os.close(fd)


@contextmanager
def note_import_lock(investigation_id: str) -> Iterator[None]:
    """Serialize imports before the emitter acquires its separate event lock."""
    with _directory(investigation_id, create=True) as fd:
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise NotePersistenceError("timed out acquiring note import lock") from None
                time.sleep(0.01)
        yield


def _private_file_info(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > MAX_NOTE_BYTES):
        raise NotePersistenceError("accepted note is not a private bounded object")
    return info


def read_note(investigation_id: str, digest: str, size_bytes: int) -> str:
    digest = _validate_digest(digest)
    if not 0 < size_bytes <= MAX_NOTE_BYTES:
        raise NotePersistenceError("note size is outside its bound")
    with _directory(investigation_id, create=False) as directory:
        fd = os.open(f"{digest}.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = _private_file_info(fd)
            if info.st_size != size_bytes:
                raise CorruptNoteError("accepted note size does not match")
            data = bytearray()
            while len(data) <= size_bytes:
                chunk = os.read(fd, min(8192, size_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) != size_bytes or hashlib.sha256(data).hexdigest() != digest:
                raise CorruptNoteError("accepted note content hash or size does not match")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CorruptNoteError("accepted note is not UTF-8") from exc
            if not text or text != text.strip():
                raise CorruptNoteError("accepted note is not normalized")
            return text
        finally:
            os.close(fd)


def _write_temporary(directory: int, data: bytes) -> str:
    temporary = f".note-{secrets.token_hex(16)}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written == 0:
                    raise NotePersistenceError("note write made no progress")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        os.unlink(temporary, dir_fd=directory)
        raise
    return temporary


def publish_note(investigation_id: str, text: str) -> tuple[str, Path, int]:
    """Publish under note_import_lock; never replace a committed or corrupt object."""
    data = text.encode("utf-8")
    if not text or text != text.strip() or len(data) > MAX_NOTE_BYTES:
        raise NotePersistenceError("note is empty, unnormalized or exceeds its byte bound")
    digest = hashlib.sha256(data).hexdigest()
    with _directory(investigation_id, create=True) as directory:
        temporary = _write_temporary(directory, data)
        try:
            with suppress(FileExistsError):
                os.link(temporary, f"{digest}.txt", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        finally:
            os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)
    # Existing objects, including orphans from an earlier failed event append,
    # must verify before reuse. A corrupt object is never silently repaired.
    read_note(investigation_id, digest, len(data))
    return digest, note_path(investigation_id, digest), len(data)


def restore_note(investigation_id: str, digest: str, size_bytes: int, text: str) -> None:
    """Restore exact event-authorized bytes under note_import_lock, retaining damage."""
    data = text.encode("utf-8")
    if (hashlib.sha256(data).hexdigest() != _validate_digest(digest)
            or len(data) != size_bytes or not 0 < size_bytes <= MAX_NOTE_BYTES
            or text != text.strip()):
        raise NotePersistenceError("replacement does not match the accepted note")
    try:
        read_note(investigation_id, digest, size_bytes)
        return
    except MissingNoteError:
        publish_note(investigation_id, text)
        return
    except CorruptNoteError:
        pass
    with _directory(investigation_id, create=False) as directory:
        name = f"{digest}.txt"
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = _private_file_info(fd)
            temporary = _write_temporary(directory, data)
            try:
                current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                    raise NotePersistenceError("accepted note changed before recovery")
                _private_file_info(fd)
                os.fsync(fd)
                quarantine = f".quarantine-{digest}-{secrets.token_hex(16)}.txt"
                reserved = os.open(quarantine, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                   0o600, dir_fd=directory)
                os.close(reserved)
                # Leave even the reserved placeholder on a rename error: an
                # uncertain failure must never delete potentially moved bytes.
                os.rename(name, quarantine, src_dir_fd=directory, dst_dir_fd=directory)
                # After this fsync a crash leaves preserved damage and a missing
                # accepted path that a subsequent exact reimport can restore.
                os.fsync(directory)
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            finally:
                os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(fd)
    read_note(investigation_id, digest, size_bytes)

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
        yield fd
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


def read_note(investigation_id: str, digest: str, size_bytes: int) -> str:
    digest = _validate_digest(digest)
    if not 0 < size_bytes <= MAX_NOTE_BYTES:
        raise NotePersistenceError("note size is outside its bound")
    with _directory(investigation_id, create=False) as directory:
        fd = os.open(f"{digest}.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size != size_bytes):
                raise NotePersistenceError("accepted note is not a private bounded object")
            data = bytearray()
            while len(data) <= size_bytes:
                chunk = os.read(fd, min(8192, size_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) != size_bytes or hashlib.sha256(data).hexdigest() != digest:
                raise NotePersistenceError("accepted note content hash or size does not match")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise NotePersistenceError("accepted note is not UTF-8") from exc
            if not text or text != text.strip():
                raise NotePersistenceError("accepted note is not normalized")
            return text
        finally:
            os.close(fd)


def publish_note(investigation_id: str, text: str) -> tuple[str, Path, int]:
    """Publish under note_import_lock; never replace a committed or corrupt object."""
    data = text.encode("utf-8")
    if not text or text != text.strip() or len(data) > MAX_NOTE_BYTES:
        raise NotePersistenceError("note is empty, unnormalized or exceeds its byte bound")
    digest = hashlib.sha256(data).hexdigest()
    with _directory(investigation_id, create=True) as directory:
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
            with suppress(FileExistsError):
                os.link(temporary, f"{digest}.txt", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        finally:
            os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)
    # Existing objects, including orphans from an earlier failed event append,
    # must verify before reuse. A corrupt object is never silently repaired.
    read_note(investigation_id, digest, len(data))
    return digest, note_path(investigation_id, digest), len(data)

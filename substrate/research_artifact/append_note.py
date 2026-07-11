"""Persist one bounded note into the canonical ResearchArtifact."""

from __future__ import annotations

import fcntl
import os
import stat
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from .import_notes import import_agent_notes, parse_body_from_html
from .paths import artifact_path_for
from .render import render_html
from .schema import SCHEMA_VERSION

MAX_NOTE_CHARS = 20_000
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


class StaleArtifactError(ValueError):
    """The caller rendered an older canonical artifact."""


@dataclass(frozen=True)
class AppendNoteResult:
    investigation_id: str
    notes_persisted: int
    notes_skipped_duplicate: int
    current_content_hash: str
    event_ids: list[str]
    event_pending: bool = False


_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(path), threading.Lock())


@contextmanager
def _process_lock(path: Path) -> Iterator[None]:
    """Serialize canonical rewrites across API worker processes."""
    lock_path = path.with_name(f".{path.name}.lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_canonical(path: Path) -> str:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_ARTIFACT_BYTES
    ):
        raise ValueError("canonical artifact unavailable")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size > MAX_ARTIFACT_BYTES
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError("canonical artifact unavailable")
        chunks: list[bytes] = []
        remaining = MAX_ARTIFACT_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("canonical artifact unavailable")
    return raw.decode("utf-8", errors="strict")


def _atomic_private_write(path: Path, text: str) -> None:
    raw = text.encode("utf-8")
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("rendered artifact exceeds size limit")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            fd = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def append_note(
    investigation_id: str,
    note: str,
    expected_content_hash: str,
    *,
    events_dir: str | None = None,
) -> AppendNoteResult:
    """Append to the canonical v2 artifact; caller paths/HTML are never accepted."""
    text = note.strip()
    if not text:
        raise ValueError("note must not be empty")
    if len(text) > MAX_NOTE_CHARS:
        raise ValueError(f"note exceeds {MAX_NOTE_CHARS} characters")
    if len(expected_content_hash) != 64:
        raise ValueError("expected_content_hash must be a SHA-256 hex digest")
    try:
        int(expected_content_hash, 16)
    except ValueError as exc:
        raise ValueError("expected_content_hash must be a SHA-256 hex digest") from exc

    path = artifact_path_for(investigation_id)
    with _lock_for(path), _process_lock(path):
        body = parse_body_from_html(_read_canonical(path))
        if body.schema_version != SCHEMA_VERSION or body.investigation_id != investigation_id:
            raise ValueError("canonical artifact identity mismatch")
        current_hash = body.content_hash()
        if current_hash != expected_content_hash:
            raise StaleArtifactError("artifact content hash is stale")
        if text in {existing.strip() for existing in body.agent_notes}:
            # Reconcile a prior file-first commit whose event append failed.
            imported = import_agent_notes(
                path, investigation_id=investigation_id, events_dir=events_dir
            )
            return AppendNoteResult(investigation_id, 0, 1, current_hash, imported.event_ids)

        body.agent_notes.append(text)
        rendered = render_html(body)
        _atomic_private_write(path, rendered)
        try:
            imported = import_agent_notes(
                path, investigation_id=investigation_id, events_dir=events_dir
            )
        except OSError:
            # The canonical note is already durable. Report honest indexing
            # lag; the next append/duplicate pass reconciles it idempotently.
            return AppendNoteResult(
                investigation_id=investigation_id,
                notes_persisted=1,
                notes_skipped_duplicate=0,
                current_content_hash=body.content_hash(),
                event_ids=[],
                event_pending=True,
            )
        return AppendNoteResult(
            investigation_id=investigation_id,
            notes_persisted=1,
            notes_skipped_duplicate=0,
            current_content_hash=body.content_hash(),
            event_ids=imported.event_ids,
        )

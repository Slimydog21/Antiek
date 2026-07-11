"""Crash-safe filesystem adapter for the run-durability ``EventLogPort``.

This is deliberately a narrow adapter.  It stores the canonical
``TraceEvent`` bytes and does not participate in the event_log JSONL/Parquet
trajectory format.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import secrets
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from substrate.run_durability.checkpoints import validate_ref, validate_sequence
from substrate.run_durability.trace import (
    ConcurrentAppendError,
    TraceError,
    TraceEvent,
    reconstruct,
)

MAX_EVENT_BYTES: Final = 16 * 1024
MAX_EVENTS_PER_RUN: Final = 10_000
MAX_RUN_BYTES: Final = 64 * 1024 * 1024
MAX_TEMP_FILES: Final = 32
MAX_TEMP_BYTES: Final = 512 * 1024

_FINAL_RE: Final = re.compile(r"([0-9]{20})\.json\Z")
_TEMP_RE: Final = re.compile(r"\.eventlog-tmp-([0-9]{20})-([0-9a-f]{64})\Z")
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class RunDurabilityEventLogPort:
    """One-file-per-event implementation of the durable-run CAS protocol."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_event_bytes: int = MAX_EVENT_BYTES,
        max_events_per_run: int = MAX_EVENTS_PER_RUN,
        max_run_bytes: int = MAX_RUN_BYTES,
        max_temp_files: int = MAX_TEMP_FILES,
        max_temp_bytes: int = MAX_TEMP_BYTES,
    ) -> None:
        self._root = Path(root)
        self._max_event_bytes = self._positive_limit(max_event_bytes, "max_event_bytes")
        self._max_events = self._positive_limit(max_events_per_run, "max_events_per_run")
        self._max_run_bytes = self._positive_limit(max_run_bytes, "max_run_bytes")
        self._max_temp_files = self._positive_limit(max_temp_files, "max_temp_files")
        self._max_temp_bytes = self._positive_limit(max_temp_bytes, "max_temp_bytes")
        if self._max_event_bytes > self._max_run_bytes:
            raise ValueError("max_event_bytes cannot exceed max_run_bytes")
        self._root_identity: tuple[int, int] | None = None
        self._run_identities: dict[str, tuple[int, int]] = {}
        self._ensure_root()

    @staticmethod
    def _positive_limit(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    @staticmethod
    def _run_name(run_id: str) -> str:
        validated = validate_ref(run_id, field="run_id")
        return hashlib.sha256(validated.encode("utf-8")).hexdigest()

    @staticmethod
    def _check_private_directory(fd: int, label: str) -> None:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise TraceError(f"{label} is not a directory")
        if info.st_uid != os.getuid():
            raise TraceError(f"{label} is not owned by the current user")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise TraceError(f"{label} is group/world accessible")
        if stat.S_IMODE(info.st_mode) & 0o700 != 0o700:
            raise TraceError(f"{label} lacks private user access")

    def _walk_root(self, *, create: bool) -> int:
        """Open the root without resolving a symlink path component."""
        absolute = self._root.absolute()
        parts = absolute.parts
        parent_fd = os.open(parts[0], _DIRECTORY_FLAGS)
        try:
            for part in parts[1:-1]:
                next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = next_fd
            leaf = parts[-1]
            if create:
                try:
                    os.mkdir(leaf, 0o700, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except FileExistsError:
                    pass
            root_fd = os.open(leaf, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            self._check_private_directory(root_fd, "event-log root")
            return root_fd
        except OSError as exc:
            raise TraceError("unsafe or inaccessible event-log root") from exc
        finally:
            os.close(parent_fd)

    def _ensure_root(self) -> None:
        root_fd = self._walk_root(create=True)
        try:
            info = os.fstat(root_fd)
            self._root_identity = (info.st_dev, info.st_ino)
        finally:
            os.close(root_fd)

    def _open_root(self) -> int:
        fd = -1
        try:
            fd = self._walk_root(create=False)
            info = os.fstat(fd)
            if self._root_identity != (info.st_dev, info.st_ino):
                raise TraceError("event-log root changed after adapter initialization")
            return fd
        except Exception:
            if fd >= 0:
                os.close(fd)
            raise

    def _open_run(self, run_id: str, *, create: bool) -> int | None:
        name = self._run_name(run_id)
        root_fd = self._open_root()
        try:
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=root_fd)
                    os.fsync(root_fd)
                except FileExistsError:
                    pass
            try:
                run_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError:
                return None
            self._check_private_directory(run_fd, "run directory")
            info = os.fstat(run_fd)
            identity = (info.st_dev, info.st_ino)
            known = self._run_identities.get(name)
            if known is not None and known != identity:
                os.close(run_fd)
                raise TraceError("run directory changed after adapter initialization")
            self._run_identities[name] = identity
            return run_fd
        except OSError as exc:
            raise TraceError("unsafe or inaccessible run directory") from exc
        finally:
            os.close(root_fd)

    @staticmethod
    def _read_bounded(fd: int, limit: int) -> bytes:
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        if len(value) > limit:
            raise TraceError("event file exceeds configured byte limit")
        return value

    def _scan(self, run_fd: int, run_id: str) -> tuple[TraceEvent, ...]:
        finals: dict[int, str] = {}
        entries: dict[str, os.stat_result] = {}
        linked_publications: set[int] = set()
        temp_count = temp_bytes = 0
        final_bytes = 0
        try:
            names = os.listdir(run_fd)
        except OSError as exc:
            raise TraceError("could not enumerate run directory") from exc
        for name in names:
            final_match = _FINAL_RE.fullmatch(name)
            temp_match = _TEMP_RE.fullmatch(name)
            if final_match is None and temp_match is None:
                raise TraceError("unexpected permanent file in run directory")
            try:
                info = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
            except FileNotFoundError:
                if temp_match is not None:
                    continue
                raise TraceError("committed event changed during validation") from None
            except OSError as exc:
                raise TraceError("run entry changed during validation") from exc
            if not stat.S_ISREG(info.st_mode):
                raise TraceError("run entries must be regular files")
            if info.st_uid != os.getuid():
                raise TraceError("run entry is not owned by the current user")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise TraceError("run entries must have mode 0600")
            entries[name] = info
            if temp_match is not None:
                sequence = int(temp_match.group(1))
                if info.st_nlink == 2:
                    final_info = entries.get(f"{sequence:020d}.json")
                    if final_info is None:
                        try:
                            final_info = os.stat(
                                f"{sequence:020d}.json", dir_fd=run_fd, follow_symlinks=False
                            )
                        except FileNotFoundError:
                            final_info = None
                    if final_info is None or (
                        final_info.st_dev,
                        final_info.st_ino,
                        final_info.st_nlink,
                    ) != (info.st_dev, info.st_ino, 2):
                        raise TraceError("uncommitted event has an unsafe link count")
                    linked_publications.add(sequence)
                    # A proven alias of a published final consumes no extra
                    # file data and is not an uncommitted allocation.
                    continue
                if info.st_nlink != 1:
                    raise TraceError("uncommitted event has an unsafe link count")
                temp_count += 1
                temp_bytes += info.st_size
                if temp_count > self._max_temp_files or temp_bytes > self._max_temp_bytes:
                    raise TraceError("uncommitted temp-file budget exceeded")
                continue
            assert final_match is not None
            sequence = int(final_match.group(1))
            if sequence in finals:
                raise TraceError("duplicate sequence file")
            finals[sequence] = name
            final_bytes += info.st_size
            if info.st_size > self._max_event_bytes or final_bytes > self._max_run_bytes:
                raise TraceError("committed event byte budget exceeded")
        if len(finals) > self._max_events:
            raise TraceError("event-count budget exceeded")
        if sorted(finals) != list(range(len(finals))):
            raise TraceError("committed sequence files must be contiguous and zero-based")

        events: list[TraceEvent] = []
        for sequence in range(len(finals)):
            name = finals[sequence]
            final_info = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
            try:
                fd = os.open(name, _READ_FLAGS, dir_fd=run_fd)
                try:
                    info = os.fstat(fd)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_nlink not in {1, 2}
                    ):
                        raise TraceError("committed event is not a safe regular file")
                    if info.st_nlink == 2 and sequence not in linked_publications:
                        raise TraceError("committed event has an unexplained external hard link")
                    if (info.st_dev, info.st_ino) != (final_info.st_dev, final_info.st_ino):
                        raise TraceError("committed event changed between validation and open")
                    raw = self._read_bounded(fd, self._max_event_bytes)
                finally:
                    os.close(fd)
            except OSError as exc:
                raise TraceError("committed event changed during read") from exc
            event = TraceEvent.from_json(raw)
            if event.run_id != run_id or event.sequence != sequence:
                raise TraceError("sequence file contains a cross-run or misnamed event")
            events.append(event)
        reconstruct(tuple(events))
        return tuple(events)

    def read(self, run_id: str) -> Sequence[TraceEvent]:
        self._run_name(run_id)  # validate before touching storage
        run_fd = self._open_run(run_id, create=False)
        if run_fd is None:
            return ()
        try:
            return self._scan(run_fd, run_id)
        finally:
            os.close(run_fd)

    def append(self, event: TraceEvent, *, expected_sequence: int) -> None:
        try:
            expected = validate_sequence(expected_sequence, field="expected_sequence")
        except (TypeError, ValueError) as exc:
            raise ConcurrentAppendError("invalid expected sequence") from exc
        if expected >= 10**20:
            raise ConcurrentAppendError("expected sequence exceeds canonical filename capacity")
        if not isinstance(event, TraceEvent):
            raise TraceError("event must be a TraceEvent")
        # Reparse to reject mutated/hostile subclasses and obtain immutable canonical bytes.
        canonical = event.to_json()
        candidate = TraceEvent.from_json(canonical)
        if len(canonical) > self._max_event_bytes:
            raise TraceError("event exceeds configured byte limit")
        run_fd = self._open_run(candidate.run_id, create=True)
        assert run_fd is not None
        temp_name: str | None = None
        published = False
        try:
            before = self._scan(run_fd, candidate.run_id)
            if len(before) != expected or candidate.sequence != expected:
                raise ConcurrentAppendError("compare-and-swap rejected concurrent writer")
            if len(before) >= self._max_events:
                raise TraceError("event-count budget exceeded")
            if sum(len(item.to_json()) for item in before) + len(canonical) > self._max_run_bytes:
                raise TraceError("committed event byte budget exceeded")
            reconstruct((*before, candidate))
            final_name = f"{expected:020d}.json"
            for _ in range(8):
                temp_name = f".eventlog-tmp-{expected:020d}-{secrets.token_hex(32)}"
                try:
                    fd = os.open(
                        temp_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=run_fd,
                    )
                    break
                except FileExistsError:
                    continue
            else:
                raise TraceError("could not allocate an uncommitted event file")
            try:
                view = memoryview(canonical)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError(errno.EIO, "short event write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(
                    temp_name,
                    final_name,
                    src_dir_fd=run_fd,
                    dst_dir_fd=run_fd,
                    follow_symlinks=False,
                )
                published = True
            except FileExistsError as exc:
                raise ConcurrentAppendError("compare-and-swap rejected concurrent writer") from exc
            try:
                os.fsync(run_fd)
                os.unlink(temp_name, dir_fd=run_fd)
                temp_name = None
                os.fsync(run_fd)
            except OSError as exc:
                raise TraceError(
                    "event publication occurred but durable directory state is ambiguous"
                ) from exc
            after = self._scan(run_fd, candidate.run_id)
            if len(after) != len(before) + 1 or after[:-1] != before or after[-1] != candidate:
                raise ConcurrentAppendError("published event failed exact read-back verification")
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name, dir_fd=run_fd)
                    if published:
                        os.fsync(run_fd)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    if published:
                        raise TraceError("published event temp cleanup failed") from exc
            os.close(run_fd)


# A short alias is useful at the event-log ownership boundary.
EventLogPortAdapter = RunDurabilityEventLogPort

__all__ = [
    "EventLogPortAdapter",
    "MAX_EVENT_BYTES",
    "MAX_EVENTS_PER_RUN",
    "MAX_RUN_BYTES",
    "MAX_TEMP_BYTES",
    "MAX_TEMP_FILES",
    "RunDurabilityEventLogPort",
]

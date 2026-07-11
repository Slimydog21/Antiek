"""Crash-safe Semantic Scholar snapshot generations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import cast

_CURRENT = "CURRENT"
_LOCK = ".publish.lock"
_NAME = re.compile(r"snapshot-[0-9a-f]{64}\.json")
_MAX_BYTES = 16 * 1024 * 1024
_FIELDS = frozenset({"paperId", "requestedId", "title", "abstract", "fetched_at", "source"})


class S2SnapshotError(ValueError):
    """A snapshot, cache path, response, or timestamp violated the boundary."""


def _exact_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise S2SnapshotError(f"{field} must be a trimmed nonempty exact str")
    return value


def _record(value: object) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise S2SnapshotError("S2 snapshot record must have exact frozen fields")
    raw = cast(dict[str, object], value)
    paper_id = _exact_text(raw["paperId"], "paperId")
    requested_id = _exact_text(raw["requestedId"], "requestedId")
    title = _exact_text(raw["title"], "title")
    abstract = raw["abstract"]
    if abstract is not None and (type(abstract) is not str or not abstract.strip()):
        raise S2SnapshotError("abstract must be null or a nonempty exact str")
    fetched_at = raw["fetched_at"]
    if type(fetched_at) not in {int, float} or isinstance(fetched_at, bool):
        raise S2SnapshotError("fetched_at must be a finite nonnegative Unix timestamp")
    numeric = float(cast(int | float, fetched_at))
    if not math.isfinite(numeric) or numeric < 0:
        raise S2SnapshotError("fetched_at must be a finite nonnegative Unix timestamp")
    if raw["source"] != "semantic_scholar":
        raise S2SnapshotError("source must be semantic_scholar")
    return {
        "paperId": paper_id,
        "requestedId": requested_id,
        "title": title,
        "abstract": abstract,
        "fetched_at": numeric,
        "source": "semantic_scholar",
    }


def _canonical(records: tuple[dict[str, object], ...]) -> bytes:
    payload = {"schema_version": 1, "records": records}
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise S2SnapshotError("snapshot is not canonical JSON") from error


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise S2SnapshotError("cache path must be a real directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise S2SnapshotError("cache directory must not grant group/other permissions")
    return path


def _write_atomic(directory: Path, final_name: str, content: bytes) -> None:
    temporary = directory / f".{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(temporary, directory / final_name)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def _read_exact(fd: int, size: int, field: str) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(fd, remaining)
        if not chunk:
            raise S2SnapshotError(f"{field} ended before its declared size")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class S2SnapshotStore:
    def __init__(self, cache_dir: Path) -> None:
        if not isinstance(cache_dir, Path):
            raise S2SnapshotError("cache_dir must be a pathlib Path")
        self._directory = _private_directory(cache_dir)

    def _read_file(self, name: str) -> bytes:
        if not _NAME.fullmatch(name):
            raise S2SnapshotError("CURRENT contains an invalid snapshot name")
        path = self._directory / name
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError as error:
            raise S2SnapshotError("current snapshot is unavailable") from error
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise S2SnapshotError("snapshot must be a single-link regular file")
            if info.st_size <= 0 or info.st_size > _MAX_BYTES:
                raise S2SnapshotError("snapshot size is outside the allowed bound")
            content = _read_exact(fd, info.st_size, "snapshot")
        finally:
            os.close(fd)
        digest = hashlib.sha256(content).hexdigest()
        if name != f"snapshot-{digest}.json":
            raise S2SnapshotError("snapshot digest does not match CURRENT")
        return content

    def _read_current(self) -> str | None:
        path = self._directory / _CURRENT
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise S2SnapshotError("CURRENT is unavailable") from error
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 1 <= info.st_size <= 80:
                raise S2SnapshotError("CURRENT must be a bounded single-link regular file")
            content = _read_exact(fd, info.st_size, "CURRENT")
        finally:
            os.close(fd)
        try:
            return content.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise S2SnapshotError("CURRENT must contain ASCII") from error

    def load(self) -> tuple[dict[str, object], ...]:
        name = self._read_current()
        if name is None:
            return ()
        try:
            payload = json.loads(self._read_file(name))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise S2SnapshotError("snapshot JSON is invalid") from error
        if type(payload) is not dict or frozenset(payload) != {"schema_version", "records"}:
            raise S2SnapshotError("snapshot envelope has invalid fields")
        if payload["schema_version"] != 1 or type(payload["records"]) is not list:
            raise S2SnapshotError("snapshot schema version or records are invalid")
        records = tuple(_record(item) for item in payload["records"])
        ids = tuple(str(item["paperId"]) for item in records)
        if len(ids) != len(set(ids)) or ids != tuple(sorted(ids)):
            raise S2SnapshotError("snapshot record ids must be unique and sorted")
        return records

    def publish(self, records: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
        if type(records) is not tuple or any(type(item) is not dict for item in records):
            raise S2SnapshotError("publish records must be an exact tuple of exact dicts")
        incoming = tuple(_record(item) for item in records)
        incoming_ids = tuple(str(item["paperId"]) for item in incoming)
        if len(incoming_ids) != len(set(incoming_ids)):
            raise S2SnapshotError("response contains duplicate paperId")
        lock_path = self._directory / _LOCK
        lock_flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        try:
            lock_fd = os.open(lock_path, lock_flags, 0o600)
        except OSError as error:
            raise S2SnapshotError("publish lock is unavailable") from error
        try:
            lock_info = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1:
                raise S2SnapshotError("publish lock must be a single-link regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            merged = {str(item["paperId"]): item for item in self.load()}
            merged.update({str(item["paperId"]): item for item in incoming})
            snapshot = tuple(merged[key] for key in sorted(merged))
            content = _canonical(snapshot)
            name = f"snapshot-{hashlib.sha256(content).hexdigest()}.json"
            path = self._directory / name
            created = False
            if path.exists():
                if self._read_file(name) != content:
                    raise S2SnapshotError("existing content-addressed snapshot conflicts")
            else:
                _write_atomic(self._directory, name, content)
                created = True
            try:
                _write_atomic(self._directory, _CURRENT, f"{name}\n".encode("ascii"))
            except BaseException:
                if created:
                    path.unlink(missing_ok=True)
                raise
            for candidate in self._directory.iterdir():
                if candidate.name != name and _NAME.fullmatch(candidate.name):
                    candidate.unlink(missing_ok=True)
            directory_fd = os.open(self._directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return snapshot
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

"""Admit a closed gzip/ustar archive into a private, empty restore directory.

The caller must keep the archive inode closed to writers and run the later
DuckDB IMPORT under a separate OS sandbox. This module does neither job.
"""

from __future__ import annotations

import hashlib
import os
import stat
import zlib
from dataclasses import dataclass
from pathlib import Path

_BLOCK = 512
_CHUNK = 64 * 1024
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class ArchiveAdmissionError(ValueError):
    """The archive or extraction destination violates the admission contract."""


@dataclass(frozen=True)
class ArchiveLimits:
    compressed_bytes: int = 2 * 1024**3
    expanded_bytes: int = 8 * 1024**3
    members: int = 100_000
    member_bytes: int = 4 * 1024**3
    path_bytes: int = 4096
    path_depth: int = 32

    def __post_init__(self) -> None:
        if (
            min(
                self.compressed_bytes,
                self.expanded_bytes,
                self.members,
                self.member_bytes,
                self.path_bytes,
                self.path_depth,
            )
            < 1
        ):
            raise ValueError("archive limits must be positive")


@dataclass(frozen=True)
class AdmittedMember:
    path: str
    size: int
    sha256: str | None  # None for a directory.


@dataclass(frozen=True)
class AdmissionReport:
    archive_sha256: str
    compressed_bytes: int
    expanded_bytes: int
    members: tuple[AdmittedMember, ...]


class _GzipReader:
    def __init__(self, fd: int, limits: ArchiveLimits) -> None:
        self.fd = fd
        self.limits = limits
        self.decoder = zlib.decompressobj(31)
        self.compressed = 0
        self.expanded = 0
        self.digest = hashlib.sha256()
        self.pending = b""
        self.output = bytearray()
        self.finished = False

    def _pump(self) -> None:
        if self.finished:
            return
        if not self.pending:
            data = os.read(self.fd, min(_CHUNK, self.limits.compressed_bytes - self.compressed + 1))
            if not data:
                raise ArchiveAdmissionError("truncated gzip stream")
            self.compressed += len(data)
            if self.compressed > self.limits.compressed_bytes:
                raise ArchiveAdmissionError("compressed archive exceeds limit")
            self.digest.update(data)
            self.pending = data
        try:
            data = self.decoder.decompress(
                self.pending, min(_CHUNK, self.limits.expanded_bytes - self.expanded + 1)
            )
        except zlib.error as exc:
            raise ArchiveAdmissionError("invalid gzip stream") from exc
        self.pending = self.decoder.unconsumed_tail
        self.expanded += len(data)
        if self.expanded > self.limits.expanded_bytes:
            raise ArchiveAdmissionError("expanded archive exceeds limit")
        self.output.extend(data)
        if self.decoder.eof:
            if self.decoder.unused_data or self.pending:
                raise ArchiveAdmissionError("data follows gzip stream")
            tail = os.read(self.fd, 1)
            if tail:
                raise ArchiveAdmissionError("data follows gzip stream")
            self.finished = True

    def read(self, count: int) -> bytes:
        while len(self.output) < count and not self.finished:
            self._pump()
        if len(self.output) < count:
            raise ArchiveAdmissionError("truncated tar stream")
        result = bytes(self.output[:count])
        del self.output[:count]
        return result

    def finish_tar(self) -> None:
        while not self.finished:
            if any(self.output):
                raise ArchiveAdmissionError("nonzero data after tar end")
            self.output.clear()
            self._pump()
        if any(self.output):
            raise ArchiveAdmissionError("nonzero data after tar end")
        self.output.clear()


def _field(header: bytes, start: int, width: int) -> bytes:
    raw = header[start : start + width]
    value, separator, suffix = raw.partition(b"\0")
    if separator and any(byte not in (0, 32) for byte in suffix):
        raise ArchiveAdmissionError("nonzero data after tar field terminator")
    return value


def _octal(header: bytes, start: int, width: int) -> int:
    raw = _field(header, start, width).strip(b" ")
    if not raw or any(byte not in b"01234567" for byte in raw):
        raise ArchiveAdmissionError("invalid tar numeric field")
    return int(raw, 8)


def _member(
    header: bytes, limits: ArchiveLimits, long_name: bytes | None = None
) -> tuple[str, int, bool, bool]:
    posix = header[257:265] == b"ustar\x0000"
    gnu = header[257:265] == b"ustar  \0"
    if not (posix or gnu):
        raise ArchiveAdmissionError("unsupported tar header format")
    recorded = _octal(header, 148, 8)
    actual = sum(header[:148]) + sum(b"        ") + sum(header[156:])
    if recorded != actual:
        raise ArchiveAdmissionError("invalid tar header checksum")
    kind = header[156:157]
    extension = gnu and kind == b"L"
    if kind not in (b"0", b"\0", b"5") and not extension:
        raise ArchiveAdmissionError("only regular files and directories are admitted")
    if _field(header, 157, 100):
        raise ArchiveAdmissionError("tar link target is forbidden")
    if _field(header, 329, 8).strip(b" 0") or _field(header, 337, 8).strip(b" 0"):
        raise ArchiveAdmissionError("tar device metadata is forbidden")
    size = _octal(header, 124, 12)
    if extension:
        if long_name is not None or size > min(limits.path_bytes + 1, limits.member_bytes):
            raise ArchiveAdmissionError("invalid GNU long-name record")
        return "", size, False, True
    raw_name = _field(header, 0, 100)
    prefix = _field(header, 345, 155) if posix else b""
    if long_name is not None:
        raw_path = long_name
    elif prefix:
        raw_path = prefix + b"/" + raw_name
    else:
        raw_path = raw_name
    if len(raw_path) > limits.path_bytes:
        raise ArchiveAdmissionError("tar path exceeds byte limit")
    try:
        path = raw_path.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ArchiveAdmissionError("tar path is not UTF-8") from exc
    directory = kind == b"5"
    if directory and path.endswith("/"):
        path = path[:-1]
    segments = path.split("/")
    if (
        not path
        or path.startswith("/")
        or len(segments) > limits.path_depth
        or any(part in ("", ".", "..") or "\x00" in part for part in segments)
    ):
        raise ArchiveAdmissionError("unsafe or noncanonical tar path")
    if size > limits.member_bytes:
        raise ArchiveAdmissionError("tar member exceeds limit")
    if directory and size:
        raise ArchiveAdmissionError("directory has payload")
    return path, size, directory, False


def _remember_directory(fd: int, path: str, known: dict[tuple[int, int], str]) -> None:
    identity = os.fstat(fd)
    key = (identity.st_dev, identity.st_ino)
    previous = known.setdefault(key, path)
    if previous != path:
        raise ArchiveAdmissionError(f"directory path aliases {previous}: {path}")


def _open_parent(
    root_fd: int,
    parts: list[str],
    created: list[tuple[str, bool]],
    *,
    create: bool = True,
    known_dirs: dict[tuple[int, int], str] | None = None,
) -> int:
    fd = os.dup(root_fd)
    try:
        current = []
        for part in parts:
            current.append(part)
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=fd)
                created.append(("/".join(current), True))
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            try:
                if known_dirs is not None:
                    _remember_directory(child, "/".join(current), known_dirs)
            except BaseException:
                os.close(child)
                raise
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _remove_created(root_fd: int, created: list[tuple[str, bool]]) -> None:
    for path, directory in reversed(created):
        parts = path.split("/")
        try:
            parent = _open_parent(root_fd, parts[:-1], [], create=False)
        except OSError:
            continue
        try:
            if directory:
                os.rmdir(parts[-1], dir_fd=parent)
            else:
                os.unlink(parts[-1], dir_fd=parent)
        except OSError:
            pass
        finally:
            os.close(parent)


def admit_archive(
    archive: str | Path,
    destination: str | Path,
    *,
    limits: ArchiveLimits | None = None,
) -> AdmissionReport:
    """Extract one strict gzip/ustar stream into an owned mode-0700 empty directory.

    Reject malformed input and remove files created by this call on failure.
    Directory spellings that resolve to one inode are rejected. Distinct names
    on a case-sensitive filesystem remain valid.
    The caller must prevent other processes with this effective UID from
    writing the archive or destination during admission.
    """
    if limits is None:
        limits = ArchiveLimits()
    root_fd = os.open(destination, _DIR_FLAGS)
    try:
        root_stat = os.fstat(root_fd)
        if root_stat.st_uid != os.geteuid() or stat.S_IMODE(root_stat.st_mode) != 0o700:
            raise ArchiveAdmissionError("destination must be owned and mode 0700")
        if os.listdir(root_fd):
            raise ArchiveAdmissionError("destination must be empty")
        archive_fd = os.open(archive, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            archive_stat = os.fstat(archive_fd)
            if not stat.S_ISREG(archive_stat.st_mode):
                raise ArchiveAdmissionError("archive must be a regular file")
            if archive_stat.st_size > limits.compressed_bytes:
                raise ArchiveAdmissionError("compressed archive exceeds limit")
            reader = _GzipReader(archive_fd, limits)
            created: list[tuple[str, bool]] = []
            known_dirs: dict[tuple[int, int], str] = {}
            seen: set[str] = set()
            members: list[AdmittedMember] = []
            headers = 0
            long_name: bytes | None = None
            try:
                while True:
                    header = reader.read(_BLOCK)
                    if header == bytes(_BLOCK):
                        if long_name is not None:
                            raise ArchiveAdmissionError("orphaned GNU long-name record")
                        if reader.read(_BLOCK) != bytes(_BLOCK):
                            raise ArchiveAdmissionError("invalid tar end blocks")
                        reader.finish_tar()
                        break
                    headers += 1
                    if headers > limits.members:
                        raise ArchiveAdmissionError("tar member count exceeds limit")
                    path, size, directory, extension = _member(header, limits, long_name)
                    if extension:
                        payload = reader.read(size)
                        if not payload.endswith(b"\0") or payload.rstrip(b"\0") + b"\0" != payload:
                            raise ArchiveAdmissionError("invalid GNU long-name payload")
                        long_name = payload[:-1]
                        padding = (-size) % _BLOCK
                        if padding and any(reader.read(padding)):
                            raise ArchiveAdmissionError("nonzero tar member padding")
                        continue
                    long_name = None
                    if path in seen:
                        raise ArchiveAdmissionError("duplicate tar path")
                    seen.add(path)
                    parts = path.split("/")
                    parent = _open_parent(root_fd, parts[:-1], created, known_dirs=known_dirs)
                    try:
                        if directory:
                            try:
                                os.mkdir(parts[-1], 0o700, dir_fd=parent)
                                created.append((path, True))
                            except FileExistsError:
                                pass
                            child = os.open(parts[-1], _DIR_FLAGS, dir_fd=parent)
                            try:
                                _remember_directory(child, path, known_dirs)
                            finally:
                                os.close(child)
                            members.append(AdmittedMember(path, 0, None))
                        else:
                            fd = os.open(parts[-1], _FILE_FLAGS, 0o600, dir_fd=parent)
                            created.append((path, False))
                            digest = hashlib.sha256()
                            try:
                                remaining = size
                                while remaining:
                                    chunk = reader.read(min(remaining, _CHUNK))
                                    digest.update(chunk)
                                    view = memoryview(chunk)
                                    while view:
                                        written = os.write(fd, view)
                                        if written == 0:
                                            raise OSError("short archive extraction write")
                                        view = view[written:]
                                    remaining -= len(chunk)
                            finally:
                                os.close(fd)
                            members.append(AdmittedMember(path, size, digest.hexdigest()))
                    finally:
                        os.close(parent)
                    padding = (-size) % _BLOCK
                    if padding and any(reader.read(padding)):
                        raise ArchiveAdmissionError("nonzero tar member padding")
                if reader.compressed != archive_stat.st_size:
                    raise ArchiveAdmissionError("archive size changed during admission")
                if not members:
                    raise ArchiveAdmissionError("archive has no members")
                return AdmissionReport(
                    reader.digest.hexdigest(), reader.compressed, reader.expanded, tuple(members)
                )
            except BaseException:
                _remove_created(root_fd, created)
                raise
        finally:
            os.close(archive_fd)
    finally:
        os.close(root_fd)

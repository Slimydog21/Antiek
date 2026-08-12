"""Filesystem layout for research artifact HTML (gitignored operator store)."""

from __future__ import annotations

import os
import re
import secrets
import stat
from contextlib import suppress
from pathlib import Path

_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def research_artifacts_dir() -> Path:
    raw = os.environ.get("ANTIEK_RESEARCH_ARTIFACTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".antiek" / "research-artifacts"


def snapshot_dir() -> Path:
    return research_artifacts_dir() / "snapshots"


def validate_artifact_id(artifact_id: str) -> str:
    """Return a storage-safe canonical id (never silently rewrite it)."""
    if not _ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise ValueError("invalid artifact id")
    return artifact_id


def artifact_path_for(artifact_id: str) -> Path:
    return research_artifacts_dir() / f"{validate_artifact_id(artifact_id)}.html"


def artifact_version_path_for(artifact_id: str, version: int) -> Path:
    if version < 1:
        raise ValueError("artifact version must be positive")
    return (
        research_artifacts_dir()
        / "versions"
        / validate_artifact_id(artifact_id)
        / f"v{version}.html"
    )


def artifact_source_path_for(artifact_id: str, content_hash: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ValueError("invalid source content hash")
    return (
        research_artifacts_dir()
        / "sources"
        / validate_artifact_id(artifact_id)
        / f"{content_hash}.html"
    )


def read_bounded_nofollow(path: Path, limit: int) -> bytes:
    """Descriptor-bound read: reject symlinks and size before allocation."""
    parent_fd, name = _open_parent_dir(path, create=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as err:
        os.close(parent_fd)
        raise ValueError("artifact cannot be opened safely") from err
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("artifact is not a regular file")
        if metadata.st_size > limit:
            raise OverflowError(f"artifact exceeds {limit} bytes")
        data = os.read(fd, limit + 1)
        if len(data) > limit:
            raise OverflowError(f"artifact exceeds {limit} bytes")
        return data
    finally:
        os.close(fd)
        os.close(parent_fd)


def unlink_anchored(path: Path, *, missing_ok: bool = True) -> None:
    """Unlink only after fd-anchored, no-follow parent traversal."""
    try:
        parent_fd, name = _open_parent_dir(path, create=False)
    except (FileNotFoundError, ValueError):
        if missing_ok:
            return
        raise
    try:
        try:
            os.unlink(name, dir_fd=parent_fd)
        except FileNotFoundError:
            if not missing_ok:
                raise
    finally:
        os.close(parent_fd)


def atomic_write_nofollow(path: Path, data: bytes) -> None:
    """Publish bytes atomically via an exclusive, fsynced sibling temp."""
    parent_fd, name = _open_parent_dir(path, create=True)
    temp_name = f".{name}.{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
    except BaseException:
        os.close(parent_fd)
        raise
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=parent_fd)
        os.close(parent_fd)
        raise
    else:
        os.close(fd)
    try:
        os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=parent_fd)
        raise
    finally:
        os.close(parent_fd)


def _open_parent_dir(path: Path, *, create: bool) -> tuple[int, str]:
    """Walk storage directories by fd, refusing symlink components."""
    root = research_artifacts_dir()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    root_absolute = Path(os.path.abspath(root))
    path_absolute = Path(os.path.abspath(path))
    try:
        relative = path_absolute.relative_to(root_absolute)
    except ValueError as err:
        raise ValueError("artifact storage path escapes configured root") from err
    parts = relative.parts
    if not parts:
        raise ValueError("artifact path must name a file")
    dir_fd = os.open(
        root_absolute,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        for part in parts[:-1]:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=dir_fd)
            next_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=dir_fd,
            )
            os.close(dir_fd)
            dir_fd = next_fd
        return dir_fd, parts[-1]
    except BaseException:
        os.close(dir_fd)
        raise


def compose_path_for(*investigation_ids: str) -> Path:
    joined = "-".join(i.replace("/", "_") for i in investigation_ids[:8])
    if len(investigation_ids) > 8:
        joined += f"-and{len(investigation_ids) - 8}-more"
    return research_artifacts_dir() / f"compose-{joined}.html"

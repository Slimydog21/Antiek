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
    """Descriptor-bound read: reject symlinks and size before allocation.

    O_NONBLOCK: opening a FIFO for reading blocks until a writer appears, and
    that open comes before the fstat that refuses non-regular files. It has no
    effect on reading a regular file."""
    parent_fd, name = _open_parent_dir(path, create=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    # Every descriptor is closed on every path out, whatever raises: a name
    # the OS rejects outright (an embedded NUL raises ValueError, not OSError)
    # must not leak the parent directory's descriptor.
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except (OSError, ValueError) as err:
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
    finally:
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
    """Publish bytes atomically via an exclusive, fsynced sibling temp.

    The parent directory's descriptor is closed on every path out, and a
    failed cleanup of the temp file never replaces the error that caused it:
    removing the temp is best effort, the original failure is what raises."""
    parent_fd, name = _open_parent_dir(path, create=True)
    try:
        temp_name = f".{name}.{secrets.token_hex(12)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        except BaseException:
            with suppress(OSError):
                os.unlink(temp_name, dir_fd=parent_fd)
            raise
        finally:
            os.close(fd)
        try:
            os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        except BaseException:
            with suppress(OSError):
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


def twin_notes_path_for(investigation_id: str) -> Path:
    safe = investigation_id.replace("/", "_")
    return research_artifacts_dir() / f"{safe}.notes.html"


def compose_path_for(*investigation_ids: str) -> Path:
    joined = "-".join(i.replace("/", "_") for i in investigation_ids[:8])
    if len(investigation_ids) > 8:
        joined += f"-and{len(investigation_ids) - 8}-more"
    return research_artifacts_dir() / f"compose-{joined}.html"


def draft_merge_path_for(*investigation_ids: str) -> Path:
    joined = "-".join(i.replace("/", "_") for i in investigation_ids[:8])
    if len(investigation_ids) > 8:
        joined += f"-and{len(investigation_ids) - 8}-more"
    return research_artifacts_dir() / f"draft-merge-{joined}.html"


_DRAFT_MERGE_NAME = re.compile(r"draft-merge-[^/\\]+\.html")
_CONFINED_READ_LIMIT = 10 * 1024 * 1024


def _read_confined_text(candidate: str, *, refusal: str, direct_child: re.Pattern[str] | None) -> str:
    """UTF-8 text of a file under the research artifacts directory, read
    through one descriptor anchored at that directory (no symlink component,
    no ``..`` escape, regular file, bounded). The check and the read are the
    same open, so the file cannot be swapped between them. Every refusal,
    present or missing, raises ``ValueError(refusal)``."""
    path = Path(os.path.abspath(candidate))
    if direct_child is not None and (
        path.parent != Path(os.path.abspath(research_artifacts_dir()))
        or not direct_child.fullmatch(path.name)
    ):
        raise ValueError(refusal)
    try:
        return read_bounded_nofollow(path, _CONFINED_READ_LIMIT).decode("utf-8")
    except (OSError, ValueError, OverflowError):
        raise ValueError(refusal) from None


def read_reviewed_draft_merge(candidate: str) -> str:
    """The text of the server-written draft-merge file ``candidate`` names.

    A source merge splices this file into a book's body, and the path arrives
    in a client's review packet. It may only name a draft this server wrote:
    a ``draft-merge-*.html`` directly inside the research artifacts directory.
    Anything else raises ``ValueError("source_merge_draft_merge_path_invalid")``.
    """
    return _read_confined_text(
        candidate, refusal="source_merge_draft_merge_path_invalid", direct_child=_DRAFT_MERGE_NAME
    )


def read_importable_artifact(candidate: str) -> str:
    """The text of a research artifact under the artifacts directory, for an
    HTTP notes import whose path arrives from the client. Anything outside it
    raises ``ValueError("import_notes_path_invalid")``."""
    return _read_confined_text(candidate, refusal="import_notes_path_invalid", direct_child=None)

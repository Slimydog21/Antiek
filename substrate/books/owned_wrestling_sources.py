"""Exact, owner-scoped book material for an owned wrestling action.

The source artifact is private data. Its digest is only a reference; the BYOT
journal, not possession of this file, decides whether a worker may spend.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from runtime.db_lock import connect_read
from substrate.books.serve_guard import (
    LinkBackMissingError,
    serve_full_text_guarded,
)
from substrate.rights import T3BodyServeError


class OwnedSourceUnavailable(RuntimeError):
    pass


@contextmanager
def owned_execution_guard(directory: Path, name: str) -> Iterator[bool]:
    """OS-proven active worker ownership; process death releases the claim."""
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in name):
        raise OwnedSourceUnavailable("execution identity is invalid")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_stat = directory.lstat()
    if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_mode & 0o077:
        raise OwnedSourceUnavailable("private execution directory is unavailable")
    fd = os.open(directory / f".execution-{name}.lock",
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    acquired = False
    try:
        file_stat = os.fstat(fd)
        if (not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1
            or file_stat.st_mode & 0o077):
            raise OwnedSourceUnavailable("private execution lock is invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        acquired = True
        yield True
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def source_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _read_private_file(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise OwnedSourceUnavailable("private artifact is unavailable") from exc
    with os.fdopen(fd, "rb") as source:
        file_stat = os.fstat(source.fileno())
        if (not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1
            or file_stat.st_mode & 0o077):
            raise OwnedSourceUnavailable("private artifact file is invalid")
        return source.read()


def current_book_material(db_path: str, *, owner: str, document_id: str) -> dict[str, Any]:
    """Read the actual body, rights state and every chunk under the graph gate."""
    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT d.owner_user_id,d.content_class,d.metadata,"
            "COALESCE(b.taken_down,FALSE) FROM documents d"
            " LEFT JOIN book_assets b ON b.document_id=d.document_id"
            " WHERE d.document_id=?", [document_id],
        ).fetchone()
        if row is None or row[0] != owner:
            raise OwnedSourceUnavailable("book owner differs or book is unavailable")
        try:
            served = serve_full_text_guarded(con, document_id, owner=True)
        except (T3BodyServeError, LinkBackMissingError) as exc:
            raise OwnedSourceUnavailable("book body is unavailable under its current rights") from exc
        if served.full_text is None or not served.full_text:
            raise OwnedSourceUnavailable("book body is unavailable under its current rights")
        body = served.full_text
        raw_chunks = con.execute(
            "SELECT chunk_id,chunk_index,section_path,text,token_count FROM chunks"
            " WHERE document_id=? ORDER BY chunk_index,chunk_id", [document_id],
        ).fetchall()
    finally:
        con.close()

    chunks: list[dict[str, Any]] = []
    for chunk_id, index, section, text, tokens in raw_chunks:
        if not text:
            raise OwnedSourceUnavailable("empty chunk has no source span")
        start = body.find(text)
        if start < 0 or body.find(text, start + 1) >= 0:
            raise OwnedSourceUnavailable("chunk has no unique exact body span")
        chunks.append({
            "chunk_id": chunk_id, "chunk_index": index, "section_path": section,
            "text": text, "token_count": tokens,
            "char_start": start, "char_end": start + len(text),
        })
    return {
        "schema": "antiek.owned-wrestling-source.v1",
        "document_id": document_id, "owner_user_id": owner,
        "content_class": row[1], "metadata_sha256": hashlib.sha256(
            str(row[2] or "").encode("utf-8")
        ).hexdigest(),
        "taken_down": bool(row[3]), "content_format": served.content_format,
        "rights_tier": served.tier, "license": served.license,
        "canonical_url": served.canonical_url,
        "body": body,
        "body_span": {"char_start": 0, "char_end": len(body)},
        "chunks": chunks,
    }


def write_immutable_artifact(directory: Path, name: str, value: dict[str, Any]) -> str:
    """Create once with private permissions; an orphan cannot authorize work."""
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in name):
        raise ValueError("artifact name is invalid")
    data = canonical_bytes(value)
    digest = hashlib.sha256(data).hexdigest()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_stat = directory.lstat()
    if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_mode & 0o077:
        raise OwnedSourceUnavailable("private artifact directory is unavailable")
    parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    path = directory / f"{name}.json"
    lock_fd = os.open(directory / f".{name}.lock",
                      os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        lock_stat = os.fstat(lock_fd)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1
            or lock_stat.st_mode & 0o077):
            raise OwnedSourceUnavailable("private artifact lock is invalid")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            if path.exists() or path.is_symlink():
                _recover_completed_link(directory, name, path)
                if _read_private_file(path) != data:
                    raise OwnedSourceUnavailable("immutable artifact differs")
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                return digest
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{name}-", suffix=".tmp", dir=directory,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
                os.link(temporary, path, follow_symlinks=False)
                temporary.unlink()
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                temporary.unlink(missing_ok=True)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        os.close(lock_fd)
    return digest


def _recover_completed_link(directory: Path, name: str, path: Path) -> None:
    """Finish only our already-fsynced hardlink after a crash before unlink."""
    try:
        final_stat = path.lstat()
    except OSError:
        return
    if not stat.S_ISREG(final_stat.st_mode) or final_stat.st_nlink != 2:
        return
    for candidate in directory.glob(f".{name}-*.tmp"):
        candidate_stat = candidate.lstat()
        if (stat.S_ISREG(candidate_stat.st_mode)
            and candidate_stat.st_dev == final_stat.st_dev
            and candidate_stat.st_ino == final_stat.st_ino):
            candidate.unlink()
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return


def read_immutable_artifact(directory: Path, name: str, digest: str) -> dict[str, Any]:
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in name):
        raise OwnedSourceUnavailable("artifact identity is invalid")
    path = directory / f"{name}.json"
    try:
        directory_stat = directory.lstat()
    except OSError as exc:
        raise OwnedSourceUnavailable("artifact directory is unavailable") from exc
    if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_mode & 0o077:
        raise OwnedSourceUnavailable("artifact link is invalid")
    data = _read_private_file(path)
    if hashlib.sha256(data).hexdigest() != digest:
        raise OwnedSourceUnavailable("artifact digest differs")
    value = json.loads(data)
    if not isinstance(value, dict) or canonical_bytes(value) != data:
        raise OwnedSourceUnavailable("artifact encoding differs")
    return value

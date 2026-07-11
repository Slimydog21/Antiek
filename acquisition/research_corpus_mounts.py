"""Open explicitly configured durable scholarly corpora without network access."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
from collections.abc import Callable
from pathlib import Path

from acquisition.core_cache import CoreCorpusAdapter, CoreSnapshotError
from acquisition.core_cache.store import _APPLICATION_ID as _CORE_APPLICATION_ID
from acquisition.core_cache.store import _record as _core_record
from acquisition.corpus_bridge import from_openalex, from_semantic_scholar
from acquisition.openalex_cache import OpenAlexSnapshotError
from acquisition.openalex_cache.store import _APPLICATION_ID as _OPENALEX_APPLICATION_ID
from acquisition.openalex_cache.store import _record as _openalex_record
from acquisition.s2_cache import S2SnapshotStore
from substrate.corpus_contract import CorpusAdapter
from substrate.corpus_federation import MountedCorpus

_KINDS = frozenset({"s2", "openalex", "core"})
type _ValidatedRecord = tuple[dict[str, object], str, str, float]


class MountConfigurationError(ValueError):
    """An explicit corpus mount declaration is malformed or unsafe."""


def _load_sqlite_snapshot_read_only(
    path: Path,
    *,
    application_id: int,
    validate: Callable[[object], _ValidatedRecord],
    error_type: type[ValueError],
) -> tuple[dict[str, object], ...]:
    """Read a sealed SQLite snapshot without initialization or sidecar writes."""
    before = path.lstat()
    if any(Path(f"{path}{suffix}").exists() for suffix in ("-journal", "-shm", "-wal")):
        raise error_type("cache database has an unsealed transaction sidecar")
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro&immutable=1",
            uri=True,
            timeout=10.0,
            isolation_level=None,
        )
        try:
            if connection.execute("PRAGMA query_only").fetchone() != (0,):
                raise error_type("cache database query-only state is incoherent")
            connection.execute("PRAGMA query_only = ON")
            if int(connection.execute("PRAGMA application_id").fetchone()[0]) != application_id:
                raise error_type("cache database application id mismatch")
            columns = tuple(
                (str(row[1]), str(row[2]).upper())
                for row in connection.execute("PRAGMA table_info(works)").fetchall()
            )
            if columns != (
                ("id", "TEXT"),
                ("payload", "TEXT"),
                ("digest", "TEXT"),
                ("fetched_at", "REAL"),
            ):
                raise error_type("cache database schema mismatch")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise error_type("cache database integrity check failed")
            rows = connection.execute(
                "SELECT id,payload,digest,fetched_at FROM works ORDER BY id"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise error_type("cache snapshot read failed") from exc
    after = path.lstat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if after_identity != before_identity:
        raise error_type("cache database changed during immutable read")

    records: list[dict[str, object]] = []
    for id, payload, digest, fetched_at in rows:
        if type(payload) is not str or hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
            raise error_type("cache payload digest mismatch")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise error_type("cache payload JSON is invalid") from exc
        record, canonical, expected_digest, timestamp = validate(decoded)
        if record["id"] != id or canonical != payload or expected_digest != digest:
            raise error_type("cache payload identity or canonical form mismatch")
        if timestamp != fetched_at:
            raise error_type("cache fetched_at column mismatch")
        records.append(record)
    return tuple(records)


def load_research_corpus_mounts(values: list[str]) -> tuple[MountedCorpus, ...]:
    """Validate and open repeatable ``KIND=PATH`` read-only authorities.

    A mount path must be a real directory rather than a symlink, and its
    authoritative snapshot pointer/database must be a real file. Snapshot
    loaders retain responsibility for validating the contents.
    """
    if type(values) is not list or not values or len(values) > len(_KINDS):
        raise MountConfigurationError("one unique mount per supported kind is required")
    parsed: list[tuple[str, Path]] = []
    for value in values:
        if type(value) is not str or value.count("=") != 1:
            raise MountConfigurationError("mount must be KIND=PATH")
        kind, raw_path = value.split("=", 1)
        path = Path(raw_path)
        if kind not in _KINDS or not raw_path or not path.is_dir() or path.is_symlink():
            raise MountConfigurationError("mount kind or path is invalid")
        directory_info = path.lstat()
        if not stat.S_ISDIR(directory_info.st_mode) or stat.S_IMODE(directory_info.st_mode) & 0o077:
            raise MountConfigurationError("mount directory must be private")
        authority = path / ("CURRENT" if kind == "s2" else "works.sqlite3")
        if not authority.is_file() or authority.is_symlink():
            raise MountConfigurationError("mount authority does not exist")
        authority_info = authority.lstat()
        if (
            not stat.S_ISREG(authority_info.st_mode)
            or authority_info.st_nlink != 1
            or stat.S_IMODE(authority_info.st_mode) & 0o077
        ):
            raise MountConfigurationError("mount authority must be a private single-link file")
        parsed.append((kind, path))
    names = tuple(kind for kind, _ in parsed)
    if len(names) != len(set(names)):
        raise MountConfigurationError("mount kinds must be unique")

    mounts: list[MountedCorpus] = []
    for kind, path in parsed:
        adapter: CorpusAdapter
        if kind == "s2":
            adapter = from_semantic_scholar(S2SnapshotStore(path).load())
        elif kind == "openalex":
            adapter = from_openalex(
                _load_sqlite_snapshot_read_only(
                    path / "works.sqlite3",
                    application_id=_OPENALEX_APPLICATION_ID,
                    validate=_openalex_record,
                    error_type=OpenAlexSnapshotError,
                )
            )
        else:
            adapter = CoreCorpusAdapter(
                _load_sqlite_snapshot_read_only(
                    path / "works.sqlite3",
                    application_id=_CORE_APPLICATION_ID,
                    validate=_core_record,
                    error_type=CoreSnapshotError,
                )
            )
        mounts.append(MountedCorpus(kind, adapter))
    return tuple(mounts)

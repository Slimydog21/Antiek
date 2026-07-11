"""Private, tamper-evident SQLite authority for CORE metadata snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .adapter import CoreCorpusAdapter

_APPLICATION_ID = 0x41434F52  # ACOR
_FIELDS = frozenset(
    {"id", "title", "abstract", "doi", "arxiv_id", "authors", "declared_license", "fetched_at", "source"}
)


class CoreSnapshotError(ValueError):
    """A CORE record or local snapshot violated the authority contract."""


def _optional_text(raw: dict[str, object], field: str) -> None:
    value = raw[field]
    if value is not None and (type(value) is not str or not value.strip()):
        raise CoreSnapshotError(f"{field} must be null or a nonempty exact str")


def _record(value: object) -> tuple[dict[str, object], str, str, float]:
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise CoreSnapshotError("CORE record must have exact frozen fields")
    raw = cast(dict[str, object], value)
    if raw["source"] != "core":
        raise CoreSnapshotError("CORE record source mismatch")
    for field in ("id", "title"):
        if type(raw[field]) is not str or not str(raw[field]).strip():
            raise CoreSnapshotError(f"{field} must be a nonempty exact str")
    for field in ("abstract", "doi", "arxiv_id", "declared_license"):
        _optional_text(raw, field)
    authors = raw["authors"]
    if type(authors) is not list or any(
        type(author) is not str or not author.strip() for author in authors
    ):
        raise CoreSnapshotError("authors must be an exact list of nonempty strings")
    fetched = raw["fetched_at"]
    if type(fetched) not in {int, float} or isinstance(fetched, bool):
        raise CoreSnapshotError("fetched_at must be a finite nonnegative timestamp")
    timestamp = float(cast(int | float, fetched))
    if not math.isfinite(timestamp) or timestamp < 0:
        raise CoreSnapshotError("fetched_at must be a finite nonnegative timestamp")
    # Exercise the actual read boundary before publication.
    try:
        CoreCorpusAdapter((raw,)).fetch(str(raw["id"]))
    except ValueError as error:
        raise CoreSnapshotError("CORE record failed corpus validation") from error
    canonical = json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return raw, canonical, hashlib.sha256(canonical.encode()).hexdigest(), timestamp


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise CoreSnapshotError("cache path must be a real directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise CoreSnapshotError("cache directory must be private")
    return path


class CoreSnapshotStore:
    def __init__(self, cache_dir: Path) -> None:
        if not isinstance(cache_dir, Path):
            raise CoreSnapshotError("cache_dir must be a pathlib Path")
        self.cache_dir = _private_directory(cache_dir)
        self._path = self.cache_dir / "works.sqlite3"
        if self._path.is_symlink():
            raise CoreSnapshotError("cache database must not be a symlink")
        if self._path.exists():
            info = self._path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise CoreSnapshotError("cache database must be a single-link regular file")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise CoreSnapshotError("cache database must be private")
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self._path, timeout=10.0, isolation_level=None)
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as error:
            raise CoreSnapshotError("cache database is unavailable") from error

    def _initialize(self) -> None:
        existed = self._path.exists()
        connection = self._connect()
        try:
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            if application_id not in {0, _APPLICATION_ID}:
                raise CoreSnapshotError("cache database application id mismatch")
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS works (id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                "digest TEXT NOT NULL, fetched_at REAL NOT NULL CHECK(fetched_at >= 0))"
            )
            columns = tuple(
                (str(row[1]), str(row[2]).upper())
                for row in connection.execute("PRAGMA table_info(works)").fetchall()
            )
            if columns != (("id", "TEXT"), ("payload", "TEXT"), ("digest", "TEXT"), ("fetched_at", "REAL")):
                raise CoreSnapshotError("cache database schema mismatch")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise CoreSnapshotError("cache database integrity check failed")
        except sqlite3.Error as error:
            raise CoreSnapshotError("cache database initialization failed") from error
        finally:
            connection.close()
        if not existed:
            os.chmod(self._path, 0o600)
        info = self._path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise CoreSnapshotError("cache database path or permissions are unsafe")

    def load(self) -> tuple[dict[str, object], ...]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT id,payload,digest,fetched_at FROM works ORDER BY id").fetchall()
        except sqlite3.Error as error:
            raise CoreSnapshotError("cache snapshot read failed") from error
        finally:
            connection.close()
        records: list[dict[str, object]] = []
        for id, payload, digest, fetched_at in rows:
            if type(payload) is not str or hashlib.sha256(payload.encode()).hexdigest() != digest:
                raise CoreSnapshotError("cache payload digest mismatch")
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError as error:
                raise CoreSnapshotError("cache payload JSON is invalid") from error
            record, canonical, expected_digest, timestamp = _record(decoded)
            if record["id"] != id or canonical != payload or expected_digest != digest:
                raise CoreSnapshotError("cache payload identity or canonical form mismatch")
            if timestamp != fetched_at:
                raise CoreSnapshotError("cache fetched_at column mismatch")
            records.append(record)
        return tuple(records)

    def publish(self, records: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
        if type(records) is not tuple or any(type(item) is not dict for item in records):
            raise CoreSnapshotError("records must be an exact tuple of exact dicts")
        normalized = tuple(_record(item) for item in records)
        ids = tuple(str(item[0]["id"]) for item in normalized)
        if len(ids) != len(set(ids)):
            raise CoreSnapshotError("provider response contains duplicate id")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for record, payload, digest, timestamp in normalized:
                connection.execute(
                    "INSERT INTO works VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "payload=excluded.payload,digest=excluded.digest,fetched_at=excluded.fetched_at "
                    "WHERE excluded.fetched_at >= works.fetched_at",
                    (record["id"], payload, digest, timestamp),
                )
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise CoreSnapshotError("cache snapshot publication failed") from error
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.load()

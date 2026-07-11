"""Authoritative SQLite snapshot for validated OpenAlex work records."""

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

from acquisition.corpus_bridge import from_openalex

_APPLICATION_ID = 0x414F4158  # AOAX
_FIELDS = frozenset({"id", "title", "abstract_inverted_index", "fetched_at"})


class OpenAlexSnapshotError(ValueError):
    """A provider record or authoritative snapshot violated the contract."""


def _record(value: object) -> tuple[dict[str, object], str, str, float]:
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise OpenAlexSnapshotError("OpenAlex record must have exact frozen fields")
    raw = cast(dict[str, object], value)
    # The corpus normalizer performs exact id/title/abstract validation.
    try:
        from_openalex((raw,))
    except ValueError as error:
        raise OpenAlexSnapshotError("OpenAlex record failed corpus validation") from error
    fetched = raw["fetched_at"]
    if type(fetched) not in {int, float} or isinstance(fetched, bool):
        raise OpenAlexSnapshotError("fetched_at must be a finite nonnegative timestamp")
    timestamp = float(cast(int | float, fetched))
    if not math.isfinite(timestamp) or timestamp < 0:
        raise OpenAlexSnapshotError("fetched_at must be a finite nonnegative timestamp")
    canonical = json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return raw, canonical, digest, timestamp


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise OpenAlexSnapshotError("cache path must be a real directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise OpenAlexSnapshotError("cache directory must not grant group/other permissions")
    return path


class OpenAlexSnapshotStore:
    def __init__(self, cache_dir: Path) -> None:
        if not isinstance(cache_dir, Path):
            raise OpenAlexSnapshotError("cache_dir must be a pathlib Path")
        self.cache_dir = _private_directory(cache_dir)
        self._path = self.cache_dir / "works.sqlite3"
        if self._path.is_symlink():
            raise OpenAlexSnapshotError("cache database must not be a symlink")
        if self._path.exists():
            info = self._path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OpenAlexSnapshotError("cache database must be a single-link regular file")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise OpenAlexSnapshotError("cache database permissions are not private")
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self._path, timeout=10.0, isolation_level=None)
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as error:
            raise OpenAlexSnapshotError("cache database is unavailable") from error

    def _initialize(self) -> None:
        existed = self._path.exists()
        connection = self._connect()
        try:
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            if application_id not in {0, _APPLICATION_ID}:
                raise OpenAlexSnapshotError("cache database application id mismatch")
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS works ("
                "id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, "
                "fetched_at REAL NOT NULL CHECK(fetched_at >= 0))"
            )
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
                raise OpenAlexSnapshotError("cache database schema mismatch")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise OpenAlexSnapshotError("cache database integrity check failed")
        except sqlite3.Error as error:
            raise OpenAlexSnapshotError("cache database initialization failed") from error
        finally:
            connection.close()
        if not existed:
            os.chmod(self._path, 0o600)
        info = self._path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OpenAlexSnapshotError("cache database must be a single-link regular file")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise OpenAlexSnapshotError("cache database permissions are not private")

    def load(self) -> tuple[dict[str, object], ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id,payload,digest,fetched_at FROM works ORDER BY id"
            ).fetchall()
        except sqlite3.Error as error:
            raise OpenAlexSnapshotError("cache snapshot read failed") from error
        finally:
            connection.close()
        records: list[dict[str, object]] = []
        for id, payload, digest, fetched_at in rows:
            if (
                type(payload) is not str
                or hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest
            ):
                raise OpenAlexSnapshotError("cache payload digest mismatch")
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError as error:
                raise OpenAlexSnapshotError("cache payload JSON is invalid") from error
            record, canonical, expected_digest, timestamp = _record(decoded)
            if record["id"] != id or canonical != payload or expected_digest != digest:
                raise OpenAlexSnapshotError("cache payload identity or canonical form mismatch")
            if timestamp != fetched_at:
                raise OpenAlexSnapshotError("cache fetched_at column mismatch")
            records.append(record)
        return tuple(records)

    def publish(self, records: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
        if type(records) is not tuple or any(type(item) is not dict for item in records):
            raise OpenAlexSnapshotError("records must be an exact tuple of exact dicts")
        normalized = tuple(_record(item) for item in records)
        ids = tuple(str(item[0]["id"]) for item in normalized)
        if len(ids) != len(set(ids)):
            raise OpenAlexSnapshotError("provider response contains duplicate id")
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
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.load()

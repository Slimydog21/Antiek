"""Crash-safe, private SQLite snapshots for Substack feed records."""

from __future__ import annotations

import math
import os
import sqlite3
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import cast

_APPLICATION_ID = 0x4153544B  # ASTK
_SCHEMA = (
    ("url", "TEXT"),
    ("title", "TEXT"),
    ("body_html", "TEXT"),
    ("accessible", "INTEGER"),
    ("fetched_at", "REAL"),
    ("publication", "TEXT"),
)
_FIELDS = frozenset({name for name, _ in _SCHEMA})


class SubstackSnapshotError(ValueError):
    """A feed record or durable cache violated the snapshot contract."""


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise SubstackSnapshotError(f"{field} must be a trimmed nonempty exact str")
    return value


def _record(value: object) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise SubstackSnapshotError("Substack snapshot record must have exact frozen fields")
    raw = cast(dict[str, object], value)
    accessible = raw["accessible"]
    if type(accessible) is not bool:
        raise SubstackSnapshotError("accessible must be an exact bool")
    body = raw["body_html"]
    if accessible and (type(body) is not str or not body.strip()):
        raise SubstackSnapshotError("accessible record requires nonempty body_html")
    if not accessible and body is not None:
        raise SubstackSnapshotError("inaccessible record must not retain body_html")
    fetched = raw["fetched_at"]
    if type(fetched) not in {int, float} or isinstance(fetched, bool):
        raise SubstackSnapshotError("fetched_at must be a finite nonnegative timestamp")
    timestamp = float(cast(int | float, fetched))
    if not math.isfinite(timestamp) or timestamp < 0:
        raise SubstackSnapshotError("fetched_at must be a finite nonnegative timestamp")
    return {
        "url": _text(raw["url"], "url"),
        "title": _text(raw["title"], "title"),
        "body_html": body,
        "accessible": accessible,
        "fetched_at": timestamp,
        "publication": _text(raw["publication"], "publication"),
    }


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise SubstackSnapshotError("cache path must be a real directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise SubstackSnapshotError("cache directory must not grant group/other permissions")
    return path


class SubstackSnapshotStore:
    def __init__(self, cache_dir: Path) -> None:
        if not isinstance(cache_dir, Path):
            raise SubstackSnapshotError("cache_dir must be a pathlib Path")
        directory = _private_directory(cache_dir)
        self._path = directory / "feed.sqlite3"
        if self._path.is_symlink():
            raise SubstackSnapshotError("cache database must not be a symlink")
        if self._path.exists():
            info = self._path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise SubstackSnapshotError("cache database must be a single-link regular file")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise SubstackSnapshotError("cache database must not grant group/other permissions")
        self._initialize()

    @property
    def cache_dir(self) -> Path:
        return self._path.parent

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self._path, timeout=10.0, isolation_level=None)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as error:
            raise SubstackSnapshotError("cache database is unavailable") from error

    def _initialize(self) -> None:
        existed = self._path.exists()
        connection = self._connect()
        try:
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            if application_id not in {0, _APPLICATION_ID}:
                raise SubstackSnapshotError("cache database application id mismatch")
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS posts ("
                "url TEXT PRIMARY KEY, title TEXT NOT NULL, body_html TEXT, "
                "accessible INTEGER NOT NULL CHECK(accessible IN (0,1)), "
                "fetched_at REAL NOT NULL CHECK(fetched_at >= 0), publication TEXT NOT NULL)"
            )
            columns = tuple(
                (str(row[1]), str(row[2]).upper())
                for row in connection.execute("PRAGMA table_info(posts)").fetchall()
            )
            if columns != _SCHEMA:
                raise SubstackSnapshotError("cache database schema mismatch")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise SubstackSnapshotError("cache database integrity check failed")
        except sqlite3.Error as error:
            raise SubstackSnapshotError("cache database initialization failed") from error
        finally:
            connection.close()
        if not existed:
            os.chmod(self._path, 0o600)
        info = self._path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SubstackSnapshotError("cache database must be a single-link regular file")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise SubstackSnapshotError("cache database must not grant group/other permissions")

    def load(self) -> tuple[dict[str, object], ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT url,title,body_html,accessible,fetched_at,publication "
                "FROM posts ORDER BY url"
            ).fetchall()
        except sqlite3.Error as error:
            raise SubstackSnapshotError("cache snapshot read failed") from error
        finally:
            connection.close()
        return tuple(
            _record(
                {
                    "url": row[0],
                    "title": row[1],
                    "body_html": row[2],
                    "accessible": bool(row[3]),
                    "fetched_at": row[4],
                    "publication": row[5],
                }
            )
            for row in rows
        )

    def publish(self, records: tuple[Mapping[str, object], ...]) -> tuple[dict[str, object], ...]:
        if type(records) is not tuple or any(type(item) is not dict for item in records):
            raise SubstackSnapshotError("records must be an exact tuple of exact dicts")
        normalized = tuple(_record(item) for item in records)
        ids = tuple(str(item["url"]) for item in normalized)
        if len(ids) != len(set(ids)):
            raise SubstackSnapshotError("feed contains duplicate URL")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for item in normalized:
                connection.execute(
                    "INSERT INTO posts VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET title=excluded.title, "
                    "body_html=excluded.body_html, accessible=excluded.accessible, "
                    "fetched_at=excluded.fetched_at, publication=excluded.publication "
                    "WHERE excluded.fetched_at >= posts.fetched_at",
                    (
                        item["url"],
                        item["title"],
                        item["body_html"],
                        int(bool(item["accessible"])),
                        item["fetched_at"],
                        item["publication"],
                    ),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.load()

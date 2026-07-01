"""Catalog backend abstraction — InMemory + SQLite implementations.

The catalog stores `(user_id, db_path, encryption_key_ref, shard_id,
last_size_bytes, updated_at)`. Production wires PostgresCatalogBackend
once the operator decides multi-tenant catalog Postgres is online.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CatalogEntry:
    user_id: str
    db_path: str
    encryption_key_ref: str | None
    shard_id: str | None
    last_size_bytes: int
    updated_at: str


class CatalogBackend(Protocol):
    def upsert(self, entry: CatalogEntry) -> None: ...
    def get(self, user_id: str) -> CatalogEntry | None: ...
    def all(self) -> list[CatalogEntry]: ...
    def remove(self, user_id: str) -> bool: ...


@dataclass
class InMemoryCatalogBackend:
    """Process-local catalog. Loses state on restart — for tests + the
    Stage-1 transition window where the catalog table is still being
    designed in."""

    entries: dict[str, CatalogEntry] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert(self, entry: CatalogEntry) -> None:
        with self._lock:
            self.entries[entry.user_id] = entry

    def get(self, user_id: str) -> CatalogEntry | None:
        with self._lock:
            return self.entries.get(user_id)

    def all(self) -> list[CatalogEntry]:
        with self._lock:
            return list(self.entries.values())

    def remove(self, user_id: str) -> bool:
        with self._lock:
            return self.entries.pop(user_id, None) is not None


@dataclass
class SqliteCatalogBackend:
    """SQLite-backed catalog. Survives process restart; promotes to
    Postgres by re-pointing the connection. Single-table schema."""

    db_path: str
    _conn: sqlite3.Connection | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS catalog_entries (
                user_id TEXT PRIMARY KEY,
                db_path TEXT NOT NULL,
                encryption_key_ref TEXT,
                shard_id TEXT,
                last_size_bytes INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def upsert(self, entry: CatalogEntry) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("""
                INSERT INTO catalog_entries
                  (user_id, db_path, encryption_key_ref, shard_id, last_size_bytes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  db_path=excluded.db_path,
                  encryption_key_ref=excluded.encryption_key_ref,
                  shard_id=excluded.shard_id,
                  last_size_bytes=excluded.last_size_bytes,
                  updated_at=excluded.updated_at
            """, (
                entry.user_id, entry.db_path, entry.encryption_key_ref,
                entry.shard_id, entry.last_size_bytes, entry.updated_at,
            ))
            self._conn.commit()

    def get(self, user_id: str) -> CatalogEntry | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, db_path, encryption_key_ref, shard_id, last_size_bytes, updated_at "
                "FROM catalog_entries WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return CatalogEntry(*row)

    def all(self) -> list[CatalogEntry]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                "SELECT user_id, db_path, encryption_key_ref, shard_id, last_size_bytes, updated_at "
                "FROM catalog_entries"
            ).fetchall()
        return [CatalogEntry(*r) for r in rows]

    def remove(self, user_id: str) -> bool:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM catalog_entries WHERE user_id = ?",
                (user_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0


def _coerce_updated_at(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


@dataclass
class PostgresCatalogBackend:
    """Postgres-backed catalog for the production DuckLake Stage 1 wiring.

    ``psycopg`` is imported lazily so local/dev users keep the SQLite
    stand-in without installing a Postgres driver. Production passes ``dsn``;
    tests can pass a DB-API-like ``conn`` with ``execute`` + ``commit``.
    """

    dsn: str | None = None
    conn: Any | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.conn is None:
            if not self.dsn:
                raise ValueError("PostgresCatalogBackend requires dsn or conn")
            try:
                import psycopg  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "PostgresCatalogBackend requires psycopg; install "
                    "`antiek[postgres]` on the production host",
                ) from exc
            self.conn = psycopg.connect(self.dsn)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS catalog_entries (
                user_id TEXT PRIMARY KEY,
                db_path TEXT NOT NULL,
                encryption_key_ref TEXT,
                shard_id TEXT,
                last_size_bytes BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL
            )
        """)
        self.conn.commit()

    def upsert(self, entry: CatalogEntry) -> None:
        assert self.conn is not None
        with self._lock:
            self.conn.execute("""
                INSERT INTO catalog_entries
                  (user_id, db_path, encryption_key_ref, shard_id, last_size_bytes, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE SET
                  db_path=excluded.db_path,
                  encryption_key_ref=excluded.encryption_key_ref,
                  shard_id=excluded.shard_id,
                  last_size_bytes=excluded.last_size_bytes,
                  updated_at=excluded.updated_at
            """, (
                entry.user_id, entry.db_path, entry.encryption_key_ref,
                entry.shard_id, entry.last_size_bytes, entry.updated_at,
            ))
            self.conn.commit()

    def get(self, user_id: str) -> CatalogEntry | None:
        assert self.conn is not None
        with self._lock:
            cur = self.conn.execute(
                "SELECT user_id, db_path, encryption_key_ref, shard_id, last_size_bytes, updated_at "
                "FROM catalog_entries WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return CatalogEntry(
            user_id=row[0],
            db_path=row[1],
            encryption_key_ref=row[2],
            shard_id=row[3],
            last_size_bytes=row[4],
            updated_at=_coerce_updated_at(row[5]),
        )

    def all(self) -> list[CatalogEntry]:
        assert self.conn is not None
        with self._lock:
            cur = self.conn.execute(
                "SELECT user_id, db_path, encryption_key_ref, shard_id, last_size_bytes, updated_at "
                "FROM catalog_entries"
            )
            rows = cur.fetchall()
        return [
            CatalogEntry(
                user_id=r[0],
                db_path=r[1],
                encryption_key_ref=r[2],
                shard_id=r[3],
                last_size_bytes=r[4],
                updated_at=_coerce_updated_at(r[5]),
            )
            for r in rows
        ]

    def remove(self, user_id: str) -> bool:
        assert self.conn is not None
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM catalog_entries WHERE user_id = %s",
                (user_id,),
            )
            self.conn.commit()
            return cur.rowcount > 0


@dataclass
class DuckLakeCatalog:
    """The catalog facade the GraphRouter consults at Stage 2."""

    backend: CatalogBackend

    def register(
        self,
        *,
        user_id: str,
        db_path: str,
        encryption_key_ref: str | None = None,
        shard_id: str | None = None,
        last_size_bytes: int = 0,
    ) -> CatalogEntry:
        entry = CatalogEntry(
            user_id=user_id,
            db_path=db_path,
            encryption_key_ref=encryption_key_ref,
            shard_id=shard_id,
            last_size_bytes=last_size_bytes,
            updated_at=_now_iso(),
        )
        self.backend.upsert(entry)
        return entry

    def lookup(self, user_id: str) -> CatalogEntry | None:
        return self.backend.get(user_id)

    def list_all(self) -> list[CatalogEntry]:
        return self.backend.all()

    def deregister(self, user_id: str) -> bool:
        return self.backend.remove(user_id)

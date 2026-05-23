"""Per-user telemetry-preference storage + DP shuffler integration."""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class UserTelemetryPreferences:
    """The shape one (user_id, surface_name) row takes."""

    user_id: str
    surface_name: str
    enabled: bool
    updated_at: str


class PreferenceStore(Protocol):
    def upsert(self, pref: UserTelemetryPreferences) -> None: ...
    def get(self, *, user_id: str, surface_name: str) -> Optional[UserTelemetryPreferences]: ...
    def list_for_user(self, user_id: str) -> list[UserTelemetryPreferences]: ...
    def delete_for_user(self, user_id: str) -> int: ...


@dataclass
class InMemoryPreferenceStore:
    """Process-local store. Tests + the Stage-0 transition window."""

    rows: dict[tuple[str, str], UserTelemetryPreferences] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert(self, pref: UserTelemetryPreferences) -> None:
        with self._lock:
            self.rows[(pref.user_id, pref.surface_name)] = pref

    def get(
        self, *, user_id: str, surface_name: str,
    ) -> Optional[UserTelemetryPreferences]:
        with self._lock:
            return self.rows.get((user_id, surface_name))

    def list_for_user(self, user_id: str) -> list[UserTelemetryPreferences]:
        with self._lock:
            return [
                p for (uid, _surf), p in self.rows.items()
                if uid == user_id
            ]

    def delete_for_user(self, user_id: str) -> int:
        with self._lock:
            keys = [k for k in self.rows if k[0] == user_id]
            for k in keys:
                del self.rows[k]
            return len(keys)


@dataclass
class SqlitePreferenceStore:
    """SQLite-backed store. Survives restart; promotable to Postgres
    by re-pointing the connection."""

    db_path: str
    _conn: Optional[sqlite3.Connection] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_telemetry_preferences (
                user_id TEXT NOT NULL,
                surface_name TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, surface_name)
            )
        """)
        self._conn.commit()

    def upsert(self, pref: UserTelemetryPreferences) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("""
                INSERT INTO user_telemetry_preferences
                    (user_id, surface_name, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, surface_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
            """, (pref.user_id, pref.surface_name,
                  1 if pref.enabled else 0, pref.updated_at))
            self._conn.commit()

    def get(
        self, *, user_id: str, surface_name: str,
    ) -> Optional[UserTelemetryPreferences]:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute("""
                SELECT user_id, surface_name, enabled, updated_at
                FROM user_telemetry_preferences
                WHERE user_id = ? AND surface_name = ?
            """, (user_id, surface_name)).fetchone()
        if row is None:
            return None
        return UserTelemetryPreferences(
            user_id=row[0],
            surface_name=row[1],
            enabled=bool(row[2]),
            updated_at=row[3],
        )

    def list_for_user(self, user_id: str) -> list[UserTelemetryPreferences]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute("""
                SELECT user_id, surface_name, enabled, updated_at
                FROM user_telemetry_preferences
                WHERE user_id = ?
            """, (user_id,)).fetchall()
        return [
            UserTelemetryPreferences(
                user_id=r[0], surface_name=r[1],
                enabled=bool(r[2]), updated_at=r[3],
            ) for r in rows
        ]

    def delete_for_user(self, user_id: str) -> int:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.execute("""
                DELETE FROM user_telemetry_preferences WHERE user_id = ?
            """, (user_id,))
            self._conn.commit()
            return cur.rowcount


def is_enabled(
    store: PreferenceStore,
    *,
    user_id: str,
    surface_name: str,
    default_when_missing: bool = True,
) -> bool:
    """The predicate the DP shuffler calls before emitting telemetry.

    `default_when_missing` is the policy when no explicit preference
    has been recorded. Callers pass the EpsilonRegistry's
    `opt_in_required` inverted: opt-in-required surfaces default to
    False; everything else defaults to True.
    """
    existing = store.get(user_id=user_id, surface_name=surface_name)
    if existing is None:
        return default_when_missing
    return existing.enabled


def set_preference(
    store: PreferenceStore,
    *,
    user_id: str,
    surface_name: str,
    enabled: bool,
) -> UserTelemetryPreferences:
    """Upsert one preference row."""
    pref = UserTelemetryPreferences(
        user_id=user_id,
        surface_name=surface_name,
        enabled=enabled,
        updated_at=_now_iso(),
    )
    store.upsert(pref)
    return pref


def list_preferences(
    store: PreferenceStore,
    *,
    user_id: str,
) -> list[UserTelemetryPreferences]:
    return store.list_for_user(user_id)


def apply_defaults_from_registry(
    store: PreferenceStore,
    *,
    user_id: str,
    registry,  # avoid circular import; substrate.dp_shuffler.EpsilonRegistry
) -> int:
    """Seed a user's preferences from the registry's defaults.

    For each surface:
    - If opt_in_required AND no existing pref → write FALSE
    - If NOT opt_in_required AND no existing pref → write TRUE
    - If pref already exists → skip (user's explicit choice wins)

    Returns the number of preferences seeded."""
    seeded = 0
    for surface in registry.list_surfaces():
        existing = store.get(user_id=user_id, surface_name=surface.surface_name)
        if existing is not None:
            continue
        default_enabled = not surface.opt_in_required
        if surface.sensitivity == "forbidden":
            default_enabled = False
        set_preference(
            store,
            user_id=user_id,
            surface_name=surface.surface_name,
            enabled=default_enabled,
        )
        seeded += 1
    return seeded

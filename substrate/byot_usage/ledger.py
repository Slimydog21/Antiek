"""Per-key BYOT usage ledger — sidecar tracking of API-key spend.

Mirrors the discipline of ``substrate/research_spend/ledger.py``:
SQLite WAL, single-writer, respects ``runtime/db_lock``.

Each row tracks one API key's cumulative ``used_cents`` (incremented by
settle events from the research-spend ledger) and an optional
user-set ``limit_cents`` spend cap.  The ledger is a sidecar — it does
not rewrite the audited core schema.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

__all__ = [
    "ByotUsageLedger",
    "KeyUsageRow",
]

_SCHEMA_VERSION: Final = 1
_BUSY_TIMEOUT_MS: Final = 30_000


def default_byot_usage_db_path() -> Path:
    """Resolve the sidecar DB path, co-located with the research-spend DB."""
    configured = os.environ.get("ANTIEK_BYOT_USAGE_DB")
    if configured:
        return Path(configured).expanduser()
    from substrate.research_spend.ledger import default_research_spend_db_path

    spend_db = default_research_spend_db_path()
    return spend_db.with_name(f"{spend_db.name}.byot-usage.sqlite3")


@dataclass(frozen=True, slots=True)
class KeyUsageRow:
    """Read-only snapshot of one key's usage state."""

    api_key_id: str
    owner_user_id: str
    used_cents: int
    limit_cents: int | None
    last_settled_at: str | None
    updated_at: str

    @property
    def remaining_cents(self) -> int | None:
        """Remaining budget, or ``None`` if no limit is set."""
        if self.limit_cents is None:
            return None
        return max(0, self.limit_cents - self.used_cents)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ByotUsageLedger:
    """Per-key usage accumulator backed by a small SQLite sidecar.

    Thread-safe for single-writer use (the caller serialises through
    ``runtime.db_lock`` or process-level single-writer discipline).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        busy_timeout_ms: int = _BUSY_TIMEOUT_MS,
    ) -> None:
        self._db_path = str(db_path) if db_path else str(default_byot_usage_db_path())
        self._busy_timeout_ms = busy_timeout_ms
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path, timeout=self._busy_timeout_ms / 1000)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        return con

    def _ensure_schema(self) -> None:
        con = self._connect()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS byot_usage_meta ("
                "  key TEXT PRIMARY KEY, value TEXT NOT NULL"
                ")"
            )
            row = con.execute(
                "SELECT value FROM byot_usage_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO byot_usage_meta (key, value) VALUES ('schema_version', ?)",
                    (str(_SCHEMA_VERSION),),
                )
            con.execute(
                "CREATE TABLE IF NOT EXISTS byot_key_usage ("
                "  api_key_id TEXT NOT NULL,"
                "  owner_user_id TEXT NOT NULL,"
                "  used_cents INTEGER NOT NULL DEFAULT 0,"
                "  limit_cents INTEGER,"
                "  last_settled_at TEXT,"
                "  updated_at TEXT NOT NULL,"
                "  PRIMARY KEY (api_key_id, owner_user_id)"
                ")"
            )
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def record_settlement(
        self,
        api_key_id: str,
        owner_user_id: str,
        actual_cents: int,
        evidence_sha256: str,
    ) -> None:
        """Increment ``used_cents`` for a key after a successful settle.

        Called from the research-spend ledger's settle path.  The
        ``evidence_sha256`` is recorded for auditability but does not
        affect the accumulated total.
        """
        if actual_cents < 0:
            raise ValueError("actual_cents must be non-negative")
        if not api_key_id:
            raise ValueError("api_key_id must be non-empty")
        if not owner_user_id:
            raise ValueError("owner_user_id must be non-empty")
        now = _now_iso()
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO byot_key_usage"
                "  (api_key_id, owner_user_id, used_cents, last_settled_at, updated_at)"
                "  VALUES (?, ?, ?, ?, ?)"
                "  ON CONFLICT(api_key_id, owner_user_id) DO UPDATE SET"
                "    used_cents = byot_key_usage.used_cents + excluded.used_cents,"
                "    last_settled_at = excluded.last_settled_at,"
                "    updated_at = excluded.updated_at",
                (api_key_id, owner_user_id, actual_cents, now, now),
            )
            con.commit()
        finally:
            con.close()

    def set_limit(
        self,
        api_key_id: str,
        owner_user_id: str,
        limit_cents: int | None,
    ) -> None:
        """Set (or clear) the per-key spend cap."""
        if not api_key_id:
            raise ValueError("api_key_id must be non-empty")
        if not owner_user_id:
            raise ValueError("owner_user_id must be non-empty")
        if limit_cents is not None and limit_cents < 0:
            raise ValueError("limit_cents must be non-negative or None")
        now = _now_iso()
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO byot_key_usage"
                "  (api_key_id, owner_user_id, used_cents, limit_cents, updated_at)"
                "  VALUES (?, ?, 0, ?, ?)"
                "  ON CONFLICT(api_key_id, owner_user_id) DO UPDATE SET"
                "    limit_cents = excluded.limit_cents,"
                "    updated_at = excluded.updated_at",
                (api_key_id, owner_user_id, limit_cents, now),
            )
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def snapshot(self, owner_user_id: str) -> list[KeyUsageRow]:
        """Return usage rows for all keys owned by ``owner_user_id``."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT api_key_id, owner_user_id, used_cents,"
                "  limit_cents, last_settled_at, updated_at"
                " FROM byot_key_usage WHERE owner_user_id = ?"
                " ORDER BY api_key_id",
                (owner_user_id,),
            ).fetchall()
        finally:
            con.close()
        return [
            KeyUsageRow(
                api_key_id=r[0],
                owner_user_id=r[1],
                used_cents=r[2],
                limit_cents=r[3],
                last_settled_at=r[4],
                updated_at=r[5],
            )
            for r in rows
        ]

    def key_usage(self, api_key_id: str, owner_user_id: str) -> KeyUsageRow | None:
        """Return the usage row for one key, or ``None`` if not tracked."""
        con = self._connect()
        try:
            r = con.execute(
                "SELECT api_key_id, owner_user_id, used_cents,"
                "  limit_cents, last_settled_at, updated_at"
                " FROM byot_key_usage"
                " WHERE api_key_id = ? AND owner_user_id = ?",
                (api_key_id, owner_user_id),
            ).fetchone()
        finally:
            con.close()
        if r is None:
            return None
        return KeyUsageRow(
            api_key_id=r[0],
            owner_user_id=r[1],
            used_cents=r[2],
            limit_cents=r[3],
            last_settled_at=r[4],
            updated_at=r[5],
        )

    def would_exceed(
        self,
        api_key_id: str,
        projected_cents: int,
    ) -> bool | None:
        """Check whether a projected spend would exceed the key's limit.

        Returns ``None`` if no limit is set, ``True`` if the projection
        would exceed, ``False`` if it fits within the remaining budget.
        """
        con = self._connect()
        try:
            r = con.execute(
                "SELECT used_cents, limit_cents FROM byot_key_usage"
                " WHERE api_key_id = ?",
                (api_key_id,),
            ).fetchone()
        finally:
            con.close()
        if r is None:
            return None
        used_cents: int = r[0]
        limit_cents: int | None = r[1]
        if limit_cents is None:
            return None
        return bool((used_cents + projected_cents) > limit_cents)

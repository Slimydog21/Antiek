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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

__all__ = [
    "ByotUsageLedger",
    "KeyUsageRow",
    "OperationConflict",
    "OperationRow",
]

_SCHEMA_VERSION: Final = 3
_BUSY_TIMEOUT_MS: Final = 30_000


def default_byot_usage_db_path() -> Path:
    """Resolve the sidecar DB path, co-located with the research-spend DB."""
    configured = os.environ.get("ANTIEK_BYOT_USAGE_DB")
    if configured:
        return Path(configured).expanduser()
    from substrate.research_spend.ledger import default_research_spend_db_path

    spend_db = Path(default_research_spend_db_path())
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
    held_cents: int = 0

    @property
    def remaining_cents(self) -> int | None:
        """Legacy settled-only remainder retained for wire compatibility."""
        if self.limit_cents is None:
            return None
        return max(0, self.limit_cents - self.used_cents)

    @property
    def available_cents(self) -> int | None:
        if self.limit_cents is None:
            return None
        return max(0, self.limit_cents - self.used_cents - self.held_cents)


class OperationConflict(RuntimeError):
    """An operation id is already in use or cannot safely be retried."""


@dataclass(frozen=True, slots=True)
class OperationRow:
    api_key_id: str
    owner_user_id: str
    operation_id: str
    state: str
    reserved_cents: int
    actual_cents: int | None
    authority_digest: str
    evidence_sha256: str | None
    provider_id: str | None
    model_id: str | None
    dispatch_event_id: str | None
    created_at: str
    updated_at: str


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
            con.execute(
                "CREATE TABLE IF NOT EXISTS byot_operation_journal ("
                " api_key_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,"
                " operation_id TEXT NOT NULL, state TEXT NOT NULL,"
                " reserved_cents INTEGER NOT NULL, actual_cents INTEGER,"
                " authority_digest TEXT NOT NULL, evidence_sha256 TEXT,"
                " provider_id TEXT, model_id TEXT, dispatch_event_id TEXT,"
                " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
                " PRIMARY KEY (owner_user_id, operation_id)"
                ")"
            )
            columns = {row[1] for row in con.execute(
                "PRAGMA table_info(byot_operation_journal)"
            ).fetchall()}
            for name in ("provider_id", "model_id", "dispatch_event_id"):
                if name not in columns:
                    con.execute(f"ALTER TABLE byot_operation_journal ADD COLUMN {name} TEXT")
            con.execute(
                "UPDATE byot_usage_meta SET value = ? WHERE key = 'schema_version'",
                (str(_SCHEMA_VERSION),),
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

    def operation(self, owner_user_id: str, operation_id: str) -> OperationRow | None:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT api_key_id, owner_user_id, operation_id, state, reserved_cents,"
                " actual_cents, authority_digest, evidence_sha256, provider_id, model_id,"
                " dispatch_event_id, created_at, updated_at"
                " FROM byot_operation_journal WHERE owner_user_id = ? AND operation_id = ?",
                (owner_user_id, operation_id),
            ).fetchone()
        finally:
            con.close()
        return OperationRow(*row) if row is not None else None

    def snapshot(self, owner_user_id: str) -> list[KeyUsageRow]:
        """Return usage rows for all keys owned by ``owner_user_id``."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT api_key_id, owner_user_id, used_cents,"
                " limit_cents, last_settled_at, updated_at,"
                " (SELECT COALESCE(SUM(j.reserved_cents), 0) FROM byot_operation_journal j"
                "  WHERE j.api_key_id = byot_key_usage.api_key_id"
                "  AND j.owner_user_id = byot_key_usage.owner_user_id"
                "  AND j.state IN ('prepared','sent','settlement_pending','unknown'))"
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
                held_cents=r[6],
            )
            for r in rows
        ]

    def key_usage(self, api_key_id: str, owner_user_id: str) -> KeyUsageRow | None:
        """Return the usage row for one key, or ``None`` if not tracked."""
        con = self._connect()
        try:
            r = con.execute(
                "SELECT api_key_id, owner_user_id, used_cents,"
                " limit_cents, last_settled_at, updated_at,"
                " (SELECT COALESCE(SUM(j.reserved_cents), 0) FROM byot_operation_journal j"
                "  WHERE j.api_key_id = byot_key_usage.api_key_id"
                "  AND j.owner_user_id = byot_key_usage.owner_user_id"
                "  AND j.state IN ('prepared','sent','settlement_pending','unknown'))"
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
            held_cents=r[6],
        )

    def would_exceed(
        self,
        api_key_id: str,
        owner_user_id: str,
        projected_cents: int,
    ) -> bool | None:
        """Check whether a projected spend would exceed the key's limit.

        Scoped to ``(api_key_id, owner_user_id)`` — the table's primary
        key — so one owner's cap can never be read for another owner who
        happens to reference the same ``api_key_id``.

        Returns ``None`` if the key is untracked or no limit is set,
        ``True`` if the projection would exceed, ``False`` if it fits
        within the remaining budget.
        """
        con = self._connect()
        try:
            r = con.execute(
                "SELECT used_cents, limit_cents FROM byot_key_usage"
                " WHERE api_key_id = ? AND owner_user_id = ?",
                (api_key_id, owner_user_id),
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
    def prepare_operation(
        self,
        api_key_id: str,
        owner_user_id: str,
        operation_id: str,
        reserved_cents: int,
        authority_digest: str,
    ) -> OperationRow:
        """Atomically reserve local ceiling headroom for one new operation.

        Prepared rows may be replayed only when every immutable input matches.
        Sent/unknown operations are never made retryable because provider outcome
        may exist even when the caller did not receive it.
        """
        if not all((api_key_id, owner_user_id, operation_id, authority_digest)):
            raise ValueError("operation identity fields must be non-empty")
        if reserved_cents < 0:
            raise ValueError("reserved_cents must be non-negative")
        now = _now_iso()
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute(
                "SELECT api_key_id, state, reserved_cents, actual_cents,"
                " authority_digest, evidence_sha256 FROM byot_operation_journal"
                " WHERE owner_user_id = ? AND operation_id = ?",
                (owner_user_id, operation_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing[0] != api_key_id
                    or existing[2] != reserved_cents
                    or existing[4] != authority_digest
                    or existing[1] != "prepared"
                ):
                    raise OperationConflict("operation is not retryable")
            else:
                usage = con.execute(
                    "SELECT used_cents, limit_cents FROM byot_key_usage"
                    " WHERE api_key_id = ? AND owner_user_id = ?",
                    (api_key_id, owner_user_id),
                ).fetchone()
                other_reserved = con.execute(
                    "SELECT COALESCE(SUM(reserved_cents), 0)"
                    " FROM byot_operation_journal WHERE api_key_id = ?"
                    " AND owner_user_id = ?"
                    " AND state IN ('prepared', 'sent', 'settlement_pending', 'unknown')",
                    (api_key_id, owner_user_id),
                ).fetchone()[0]
                used, limit = usage if usage is not None else (0, None)
                if limit is not None and used + other_reserved + reserved_cents > limit:
                    raise OperationConflict("operation exceeds local limit")
                con.execute(
                    "INSERT INTO byot_operation_journal"
                    " (api_key_id, owner_user_id, operation_id, state, reserved_cents,"
                    " authority_digest, created_at, updated_at) VALUES"
                    " (?, ?, ?, 'prepared', ?, ?, ?, ?)",
                    (api_key_id, owner_user_id, operation_id, reserved_cents,
                     authority_digest, now, now),
                )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        row = self.operation(owner_user_id, operation_id)
        assert row is not None
        return row

    def mark_operation_sent(self, owner_user_id: str, operation_id: str) -> None:
        """Durably cross the no-blind-retry boundary before provider I/O."""
        self._transition(owner_user_id, operation_id, "prepared", "sent")

    def mark_operation_unknown(self, owner_user_id: str, operation_id: str) -> None:
        """Retain the full reservation when provider outcome is unknowable."""
        self._transition(owner_user_id, operation_id, "sent", "unknown")

    def cancel_prepared_operation(self, owner_user_id: str, operation_id: str) -> None:
        """Release a reservation only while provider I/O is provably unsent."""
        self._transition(owner_user_id, operation_id, "prepared", "cancelled")

    def record_operation_result(
        self, owner_user_id: str, operation_id: str, *, actual_cents: int,
        evidence_sha256: str, dispatch_event_id: str, provider_id: str, model_id: str,
    ) -> None:
        """Persist non-secret provider result facts before settlement bookkeeping."""
        if actual_cents < 0 or not all(
            (evidence_sha256, dispatch_event_id, provider_id, model_id)
        ):
            raise ValueError("result facts are invalid")
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE byot_operation_journal SET state = 'settlement_pending',"
                " actual_cents = ?, evidence_sha256 = ?, dispatch_event_id = ?,"
                " provider_id = ?, model_id = ?, updated_at = ?"
                " WHERE owner_user_id = ? AND operation_id = ? AND state = 'sent'",
                (actual_cents, evidence_sha256, dispatch_event_id, provider_id, model_id,
                 _now_iso(), owner_user_id, operation_id),
            ).rowcount
            if changed != 1:
                raise OperationConflict("operation result is not recordable")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _transition(self, owner: str, operation: str, old: str, new: str) -> None:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE byot_operation_journal SET state = ?, updated_at = ?"
                " WHERE owner_user_id = ? AND operation_id = ? AND state = ?",
                (new, _now_iso(), owner, operation, old),
            ).rowcount
            if changed != 1:
                raise OperationConflict("operation is not in the required state")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def settle_operation(
        self, owner_user_id: str, operation_id: str, actual_cents: int,
        evidence_sha256: str,
    ) -> None:
        """Atomically settle a sent operation and increment usage exactly once."""
        if actual_cents < 0:
            raise ValueError("actual_cents must be non-negative")
        con = self._connect()
        now = _now_iso()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT api_key_id, state FROM byot_operation_journal"
                " WHERE owner_user_id = ? AND operation_id = ?",
                (owner_user_id, operation_id),
            ).fetchone()
            if row is None or row[1] != "settlement_pending":
                raise OperationConflict("operation is not settleable")
            con.execute(
                "INSERT INTO byot_key_usage"
                " (api_key_id, owner_user_id, used_cents, last_settled_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT(api_key_id, owner_user_id)"
                " DO UPDATE SET used_cents = used_cents + excluded.used_cents,"
                " last_settled_at = excluded.last_settled_at, updated_at = excluded.updated_at",
                (row[0], owner_user_id, actual_cents, now, now),
            )
            con.execute(
                "UPDATE byot_operation_journal SET state = 'settled', actual_cents = ?,"
                " evidence_sha256 = ?, updated_at = ? WHERE owner_user_id = ?"
                " AND operation_id = ?",
                (actual_cents, evidence_sha256, now, owner_user_id, operation_id),
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def reconcile_operation(self, owner_user_id: str, operation_id: str) -> OperationRow:
        """Finish pending bookkeeping idempotently, never recalling the provider."""
        row = self.operation(owner_user_id, operation_id)
        if row is None:
            raise OperationConflict("operation not found")
        if row.state == "settlement_pending":
            assert row.actual_cents is not None and row.evidence_sha256 is not None
            self.settle_operation(
                owner_user_id, operation_id, row.actual_cents, row.evidence_sha256,
            )
            settled = self.operation(owner_user_id, operation_id)
            assert settled is not None
            return settled
        return row

    def cancel_stale_prepared(
        self, *, owner_user_id: str, max_age_seconds: int = 86_400,
        now: datetime | None = None,
    ) -> int:
        """Release one owner's prepared rows older than the server policy."""
        if not owner_user_id or max_age_seconds < 300:
            raise ValueError("owner and safe cleanup age are required")
        reference = now or datetime.now(UTC)
        older_than = (reference - timedelta(seconds=max_age_seconds)).isoformat(
            timespec="seconds"
        )
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE byot_operation_journal SET state = 'cancelled', updated_at = ?"
                " WHERE owner_user_id = ? AND state = 'prepared' AND created_at < ?",
                (_now_iso(), owner_user_id, older_than),
            ).rowcount
            con.commit()
            return changed
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

"""Durable enqueue-once records for authorized Midnight Oil operations.

The queue contains identifiers and immutable execution options only.  Spend
consent tokens never cross this boundary.  SQLite's UNIQUE(operation_id),
together with BEGIN IMMEDIATE, is the enqueue-once arbiter across processes.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class QueuedOperation:
    operation_id: str
    owner_user_id: str
    job_id: str
    state: str
    enqueued_at_ms: int
    leased_at_ms: int | None
    lease_owner: str | None
    lease_expires_at_ms: int | None
    lease_generation: int
    next_step_index: int
    options: dict[str, object]


@dataclass(frozen=True)
class TerminalOperation:
    operation_id: str
    owner_user_id: str
    job_id: str
    terminal_state: str
    lease_owner: str
    lease_generation: int
    next_step_index: int
    completed_at_ms: int
    options: dict[str, object]


class OperationQueue(Protocol):
    def enqueue_once(
        self,
        *,
        operation_id: str,
        owner_user_id: str,
        job_id: str,
        enqueued_at_ms: int,
        options: dict[str, object],
    ) -> tuple[QueuedOperation, bool]: ...

    def get(self, operation_id: str) -> QueuedOperation | None: ...

    def get_terminal(self, operation_id: str) -> TerminalOperation | None: ...

    def next_claimable(self, *, now_ms: int) -> QueuedOperation | None: ...

    def validate_lease(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> bool: ...

    def run_fenced(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
        expected_step_index: int,
        action: Callable[[], tuple[T, bool]],
        renew_expires_at_ms: Callable[[], int] | None = None,
    ) -> T: ...

    def lease(
        self,
        *,
        operation_id: str,
        worker_id: str,
        leased_at_ms: int,
        lease_expires_at_ms: int,
    ) -> tuple[QueuedOperation, bool]: ...

    def acknowledge_terminal(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        terminal_state: str,
        completed_at_ms: int,
    ) -> bool: ...

    def renew_lease(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        renewed_at_ms: int,
        lease_expires_at_ms: int,
    ) -> bool: ...


def provider_idempotency_key(operation_id: str, step_index: int) -> str:
    """Return the stable, non-secret key carried on each paid provider step."""
    operation = _text(operation_id, "operation_id")
    if type(step_index) is not int or step_index < 0:
        raise ValueError("step_index must be a non-negative integer")
    material = f"{operation}:{step_index}".encode()
    return hashlib.sha256(b"antiek.midnight-oil.provider-step.v1\x00" + material).hexdigest()


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 512:
        raise ValueError(f"{field} must be a bounded non-empty string")
    return value.strip()


def _time(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _options(value: object) -> tuple[dict[str, object], str]:
    if not isinstance(value, dict) or set(value) - {
        "max_steps", "auto_deposit", "draft_combined", "force_offline"
    }:
        raise ValueError("queue options are outside the closed execution contract")
    if any("token" in str(key).lower() or "secret" in str(key).lower() for key in value):
        raise ValueError("queue options must not contain secrets")
    checked = dict(value)
    max_steps = checked.get("max_steps")
    if max_steps is not None and (type(max_steps) is not int or not 1 <= max_steps <= 100_000):
        raise ValueError("max_steps must be a bounded positive integer")
    for name in ("auto_deposit", "draft_combined", "force_offline"):
        if type(checked.get(name)) is not bool:
            raise ValueError(f"{name} must be boolean")
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    return checked, encoded


def _decode(row: tuple[object, ...]) -> QueuedOperation:
    raw = json.loads(str(row[10]))
    options, _ = _options(raw)
    state = str(row[3])
    enqueued = _time(row[4], "enqueued_at_ms")
    leased = None if row[5] is None else _time(row[5], "leased_at_ms")
    lease_owner = None if row[6] is None else _text(row[6], "lease_owner")
    lease_expires = None if row[7] is None else _time(row[7], "lease_expires_at_ms")
    next_step = _time(row[8], "next_step_index")
    generation = _time(row[9], "lease_generation")
    if state not in {"queued", "running"} or (state == "queued") != (leased is None):
        raise ValueError("stored queue state is incoherent")
    if leased is not None and leased < enqueued:
        raise ValueError("lease predates enqueue")
    if state == "running" and (
        leased is None
        or lease_owner is None
        or lease_expires is None
        or lease_expires <= leased
    ):
        raise ValueError("stored lease authority is incoherent")
    return QueuedOperation(
        operation_id=_text(row[0], "operation_id"),
        owner_user_id=_text(row[1], "owner_user_id"),
        job_id=_text(row[2], "job_id"),
        state=state,
        enqueued_at_ms=enqueued,
        leased_at_ms=leased,
        lease_owner=lease_owner,
        lease_expires_at_ms=lease_expires,
        next_step_index=next_step,
        lease_generation=generation,
        options=options,
    )


def _decode_terminal(row: tuple[object, ...]) -> TerminalOperation:
    raw = json.loads(str(row[8]))
    options, _ = _options(raw)
    terminal_state = str(row[3])
    if terminal_state not in {
        "complete",
        "failed",
        "budget_halted",
        "timed_out",
        "failed_reconcile",
    }:
        raise ValueError("stored terminal queue state is invalid")
    return TerminalOperation(
        operation_id=_text(row[0], "operation_id"),
        owner_user_id=_text(row[1], "owner_user_id"),
        job_id=_text(row[2], "job_id"),
        terminal_state=terminal_state,
        lease_owner=_text(row[4], "lease_owner"),
        lease_generation=_time(row[5], "lease_generation"),
        next_step_index=_time(row[6], "next_step_index"),
        completed_at_ms=_time(row[7], "completed_at_ms"),
        options=options,
    )


class DurableOperationQueue:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_dir = self.path.parent / f"{self.path.name}.operation-locks"
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS midnight_oil_operation_queue (
                    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL UNIQUE,
                    owner_user_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('queued', 'running')),
                    enqueued_at_ms INTEGER NOT NULL,
                    leased_at_ms INTEGER,
                    lease_owner TEXT,
                    lease_expires_at_ms INTEGER,
                    next_step_index INTEGER NOT NULL DEFAULT 0,
                    lease_generation INTEGER NOT NULL DEFAULT 0,
                    options_json TEXT NOT NULL,
                    UNIQUE(owner_user_id, job_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS midnight_oil_operation_terminal (
                    operation_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    terminal_state TEXT NOT NULL CHECK (terminal_state IN (
                        'complete', 'failed', 'budget_halted', 'timed_out',
                        'failed_reconcile'
                    )),
                    lease_owner TEXT NOT NULL,
                    lease_generation INTEGER NOT NULL,
                    next_step_index INTEGER NOT NULL,
                    completed_at_ms INTEGER NOT NULL,
                    options_json TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _after_fenced_action(self) -> None:
        """Crash-injection seam after paid checkpoints, before queue advance."""

    @contextmanager
    def _operation_lock(self, operation_id: str):  # type: ignore[no-untyped-def]
        digest = hashlib.sha256(operation_id.encode()).hexdigest()
        with (self._lock_dir / f"{digest}.lock").open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _select(connection: sqlite3.Connection, operation_id: str) -> QueuedOperation | None:
        row = connection.execute(
            "SELECT operation_id, owner_user_id, job_id, state, enqueued_at_ms, "
            "leased_at_ms, lease_owner, lease_expires_at_ms, next_step_index, "
            "lease_generation, options_json "
            "FROM midnight_oil_operation_queue "
            "WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return None if row is None else _decode(tuple(row))

    def enqueue_once(
        self,
        *,
        operation_id: str,
        owner_user_id: str,
        job_id: str,
        enqueued_at_ms: int,
        options: dict[str, object],
    ) -> tuple[QueuedOperation, bool]:
        operation = _text(operation_id, "operation_id")
        owner = _text(owner_user_id, "owner_user_id")
        job = _text(job_id, "job_id")
        at = _time(enqueued_at_ms, "enqueued_at_ms")
        checked_options, encoded = _options(options)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                terminal = connection.execute(
                    "SELECT owner_user_id, job_id, options_json "
                    "FROM midnight_oil_operation_terminal WHERE operation_id = ?",
                    (operation,),
                ).fetchone()
                if terminal is not None:
                    terminal_options, _ = _options(json.loads(str(terminal[2])))
                    if (terminal[0], terminal[1], terminal_options) != (
                        owner,
                        job,
                        checked_options,
                    ):
                        raise ValueError(
                            "terminal operation replay conflicts with durable delivery"
                        )
                    raise ValueError("operation is already terminal")
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO midnight_oil_operation_queue "
                    "(operation_id, owner_user_id, job_id, state, enqueued_at_ms, options_json) "
                    "VALUES (?, ?, ?, 'queued', ?, ?)",
                    (operation, owner, job, at, encoded),
                )
                row = self._select(connection, operation)
                if row is None:
                    conflict = connection.execute(
                        "SELECT operation_id FROM midnight_oil_operation_queue "
                        "WHERE owner_user_id = ? AND job_id = ?", (owner, job)
                    ).fetchone()
                    raise ValueError(
                        "job is already bound to a different operation"
                        if conflict is not None else "enqueue did not persist"
                    )
                if (row.owner_user_id, row.job_id, row.options) != (owner, job, checked_options):
                    raise ValueError("operation queue replay conflicts with durable authority")
                connection.execute("COMMIT")
                return row, cursor.rowcount == 1
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def lease(
        self,
        *,
        operation_id: str,
        worker_id: str,
        leased_at_ms: int,
        lease_expires_at_ms: int,
    ) -> tuple[QueuedOperation, bool]:
        operation = _text(operation_id, "operation_id")
        with self._operation_lock(operation):
            return self._lease_under_operation_lock(
                operation_id=operation,
                worker_id=worker_id,
                leased_at_ms=leased_at_ms,
                lease_expires_at_ms=lease_expires_at_ms,
            )

    def get(self, operation_id: str) -> QueuedOperation | None:
        operation = _text(operation_id, "operation_id")
        with self._connect() as connection:
            return self._select(connection, operation)

    def get_terminal(self, operation_id: str) -> TerminalOperation | None:
        operation = _text(operation_id, "operation_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT operation_id, owner_user_id, job_id, terminal_state, "
                "lease_owner, lease_generation, next_step_index, completed_at_ms, "
                "options_json FROM midnight_oil_operation_terminal "
                "WHERE operation_id = ?",
                (operation,),
            ).fetchone()
        return None if row is None else _decode_terminal(tuple(row))

    def next_claimable(self, *, now_ms: int) -> QueuedOperation | None:
        """Return the oldest queued or expired operation; ``lease`` arbitrates."""

        now = _time(now_ms, "now_ms")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT operation_id, owner_user_id, job_id, state, enqueued_at_ms, "
                "leased_at_ms, lease_owner, lease_expires_at_ms, next_step_index, "
                "lease_generation, options_json FROM midnight_oil_operation_queue "
                "WHERE state = 'queued' OR (state = 'running' AND lease_expires_at_ms <= ?) "
                "ORDER BY enqueued_at_ms, queue_id LIMIT 1",
                (now,),
            ).fetchone()
        return None if row is None else _decode(tuple(row))

    def acknowledge_terminal(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        terminal_state: str,
        completed_at_ms: int,
    ) -> bool:
        """Move a leased operation to the durable terminal ledger atomically."""

        operation = _text(operation_id, "operation_id")
        worker = _text(worker_id, "worker_id")
        generation = _time(lease_generation, "lease_generation")
        completed = _time(completed_at_ms, "completed_at_ms")
        if terminal_state not in {
            "complete",
            "failed",
            "budget_halted",
            "timed_out",
            "failed_reconcile",
        }:
            raise ValueError("queue terminal state is outside the closed contract")
        with self._operation_lock(operation), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select(connection, operation)
                if row is None:
                    existing = connection.execute(
                        "SELECT terminal_state, lease_owner, lease_generation "
                        "FROM midnight_oil_operation_terminal WHERE operation_id = ?",
                        (operation,),
                    ).fetchone()
                    connection.execute("COMMIT")
                    return bool(existing == (terminal_state, worker, generation))
                if (
                    row.state != "running"
                    or row.lease_owner != worker
                    or row.lease_generation != generation
                ):
                    connection.execute("COMMIT")
                    return False
                connection.execute(
                    "INSERT INTO midnight_oil_operation_terminal "
                    "(operation_id, owner_user_id, job_id, terminal_state, "
                    "lease_owner, lease_generation, next_step_index, completed_at_ms, "
                    "options_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row.operation_id,
                        row.owner_user_id,
                        row.job_id,
                        terminal_state,
                        worker,
                        generation,
                        row.next_step_index,
                        completed,
                        json.dumps(row.options, sort_keys=True, separators=(",", ":")),
                    ),
                )
                deleted = connection.execute(
                    "DELETE FROM midnight_oil_operation_queue "
                    "WHERE operation_id = ? AND lease_owner = ? "
                    "AND lease_generation = ?",
                    (operation, worker, generation),
                )
                if deleted.rowcount != 1:
                    raise RuntimeError("terminal acknowledgement lost its lease fence")
                connection.execute("COMMIT")
                return True
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def renew_lease(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        renewed_at_ms: int,
        lease_expires_at_ms: int,
    ) -> bool:
        operation = _text(operation_id, "operation_id")
        worker = _text(worker_id, "worker_id")
        generation = _time(lease_generation, "lease_generation")
        renewed = _time(renewed_at_ms, "renewed_at_ms")
        expiry = _time(lease_expires_at_ms, "lease_expires_at_ms")
        if expiry <= renewed:
            raise ValueError("renewed lease expiry must follow renewal")
        with self._operation_lock(operation), self._connect() as connection:
            changed = connection.execute(
                "UPDATE midnight_oil_operation_queue SET leased_at_ms = ?, "
                "lease_expires_at_ms = ? WHERE operation_id = ? AND state = 'running' "
                "AND lease_owner = ? AND lease_generation = ?",
                (renewed, expiry, operation, worker, generation),
            )
            return changed.rowcount == 1

    def validate_lease(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> bool:
        operation = _text(operation_id, "operation_id")
        worker = _text(worker_id, "worker_id")
        generation = _time(lease_generation, "lease_generation")
        now = _time(now_ms, "now_ms")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM midnight_oil_operation_queue WHERE operation_id = ? "
                "AND state = 'running' AND lease_owner = ? AND lease_generation = ? "
                "AND lease_expires_at_ms > ?",
                (operation, worker, generation, now),
            ).fetchone()
            return row is not None

    def run_fenced(
        self,
        *,
        operation_id: str,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
        expected_step_index: int,
        action: Callable[[], tuple[T, bool]],
        renew_expires_at_ms: Callable[[], int] | None = None,
    ) -> T:
        """Fence one operation without serializing unrelated paid work."""
        operation = _text(operation_id, "operation_id")
        worker = _text(worker_id, "worker_id")
        generation = _time(lease_generation, "lease_generation")
        now = _time(now_ms, "now_ms")
        step = _time(expected_step_index, "expected_step_index")
        with self._operation_lock(operation):
            with self._connect() as connection:
                valid = connection.execute(
                    "SELECT 1 FROM midnight_oil_operation_queue WHERE operation_id = ? "
                    "AND state = 'running' AND lease_owner = ? AND lease_generation = ? "
                    "AND lease_expires_at_ms > ?",
                    (operation, worker, generation, now),
                ).fetchone()
                if valid is None:
                    raise RuntimeError("worker lease is stale")
            try:
                result, should_advance = action()
                self._after_fenced_action()
            except BaseException:
                # The paid action may fail after its original lease duration.
                # Renew while the same per-operation lock is still held so no
                # successor generation can overlap terminal disposition.
                if renew_expires_at_ms is not None:
                    exceptional_expiry = _time(
                        renew_expires_at_ms(), "renew_expires_at_ms"
                    )
                    if exceptional_expiry <= now:
                        raise ValueError(
                            "fenced renewal must extend beyond fence time"
                        ) from None
                    with self._connect() as connection:
                        renewed = connection.execute(
                            "UPDATE midnight_oil_operation_queue SET "
                            "lease_expires_at_ms = ? WHERE operation_id = ? "
                            "AND state = 'running' AND lease_owner = ? "
                            "AND lease_generation = ?",
                            (exceptional_expiry, operation, worker, generation),
                        )
                        if renewed.rowcount != 1:
                            raise RuntimeError(
                                "exceptional paid fence lost its lease generation"
                            ) from None
                raise
            renewal_expiry = (
                None if renew_expires_at_ms is None else renew_expires_at_ms()
            )
            if renewal_expiry is not None:
                renewal_expiry = _time(renewal_expiry, "renew_expires_at_ms")
                if renewal_expiry <= now:
                    raise ValueError("fenced renewal must extend beyond fence time")
            if should_advance or renewal_expiry is not None:
                with self._connect() as connection:
                    next_step = step + 1 if should_advance else step
                    changed = connection.execute(
                        "UPDATE midnight_oil_operation_queue SET next_step_index = ?, "
                        "lease_expires_at_ms = COALESCE(?, lease_expires_at_ms) "
                        "WHERE operation_id = ? AND state = 'running' "
                        "AND next_step_index = ? AND lease_owner = ? "
                        "AND lease_generation = ?",
                        (
                            next_step,
                            renewal_expiry,
                            operation,
                            step,
                            worker,
                            generation,
                        ),
                    )
                    if changed.rowcount != 1:
                        raise RuntimeError("provider step checkpoint requires reconciliation")
            return result

    def _lease_under_operation_lock(
        self,
        *,
        operation_id: str,
        worker_id: str,
        leased_at_ms: int,
        lease_expires_at_ms: int,
    ) -> tuple[QueuedOperation, bool]:
        operation = _text(operation_id, "operation_id")
        worker = _text(worker_id, "worker_id")
        at = _time(leased_at_ms, "leased_at_ms")
        expiry = _time(lease_expires_at_ms, "lease_expires_at_ms")
        if expiry <= at:
            raise ValueError("lease expiry must follow acquisition")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "UPDATE midnight_oil_operation_queue SET state = 'running', leased_at_ms = ?, "
                    "lease_owner = ?, lease_expires_at_ms = ?, "
                    "lease_generation = lease_generation + 1 WHERE operation_id = ? AND "
                    "(state = 'queued' OR (state = 'running' AND "
                    "(lease_owner = ? OR lease_expires_at_ms <= ?)))",
                    (at, worker, expiry, operation, worker, at),
                )
                row = self._select(connection, operation)
                if row is None:
                    raise KeyError(operation)
                connection.execute("COMMIT")
                return row, cursor.rowcount == 1
            except Exception:
                connection.execute("ROLLBACK")
                raise


__all__ = [
    "DurableOperationQueue",
    "OperationQueue",
    "QueuedOperation",
    "provider_idempotency_key",
]

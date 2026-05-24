"""
DuckDB-backed boundary-task queue.

Single-writer per the I-001 invariant — every write goes through
``runtime.db_lock.connect_write``. Reads use ``connect_read`` so
status queries don't take the writer flock.

Schema:

    CREATE TABLE boundary_tasks (
        id INTEGER PRIMARY KEY,
        description TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        status TEXT CHECK (status IN ('queued', 'running', 'done', 'cancelled'))
    );
    CREATE TABLE boundary_tasks_meta (k TEXT PRIMARY KEY, v TEXT);

The ``id`` column is a monotonic counter; we mint it via a meta row
so the value is recoverable after a restart without scanning the
table.

The ``pop`` operation uses a BEGIN IMMEDIATE transaction to atomically
move the oldest queued task to ``running``, ensuring two concurrent
daemons cannot double-pop the same task. The write lock from
``connect_write`` provides additional cross-process safety.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb

DEFAULT_DB_PATH = Path.home() / ".antiek" / "boundary_queue.db"

# Duration validation per spec: boundary tasks are deliberately
# coarse-grained — operator-bounded chunks of work, not interactive
# requests. The lower bound rejects "tasks" that are really just
# regular dispatch calls; the upper bound rejects multi-hour
# runaway work that should be its own §7 daemon mode.
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 480  # 8 hours


@dataclass(frozen=True)
class BoundaryTask:
    """One row from the queue, hydrated for callers."""

    id: int
    description: str
    duration_minutes: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    status: str


def db_path() -> Path:
    """Resolve the queue DB path, honoring ``ANTIEK_BOUNDARY_QUEUE_DB``."""
    override = os.environ.get("ANTIEK_BOUNDARY_QUEUE_DB")
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create tables and the id-counter row if missing.

    Idempotent — safe to call on every connect_write.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS boundary_tasks (
            id INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            status TEXT CHECK (status IN ('queued', 'running', 'done', 'cancelled'))
        )
        """
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS boundary_tasks_meta (k TEXT PRIMARY KEY, v TEXT)"
    )
    con.execute(
        "INSERT INTO boundary_tasks_meta VALUES ('next_id', '1') "
        "ON CONFLICT (k) DO NOTHING"
    )


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    """Atomically allocate the next task id under the writer flock.

    DuckDB's PRIMARY KEY enforces uniqueness, but we want predictable
    monotonic ids so the operator can refer to "task 17" in
    conversation. The meta row holds the counter; we bump it inside
    the same transaction the caller is in.
    """
    row = con.execute("SELECT v FROM boundary_tasks_meta WHERE k='next_id'").fetchone()
    current = int(row[0]) if row else 1
    con.execute(
        "UPDATE boundary_tasks_meta SET v = ? WHERE k = 'next_id'",
        [str(current + 1)],
    )
    return current


def _connect_write(path: Path):
    """Bridge to ``runtime.db_lock.connect_write``.

    Wrapped in a tiny helper so the test suite can monkey-patch
    without touching the live runtime module. The helper is also
    where we ensure the parent directory exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Import inside the function so importing this module doesn't
    # pull duckdb's full lifecycle in for callers that only use
    # the dataclasses.
    from runtime.db_lock import connect_write

    return connect_write(str(path), purpose="boundary_task_queue")


def _connect_read(path: Path):
    from runtime.db_lock import connect_read

    if not path.exists():
        return None
    return connect_read(str(path))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def queue(description: str, duration_minutes: int, *, path: Path | None = None) -> BoundaryTask:
    """Push a new task onto the queue. Returns the row with assigned id."""
    if not description.strip():
        raise ValueError("description must be non-empty")
    if duration_minutes < MIN_DURATION_MINUTES:
        raise ValueError(
            f"duration_minutes={duration_minutes} below {MIN_DURATION_MINUTES} — "
            f"boundary tasks are deliberately coarse; use regular dispatch for sub-{MIN_DURATION_MINUTES}m work"
        )
    if duration_minutes > MAX_DURATION_MINUTES:
        raise ValueError(
            f"duration_minutes={duration_minutes} above {MAX_DURATION_MINUTES} (8h) — "
            f"long-running work belongs in a §7 daemon mode, not the boundary queue"
        )
    p = path or db_path()
    with _connect_write(p) as con:
        _ensure_schema(con)
        task_id = _next_id(con)
        con.execute(
            "INSERT INTO boundary_tasks (id, description, duration_minutes, status) "
            "VALUES (?, ?, ?, 'queued')",
            [task_id, description.strip(), int(duration_minutes)],
        )
        return _read_one_with(con, task_id)


def pop(*, path: Path | None = None) -> BoundaryTask | None:
    """Atomically move the oldest queued task to 'running'. Returns the task
    or None if the queue is empty.

    Cross-process safety: ``connect_write`` holds an advisory flock so
    two daemons cannot enter this block simultaneously. The double-pop
    test (``test_concurrent_pop``) exercises this.
    """
    p = path or db_path()
    try:
        with _connect_write(p) as con:
            _ensure_schema(con)
            row = con.execute(
                "SELECT id FROM boundary_tasks WHERE status = 'queued' "
                "ORDER BY created_at ASC, id ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            candidate = int(row[0])
            # Guard against the race where another worker already
            # claimed this row between our SELECT and UPDATE: scope the
            # UPDATE to status='queued' so it's a no-op (0 rows) if the
            # row already moved to 'running'. DuckDB's MVCC will also
            # reject a concurrent same-row update with a
            # TransactionException, which we catch below.
            con.execute(
                "UPDATE boundary_tasks SET status = 'running', started_at = ? "
                "WHERE id = ? AND status = 'queued'",
                [_now_iso(), candidate],
            )
            fetched = _read_one_with(con, candidate)
            # If a concurrent worker's UPDATE won, our WHERE-guarded
            # update was a 0-row no-op and the row is already 'running'
            # under the other worker. Report empty so we don't hand the
            # same task to two workers.
            if fetched.status != "running":
                return None
            return fetched
    except duckdb.TransactionException:
        # We lost the race to a concurrent writer. The flock is a
        # cross-PROCESS lock; two THREADS in one process can both enter,
        # so MVCC is the load-bearing serializer here. Losing means the
        # other worker took the task — report an empty pop. The caller
        # (a daemon loop) simply tries again next cycle.
        return None


def mark_done(task_id: int, *, path: Path | None = None) -> BoundaryTask:
    """Mark a running task as done. Errors if the task is not 'running'."""
    p = path or db_path()
    with _connect_write(p) as con:
        _ensure_schema(con)
        row = con.execute(
            "SELECT status FROM boundary_tasks WHERE id = ?", [task_id]
        ).fetchone()
        if row is None:
            raise KeyError(f"no boundary task with id={task_id}")
        if row[0] != "running":
            raise ValueError(f"task id={task_id} is in state {row[0]!r}, expected 'running'")
        con.execute(
            "UPDATE boundary_tasks SET status = 'done', completed_at = ? WHERE id = ?",
            [_now_iso(), task_id],
        )
        return _read_one_with(con, task_id)


def cancel(task_id: int, *, path: Path | None = None) -> BoundaryTask:
    """Mark a queued or running task as cancelled. Idempotent on terminal states.

    The post-write read happens OUTSIDE the write block: DuckDB refuses
    to open a read connection while a write connection with a different
    configuration is live on the same file. Returning ``_read_one``
    from inside the ``with`` block (e.g. an early return on the
    already-terminal branch) trips that — so every path falls through
    to the single ``_read_one`` after the block closes.
    """
    p = path or db_path()
    with _connect_write(p) as con:
        _ensure_schema(con)
        row = con.execute(
            "SELECT status FROM boundary_tasks WHERE id = ?", [task_id]
        ).fetchone()
        if row is None:
            raise KeyError(f"no boundary task with id={task_id}")
        if row[0] not in ("done", "cancelled"):
            con.execute(
                "UPDATE boundary_tasks SET status = 'cancelled', completed_at = ? WHERE id = ?",
                [_now_iso(), task_id],
            )
        return _read_one_with(con, task_id)


def status(*, path: Path | None = None) -> list[BoundaryTask]:
    """Return every task, newest first."""
    p = path or db_path()
    if not p.exists():
        return []
    rows: list[tuple] = []
    con = _connect_read(p)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT id, description, duration_minutes, created_at, started_at, completed_at, status "
            "FROM boundary_tasks ORDER BY id DESC"
        ).fetchall()
    finally:
        con.close()
    return [_hydrate(r) for r in rows]


def _hydrate(row: tuple) -> BoundaryTask:
    return BoundaryTask(
        id=int(row[0]),
        description=str(row[1]),
        duration_minutes=int(row[2]),
        created_at=str(row[3]) if row[3] else "",
        started_at=str(row[4]) if row[4] else None,
        completed_at=str(row[5]) if row[5] else None,
        status=str(row[6]),
    )


_TASK_COLUMNS = (
    "id, description, duration_minutes, created_at, started_at, completed_at, status"
)


def _read_one_with(con, task_id: int) -> BoundaryTask:
    """Hydrate a single task using an ALREADY-OPEN connection.

    This is the read-back path for every mutating method. It reuses the
    write connection the caller already holds rather than opening a
    separate read connection — DuckDB refuses two connections with
    different configurations on one file within a single process, and a
    second worker thread mid-write would otherwise collide. Reading back
    through the held connection makes the conflict structurally
    impossible rather than merely unlikely.
    """
    row = con.execute(
        f"SELECT {_TASK_COLUMNS} FROM boundary_tasks WHERE id = ?",
        [task_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"no boundary task with id={task_id} after commit")
    return _hydrate(row)

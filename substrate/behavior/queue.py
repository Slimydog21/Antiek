"""In-process write queue + worker for the Tier-1 behavior store.

SPR-01 M6 — the queue exists so the emit API can return synchronously
to the caller (UI thread) while the actual DB write happens off-
thread. For Wave 1 we ship an in-process ``queue.Queue`` + a daemon
thread; Wave 2/3 can swap this for a durable queue (SQS, Redis
Streams) at the operator's discretion by replacing ``BehaviorQueue``
with a subclass that satisfies the same shape.

Contract
--------
- ``submit(row)`` is non-blocking and never raises (the queue is
  bounded and uses drop-on-overflow with a stderr breadcrumb).
- A single worker thread drains the queue and inserts into
  ``behavior_events`` via ``runtime.db_lock.connect_write``.
- The worker batches up to ``BATCH_SIZE`` rows per transaction to
  reduce flock churn; lone rows still write within
  ``MAX_LATENCY_S`` so the M7 "row exists within 2s" assertion holds.
- ``flush()`` blocks until the queue is drained; tests call it.
- ``shutdown()`` joins the worker.

This is intentionally simple. The shape is "queue + worker", not
an event-loop or asyncio framework. The web client doesn't see this
module at all — it goes through ``api.py``.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    from ...runtime.db_lock import connect_write
    from .schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from substrate.behavior.schema import default_db_path  # type: ignore[no-redef]


# Tunables. Conservative defaults for a single-operator workload.
BATCH_SIZE: int = 64
"""Max rows per transaction. 64 is comfortable below DuckDB's
sweet-spot of a few hundred; we prioritise low write latency over
maximal batching."""

MAX_LATENCY_S: float = 0.5
"""Worker wakes every ``MAX_LATENCY_S`` to flush a partial batch
even if it hasn't filled. Drives the M7 "row exists within 2s"
assertion."""

QUEUE_MAX: int = 10_000
"""Bounded queue. A real overflow (10k pending events) is itself a
substrate bug — we drop with a stderr breadcrumb rather than
blocking the caller. Wave 2 surfaces should NEVER fill this; a
realistic single-operator session produces dozens, not thousands."""


@dataclass
class BehaviorRow:
    """One pending insert. Field set matches the
    ``behavior_events`` table 1:1; the worker just binds them."""

    event_id: str
    user_id: str
    session_id: str
    event_type: str
    document_id: Optional[str]
    state: dict[str, Any]
    action: dict[str, Any]
    outcome: Optional[dict[str, Any]]
    consent_version: int


class BehaviorQueue:
    """In-process queue + worker. One instance per process.

    Construct lazily via ``get_default_queue()``; tests construct
    their own with an override db_path.
    """

    def __init__(self, *, db_path: Optional[str] = None):
        self._db_path = db_path or default_db_path()
        self._q: queue.Queue[BehaviorRow] = queue.Queue(maxsize=QUEUE_MAX)
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._drops = 0
        self._writes = 0
        self._lock = threading.Lock()

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def drops(self) -> int:
        return self._drops

    @property
    def writes(self) -> int:
        return self._writes

    # ── public API ──

    def start(self) -> None:
        """Idempotent worker spawn."""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop.clear()
            self._worker = threading.Thread(
                target=self._run,
                name="behavior-queue-worker",
                daemon=True,
            )
            self._worker.start()

    def submit(self, row: BehaviorRow) -> None:
        """Non-blocking enqueue. Drops on overflow with a stderr
        breadcrumb (the substrate must never block a UI thread, and
        a queue this big indicates a bug upstream)."""
        try:
            self._q.put_nowait(row)
        except queue.Full:
            self._drops += 1
            sys.stderr.write(
                f"behavior.queue: queue full ({QUEUE_MAX}); "
                f"dropping event {row.event_id} (event_type={row.event_type})\n"
            )

    def flush(self, *, timeout_s: float = 5.0) -> bool:
        """Block until the queue is empty (or timeout).

        Returns ``True`` if drained cleanly. Tests call this before
        asserting row counts.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._q.empty():
                # Give the worker a moment to commit any in-flight batch.
                time.sleep(0.05)
                if self._q.empty():
                    return True
            time.sleep(0.05)
        return self._q.empty()

    def shutdown(self, *, timeout_s: float = 5.0) -> None:
        """Drain + stop the worker. Tests call this in teardown."""
        self.flush(timeout_s=timeout_s)
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout_s)

    # ── worker internals ──

    def _run(self) -> None:
        """Drain loop. Picks up at most ``BATCH_SIZE`` rows per
        write, sleeps up to ``MAX_LATENCY_S`` when the queue is
        empty."""
        while not self._stop.is_set():
            batch = self._gather_batch()
            if batch:
                self._write_batch(batch)
            else:
                # No work; nap briefly. We do not block on the queue
                # because we need to honour the stop event.
                time.sleep(MAX_LATENCY_S / 2)

    def _gather_batch(self) -> list[BehaviorRow]:
        """Wait up to ``MAX_LATENCY_S`` for the first row, then drain
        up to ``BATCH_SIZE`` total without further waiting."""
        try:
            first = self._q.get(timeout=MAX_LATENCY_S)
        except queue.Empty:
            return []
        batch: list[BehaviorRow] = [first]
        while len(batch) < BATCH_SIZE:
            try:
                batch.append(self._q.get_nowait())
            except queue.Empty:
                break
        return batch

    def _write_batch(self, batch: list[BehaviorRow]) -> None:
        """Insert the batch in one transaction. On error, the rows
        are dropped (with a stderr breadcrumb) — re-queueing would
        be wrong here because the failure mode is usually schema-
        level (substrate bug), not transient."""
        try:
            con = connect_write(self._db_path, purpose="behavior_emit_batch")
        except Exception as e:
            sys.stderr.write(
                f"behavior.queue: could not acquire write lock; "
                f"dropping {len(batch)} rows: {e!r}\n"
            )
            return
        try:
            # executemany would be tidier but DuckDB's binding for
            # JSON-as-string is friendlier with explicit casts in a
            # loop. The batch size is small (≤64) so the perf hit is
            # negligible vs the clarity win.
            for row in batch:
                con.execute(
                    "INSERT INTO behavior_events "
                    "(event_id, user_id, session_id, event_type, "
                    " document_id, state, action, outcome, "
                    " consent_version, dp_shuffler_batch_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    [
                        row.event_id,
                        row.user_id,
                        row.session_id,
                        row.event_type,
                        row.document_id,
                        json.dumps(row.state, default=str),
                        json.dumps(row.action, default=str),
                        json.dumps(row.outcome, default=str) if row.outcome is not None else None,
                        row.consent_version,
                    ],
                )
                self._writes += 1
        except Exception as e:
            sys.stderr.write(
                f"behavior.queue: batch insert failed; "
                f"dropping {len(batch)} rows: {e!r}\n"
            )
        finally:
            con.close()


# ── module-level default queue ──

_default_queue: Optional[BehaviorQueue] = None
_default_queue_lock = threading.Lock()


def get_default_queue(*, db_path: Optional[str] = None) -> BehaviorQueue:
    """Return the process-wide default queue, creating it on first
    use. Pass ``db_path`` only at first call; subsequent calls
    ignore it and return the existing instance.

    Tests should construct their own ``BehaviorQueue`` rather than
    use this helper; this exists for the production call-site
    where Wave 2 surfaces just want a singleton.
    """
    global _default_queue
    with _default_queue_lock:
        if _default_queue is None:
            _default_queue = BehaviorQueue(db_path=db_path)
            _default_queue.start()
        return _default_queue


def reset_default_queue() -> None:
    """Test helper. Shut down the default queue and drop the ref so
    the next ``get_default_queue`` constructs a fresh one with the
    current ``ANTIEK_DUCKDB_PATH``."""
    global _default_queue
    with _default_queue_lock:
        if _default_queue is not None:
            _default_queue.shutdown()
            _default_queue = None


__all__ = [
    "BATCH_SIZE",
    "BehaviorQueue",
    "BehaviorRow",
    "MAX_LATENCY_S",
    "QUEUE_MAX",
    "get_default_queue",
    "reset_default_queue",
]

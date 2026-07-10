"""Append-only JSONL journal with deterministic call identity.

Each record carries a deterministic ``call_id`` derived from the call
parameters (requested_model + task_class + item_id) — no random run
identifiers.  The journal is the single source of truth for realized
spend, crash recovery, and idempotency.

Design invariants (per sprint rigor):

* **fsync append** — every write is flushed + fsynced before the lock
  is released, so a crash mid-write produces at most one torn tail.
* **torn-tail recovery** — ``replay()`` silently drops the last line
  if it fails to parse; all preceding complete rows survive.
* **idempotency** — ``append()`` rejects a duplicate ``call_id``.
* **deterministic identity** — ``call_id`` is a pure function of
  (requested_model, task_class, item_id).
* **secret-free** — no environment values, API credentials, or raw
  response text is persisted; failure text is bounded.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

# Call statuses — the closed set the record round-trips.
Status = Literal["ok", "timeout", "error"]

#: Maximum failure text length persisted to the journal (chars).
_FAILURE_TEXT_LIMIT = 500


def _deterministic_call_id(
    requested_model: str,
    task_class: str,
    item_id: str,
) -> str:
    """Stable hash identity from call parameters — no randomness."""
    digest = hashlib.sha256(
        f"live-call:v1:{requested_model}:{task_class}:{item_id}".encode()
    ).hexdigest()[:16]
    return f"lc_{digest}"


@dataclass(frozen=True)
class LiveCallRecord:
    """One append-only call record.

    ``call_id`` is a computed property — deterministic from the three
    identity fields, never stored or serialized.  This is the pattern
    ``run.py::_run_id`` establishes for Antiek-bench run identifiers.
    """

    # Identity (deterministic — call_id derives from these three).
    requested_model: str
    actual_model: str
    task_class: str
    item_id: str

    # Measured outcome.
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    status: Status

    # Failure detail (bounded, secret-free).
    failure_text: str = ""

    @property
    def call_id(self) -> str:
        """Deterministic identity — pure function of call parameters."""
        return _deterministic_call_id(
            self.requested_model, self.task_class, self.item_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL persistence.

        ``call_id`` is NOT stored — it is re-derived on replay.
        """
        return {
            "requested_model": self.requested_model,
            "actual_model": self.actual_model,
            "task_class": self.task_class,
            "item_id": self.item_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": str(self.cost_usd),
            "latency_ms": self.latency_ms,
            "status": self.status,
            "failure_text": self.failure_text[:_FAILURE_TEXT_LIMIT],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LiveCallRecord:
        """Reconstruct from persisted dict.

        Raises ``ValueError`` if required fields are missing or status
        is outside the closed set.  ``call_id`` is re-derived, not read.
        """
        status = d.get("status")
        if status not in ("ok", "timeout", "error"):
            raise ValueError(f"invalid status: {status!r}")
        return cls(
            requested_model=str(d["requested_model"]),
            actual_model=str(d["actual_model"]),
            task_class=str(d["task_class"]),
            item_id=str(d["item_id"]),
            prompt_tokens=int(d["prompt_tokens"]),
            completion_tokens=int(d["completion_tokens"]),
            cost_usd=Decimal(str(d["cost_usd"])),
            latency_ms=int(d["latency_ms"]),
            status=status,
            failure_text=str(d.get("failure_text", ""))[:_FAILURE_TEXT_LIMIT],
        )


def _validate_record(record: LiveCallRecord) -> None:
    """Pre-append sanity — fail loud, not silent."""
    if not record.requested_model.strip():
        raise ValueError("requested_model must not be blank")
    if not record.actual_model.strip():
        raise ValueError("actual_model must not be blank")
    if not record.task_class.strip():
        raise ValueError("task_class must not be blank")
    if not record.item_id.strip():
        raise ValueError("item_id must not be blank")
    if record.cost_usd < 0:
        raise ValueError("cost_usd must be non-negative")
    if record.prompt_tokens < 0:
        raise ValueError("prompt_tokens must be non-negative")
    if record.completion_tokens < 0:
        raise ValueError("completion_tokens must be non-negative")


class Journal:
    """Append-only JSONL journal with fsync persistence and torn-tail recovery.

    The journal is a single-writer append-only file.  Each line is a
    JSON object representing one ``LiveCallRecord``.  ``call_id`` is
    never stored — it is re-derived from the identity fields on replay.

    Thread safety: follows the existing Antiek single-writer convention
    (one process owns the journal; no cross-process locking).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        # Ensure parent directory exists (convention from FileBenchStore).
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: LiveCallRecord) -> None:
        """Append one record to the journal.

        Raises ``ValueError`` on duplicate ``call_id`` (idempotency) or
        invalid record fields.  The write is fsync-backed: once this
        returns, the record is durable.
        """
        _validate_record(record)
        existing = self.replay()
        if record.call_id in existing:
            raise ValueError(
                f"duplicate call_id: {record.call_id} "
                f"(requested_model={record.requested_model!r}, "
                f"item_id={record.item_id!r})"
            )
        self._fsync_append(record)

    def _fsync_append(self, record: LiveCallRecord) -> None:
        """Atomic JSONL append with fsync.

        Opens the file in append mode, acquires an exclusive lock,
        writes one JSON line, flushes, fsyncs, then releases the lock.
        A crash after the write but before fsync still produces a
        complete line (OS page cache); a crash mid-write produces at
        most one torn tail that ``replay()`` drops.
        """
        line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        fd = os.open(
            str(self._path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            0o644,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def replay(self) -> dict[str, LiveCallRecord]:
        """Replay the journal, returning a map of call_id → record.

        Handles torn tails: if the last line fails to parse (truncated
        write from a crash), it is silently dropped.  All preceding
        complete lines are returned.
        """
        if not self._path.exists():
            return {}
        records: dict[str, LiveCallRecord] = {}
        lines = self._path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                d = json.loads(stripped)
                rec = LiveCallRecord.from_dict(d)
                records[rec.call_id] = rec
            except (json.JSONDecodeError, KeyError, ValueError):
                # Torn tail: if this is the last non-empty line, drop
                # it silently (crash recovery).  If it's a mid-file
                # corruption, still drop — we don't have a repair path.
                if i == len(lines) - 1:
                    # Expected torn tail from crash — silent drop.
                    pass
                else:
                    # Mid-file corruption — drop but could log in future.
                    pass
        return records

    def lookup(self, call_id: str) -> LiveCallRecord | None:
        """Deterministic lookup by call_id."""
        return self.replay().get(call_id)

    def clear(self) -> None:
        """Remove the journal file (test utility only)."""
        if self._path.exists():
            self._path.unlink()

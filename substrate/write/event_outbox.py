"""Transactional delivery intents for authoritative Write events."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.constants import ANTIEK_PARAM_VERSION
from substrate.event_log.events import (
    default_events_dir,
    investigation_event_lock,
)
from substrate.schemas.events import DEFAULT_POLICY_ID, EVENT_SCHEMA_VERSION, Event


class EventOutboxError(RuntimeError):
    pass


def _events_disabled() -> bool:
    return os.environ.get("ANTIEK_EVENTS_DISABLED", "").lower() in ("1", "true", "yes")


@contextmanager
def eventful_transaction(con: LockedConnection, investigation_id: str):
    """Commit a mutation and its outbox intent before sealing can intervene.

    Callers already hold the global DuckDB write lock, so the lock order is
    always database then investigation event stream. Sealing uses the same
    order. Delivery reacquires the event lock only after this context exits.
    """
    lock = nullcontext() if _events_disabled() else investigation_event_lock(investigation_id)
    with lock:
        con.execute("BEGIN TRANSACTION")
        try:
            yield
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def canonical_event_json(event: Event) -> str:
    return json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def build_typed_envelope(
    investigation_id: str,
    payload: Any,
    *,
    parent_event_id: str | None = None,
    role: str | None = None,
    policy_id: str | None = None,
    document_id: str | None = None,
    event_id: str | None = None,
    emitted_at: datetime | None = None,
) -> Event:
    return Event(
        event_id=event_id or f"evt-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}",
        investigation_id=investigation_id,
        role=role,
        action_type=payload.action_type,
        payload=payload,
        parent_event_id=parent_event_id,
        policy_id=policy_id or DEFAULT_POLICY_ID,
        param_version=ANTIEK_PARAM_VERSION,
        schema_version=EVENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(UTC),
        document_id=document_id,
    )


def enqueue_event(
    con: LockedConnection,
    *,
    operation_id: str,
    aggregate_kind: str,
    aggregate_id: str,
    event: Event,
) -> str:
    if _events_disabled():
        return event.event_id
    encoded = canonical_event_json(event)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    existing = con.execute(
        "SELECT event_id, event_sha256, event_json FROM write_event_outbox "
        "WHERE operation_id = ? OR event_id = ?",
        [operation_id, event.event_id],
    ).fetchall()
    if existing:
        if len(existing) != 1 or existing[0] != (event.event_id, digest, encoded):
            raise EventOutboxError("outbox identity was reused with different event bytes")
        return event.event_id
    con.execute(
        "INSERT INTO write_event_outbox "
        "(event_id, operation_id, investigation_id, aggregate_kind, aggregate_id, "
        "event_json, event_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [event.event_id, operation_id, event.investigation_id, aggregate_kind,
         aggregate_id, encoded, digest],
    )
    return event.event_id


def event_for_operation(con: LockedConnection, operation_id: str) -> Event | None:
    row = con.execute(
        "SELECT event_json, event_sha256 FROM write_event_outbox WHERE operation_id=?",
        [operation_id],
    ).fetchone()
    if row is None:
        return None
    encoded, digest = row
    if hashlib.sha256(encoded.encode()).hexdigest() != digest:
        raise EventOutboxError("stored outbox digest does not match event bytes")
    try:
        return Event.model_validate_json(encoded)
    except Exception as exc:
        raise EventOutboxError("stored outbox event is invalid") from exc


def next_aggregate_operation_id(
    con: LockedConnection,
    *,
    action: str,
    aggregate_kind: str,
    aggregate_id: str,
) -> str:
    ordinal = con.execute(
        "SELECT COUNT(*) + 1 FROM write_event_outbox "
        "WHERE aggregate_kind=? AND aggregate_id=?",
        [aggregate_kind, aggregate_id],
    ).fetchone()[0]
    return f"{action}:{aggregate_id}:v{ordinal}"


def _existing_jsonl_events(path: Path) -> dict[str, str]:
    if not os.path.lexists(path):
        return {}
    found: dict[str, str] = {}
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise EventOutboxError("event JSONL must be a singly linked regular file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise EventOutboxError("event JSONL must be a singly linked regular file")
        with os.fdopen(fd, encoding="utf-8") as handle:
            fd = -1
            for line in handle:
                stripped = line.rstrip("\n")
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise EventOutboxError("event JSONL contains a malformed line") from exc
                event_id = row.get("event_id")
                if not isinstance(event_id, str) or not event_id:
                    raise EventOutboxError("event JSONL contains a row without an event ID")
                canonical = json.dumps(
                    row, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                )
                prior = found.setdefault(event_id, canonical)
                if prior != canonical:
                    raise EventOutboxError(
                        "event JSONL contains conflicting event identities"
                    )
    finally:
        if fd >= 0:
            os.close(fd)
    return found


def _append_durable(path: Path, encoded: str) -> None:
    created = not path.exists()
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise EventOutboxError("event JSONL must be a singly linked regular file")
        payload = encoded.encode() + b"\n"
        written = 0
        while written < len(payload):
            count = os.write(fd, payload[written:])
            if count <= 0:
                raise EventOutboxError("event JSONL append made no progress")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    if created:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)


def dispatch_pending(
    con: LockedConnection,
    investigation_id: str,
    *,
    events_dir: str | None = None,
    limit: int = 100,
    checkpoint: Callable[[str, str], None] | None = None,
) -> list[str]:
    if _events_disabled():
        return []
    root = events_dir or default_events_dir()
    delivered: list[str] = []
    with investigation_event_lock(investigation_id, events_dir=root):
        rows = con.execute(
            "SELECT event_id, event_json, event_sha256 FROM write_event_outbox "
            "WHERE investigation_id = ? AND state = 'pending' "
            "ORDER BY outbox_sequence LIMIT ?",
            [investigation_id, int(limit)],
        ).fetchall()
        path = Path(root) / f"{investigation_id}.jsonl"
        existing = _existing_jsonl_events(path)
        for event_id, encoded, digest in rows:
            if hashlib.sha256(encoded.encode()).hexdigest() != digest:
                raise EventOutboxError("stored outbox digest does not match event bytes")
            prior = existing.get(event_id)
            if prior is not None and prior != encoded:
                raise EventOutboxError("event identity conflicts with durable trajectory bytes")
            if prior is None:
                if checkpoint:
                    checkpoint("before_append", event_id)
                _append_durable(path, encoded)
                existing[event_id] = encoded
                if checkpoint:
                    checkpoint("after_append", event_id)
            if checkpoint:
                checkpoint("before_receipt", event_id)
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute(
                    "UPDATE write_event_outbox SET state='delivered', "
                    "attempt_count=attempt_count+1, delivered_at=CURRENT_TIMESTAMP "
                    "WHERE event_id=? AND state='pending'",
                    [event_id],
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            delivered.append(event_id)
    return delivered


def dispatch_aggregate_pending(
    con: LockedConnection,
    investigation_id: str,
    *,
    aggregate_kind: str,
    aggregate_id: str,
    events_dir: str | None = None,
    checkpoint: Callable[[str, str], None] | None = None,
) -> list[str]:
    """Deliver only one aggregate's pending events under its stream lock."""
    if _events_disabled():
        return []
    root = events_dir or default_events_dir()
    delivered: list[str] = []
    with investigation_event_lock(investigation_id, events_dir=root):
        rows = con.execute(
            "SELECT event_id, event_json, event_sha256 FROM write_event_outbox "
            "WHERE investigation_id=? AND aggregate_kind=? AND aggregate_id=? "
            "AND state='pending' ORDER BY outbox_sequence",
            [investigation_id, aggregate_kind, aggregate_id],
        ).fetchall()
        path = Path(root) / f"{investigation_id}.jsonl"
        existing = _existing_jsonl_events(path)
        for event_id, encoded, digest in rows:
            if hashlib.sha256(encoded.encode()).hexdigest() != digest:
                raise EventOutboxError("stored outbox digest does not match event bytes")
            prior = existing.get(event_id)
            if prior is not None and prior != encoded:
                raise EventOutboxError("event identity conflicts with durable trajectory bytes")
            if prior is None:
                if checkpoint:
                    checkpoint("before_append", event_id)
                _append_durable(path, encoded)
                existing[event_id] = encoded
                if checkpoint:
                    checkpoint("after_append", event_id)
            if checkpoint:
                checkpoint("before_receipt", event_id)
            changed = con.execute(
                "UPDATE write_event_outbox SET state='delivered', "
                "attempt_count=attempt_count+1, delivered_at=CURRENT_TIMESTAMP "
                "WHERE event_id=? AND state='pending' AND aggregate_kind=? "
                "AND aggregate_id=? RETURNING event_id",
                [event_id, aggregate_kind, aggregate_id],
            ).fetchone()
            if changed is None:
                raise EventOutboxError("outbox delivery state changed unexpectedly")
            delivered.append(event_id)
    return delivered


def dispatch_pending_best_effort(
    con: LockedConnection,
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> list[str]:
    try:
        return _drain_investigation(con, investigation_id, events_dir=events_dir)
    except Exception as exc:
        print(f"write event delivery pending: {exc!r}", file=sys.stderr)
        return []


def recover_pending_events(
    db_path: str,
    *,
    events_dir: str | None = None,
    batch_size: int = 100,
) -> dict[str, list[str]]:
    from runtime.db_lock import connect_write

    recovered: dict[str, list[str]] = {}
    with connect_write(db_path, purpose="write/event_outbox_recovery") as con:
        investigations = [
            row[0]
            for row in con.execute(
                "SELECT investigation_id, MIN(outbox_sequence) AS first_sequence "
                "FROM write_event_outbox WHERE state='pending' "
                "GROUP BY investigation_id ORDER BY first_sequence"
            ).fetchall()
        ]
        for investigation_id in investigations:
            recovered[investigation_id] = _drain_investigation(
                con,
                investigation_id,
                events_dir=events_dir,
                batch_size=batch_size,
            )
    return recovered


def _drain_investigation(
    con: LockedConnection,
    investigation_id: str,
    *,
    events_dir: str | None,
    batch_size: int = 100,
) -> list[str]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    delivered: list[str] = []
    while True:
        batch = dispatch_pending(
            con,
            investigation_id,
            events_dir=events_dir,
            limit=batch_size,
        )
        delivered.extend(batch)
        if len(batch) < batch_size:
            return delivered

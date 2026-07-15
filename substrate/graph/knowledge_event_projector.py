"""Durable projection of canonical knowledge events into the graph."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import duckdb

from runtime.db_lock import LockedConnection, connect_write
from substrate.event_log import default_events_dir, iter_physical_events
from substrate.schemas.events import ActionType

from .insight_question import (
    graph_db_path,
    promote_from_marginalia_event,
    promote_from_note_event,
    promote_from_question_event,
)
from .schema import init_database_at_path

CONSUMER_NAME = "knowledge_graph_projector"
CONSUMER_VERSION = 1
_ACTIONS = {
    ActionType.NOTE_EMERGED.value: promote_from_note_event,
    ActionType.QUESTION_IDENTIFIED.value: promote_from_question_event,
    ActionType.MARGINALIA_NOTED.value: promote_from_marginalia_event,
}
_SAFE_INVESTIGATION_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}\Z")


class EventConsumerCorruption(RuntimeError):
    """A receipt or immutable event identity conflicts with durable state."""


class LegacyEventPayloadError(ValueError):
    """A complete knowledge event cannot be projected by consumer v1."""


class _PrecomputedEmbeddingProvider:
    def __init__(self, text: str, embedding: Any) -> None:
        self._text = text
        self._embedding = embedding

    def encode(self, text: str) -> Any:
        if text != self._text:
            raise EventConsumerCorruption("projection embedding text changed after admission")
        return self._embedding


@dataclass
class RecoveryReport:
    scanned: int = 0
    succeeded: int = 0
    already_received: int = 0
    quarantined: int = 0
    remaining: int | None = 0
    catching_up: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_investigations(events_dir: str) -> list[str]:
    """Return safe trajectory names and reject ambiguous filesystem shapes."""
    if not os.path.exists(events_dir):
        return []
    if os.path.islink(events_dir) or not os.path.isdir(events_dir):
        raise EventConsumerCorruption("event root must be a real directory")
    investigations: set[str] = set()
    with os.scandir(events_dir) as entries:
        for entry in entries:
            suffix = next((value for value in (".parquet", ".jsonl") if entry.name.endswith(value)), None)
            if suffix is None:
                continue
            investigation_id = entry.name[: -len(suffix)]
            if not _SAFE_INVESTIGATION_ID.fullmatch(investigation_id):
                raise EventConsumerCorruption(f"unsafe event filename: {entry.name}")
            stat_result = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or stat_result.st_nlink != 1:
                raise EventConsumerCorruption(f"unsafe event file: {entry.name}")
            investigations.add(investigation_id)
    return sorted(investigations)


def canonical_event_bytes(event: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EventConsumerCorruption("event cannot be canonically encoded") from exc


def _payload_error(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return "payload is not valid JSON"
    if not isinstance(payload, dict):
        return "payload is not an object"
    action_type = event.get("action_type")
    field_name = "question_text" if action_type == ActionType.QUESTION_IDENTIFIED.value else "note_text"
    text = payload.get(field_name)
    if not isinstance(text, str) or not text.strip():
        return f"payload has no non-empty {field_name}"
    return None


def _bounded_digest(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8", errors="replace")).hexdigest()


def _connect_write_with_handoff_retry(
    db_path: str, *, purpose: str, deadline: float
) -> LockedConnection:
    while True:
        try:
            return connect_write(
                db_path,
                purpose=purpose,
                timeout_s=max(0.001, deadline - time.monotonic()),
                poll_interval_s=0.02,
            )
        except duckdb.IOException as exc:
            if "Conflicting lock is held" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


def _project_one(
    con: LockedConnection,
    investigation_id: str,
    event: dict[str, Any],
    *,
    embedding_provider: Any,
    checkpoint: Callable[[str, str], None] | None,
) -> str:
    event_id = event.get("event_id")
    action_type = event.get("action_type")
    if not isinstance(event_id, str) or not event_id:
        raise EventConsumerCorruption("knowledge event is missing event_id")
    if action_type not in _ACTIONS:
        raise EventConsumerCorruption("projector received an unsupported action")
    if event.get("investigation_id") != investigation_id:
        raise EventConsumerCorruption("event investigation_id conflicts with its trajectory")
    event_sha256 = hashlib.sha256(canonical_event_bytes(event)).hexdigest()
    existing = con.execute(
        "SELECT investigation_id, action_type, event_sha256, status FROM event_consumer_receipts "
        "WHERE consumer_name=? AND consumer_version=? AND event_id=?",
        [CONSUMER_NAME, CONSUMER_VERSION, event_id],
    ).fetchone()
    if existing:
        if existing[:3] != (investigation_id, action_type, event_sha256) or existing[3] not in (
            "succeeded", "quarantined"
        ):
            raise EventConsumerCorruption(f"receipt identity conflict for event {event_id}")
        return "already_received"

    payload_error = _payload_error(event)
    if payload_error is not None:
        con.execute(
            "INSERT INTO event_consumer_receipts "
            "(consumer_name, consumer_version, investigation_id, event_id, action_type, "
            "event_sha256, status, error_class, error_digest, attempt_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 'quarantined', ?, ?, 1)",
            [
                CONSUMER_NAME,
                CONSUMER_VERSION,
                investigation_id,
                event_id,
                action_type,
                event_sha256,
                LegacyEventPayloadError.__name__,
                _bounded_digest(payload_error),
            ],
        )
        return "quarantined"

    output_ref = _ACTIONS[action_type](
        event,
        con=con,
        enabled=True,
        embedding_provider=embedding_provider,
        emit_graph_events=False,
    )
    if not output_ref:
        raise EventConsumerCorruption("validated knowledge event produced no graph node")
    if checkpoint:
        checkpoint("after_projection_before_receipt", event_id)
    con.execute(
        "INSERT INTO event_consumer_receipts "
        "(consumer_name, consumer_version, investigation_id, event_id, action_type, "
        "event_sha256, status, output_ref, attempt_count) "
        "VALUES (?, ?, ?, ?, ?, ?, 'succeeded', ?, 1)",
        [
            CONSUMER_NAME,
            CONSUMER_VERSION,
            investigation_id,
            event_id,
            action_type,
            event_sha256,
            output_ref,
        ],
    )
    return "succeeded"


def recover(
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    candidate_limit: int = 100,
    wall_time_s: float = 1.0,
    embedding_provider: Any = None,
    checkpoint: Callable[[str, str], None] | None = None,
) -> RecoveryReport:
    """Admit bounded unseen work; each admitted transaction runs to completion."""
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    if wall_time_s <= 0:
        raise ValueError("wall_time_s must be positive")
    db_path = db_path or graph_db_path()
    events_dir = events_dir or default_events_dir()
    init_database_at_path(db_path)
    deadline = time.monotonic() + wall_time_s
    report = RecoveryReport()
    candidates: list[tuple[str, dict[str, Any]]] = []
    with _connect_write_with_handoff_retry(
        db_path,
        purpose="knowledge_event_receipt_snapshot",
        deadline=time.monotonic() + 2.0,
    ) as snapshot_con:
        receipt_snapshot = {
            row[0]: row[1:]
            for row in snapshot_con.execute(
                "SELECT event_id, investigation_id, action_type, event_sha256, status "
                "FROM event_consumer_receipts "
                "WHERE consumer_name=? AND consumer_version=?",
                [CONSUMER_NAME, CONSUMER_VERSION],
            ).fetchall()
        }
    try:
        for investigation_id in discover_investigations(events_dir):
            if time.monotonic() >= deadline:
                report.catching_up = True
                report.remaining = None
                break
            source = iter_physical_events(
                investigation_id,
                events_dir=events_dir,
                lock_timeout_s=max(0.001, deadline - time.monotonic()),
            )
            try:
                for event in source:
                    if time.monotonic() >= deadline:
                        report.catching_up = True
                        report.remaining = None
                        break
                    if event.get("action_type") not in _ACTIONS:
                        continue
                    report.scanned += 1
                    event_id = event.get("event_id")
                    existing = receipt_snapshot.get(event_id)
                    if existing:
                        expected = (
                            investigation_id,
                            event.get("action_type"),
                            hashlib.sha256(canonical_event_bytes(event)).hexdigest(),
                        )
                        if existing[:3] != expected or existing[3] not in (
                            "succeeded",
                            "quarantined",
                        ):
                            raise EventConsumerCorruption(
                                f"receipt identity conflict for event {event_id}"
                            )
                        report.already_received += 1
                        continue
                    if len(candidates) >= candidate_limit or time.monotonic() >= deadline:
                        report.catching_up = True
                        report.remaining = None
                        break
                    candidates.append((investigation_id, event))
            finally:
                source.close()
            if report.catching_up:
                break
    finally:
        receipt_snapshot.clear()

    # Event locks are closed before embeddings. Each graph transaction then
    # holds the global writer only for deterministic mutation and its receipt.
    provider = embedding_provider
    for investigation_id, event in candidates:
        if time.monotonic() >= deadline:
            report.catching_up = True
            report.remaining = None
            break
        event_provider = provider
        if _payload_error(event) is None:
            if event_provider is None:
                from processing.embedding import default_embedding_provider

                provider = event_provider = default_embedding_provider()
            payload = event["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            field_name = (
                "question_text"
                if event["action_type"] == ActionType.QUESTION_IDENTIFIED.value
                else "note_text"
            )
            text = payload[field_name].strip()
            event_provider = _PrecomputedEmbeddingProvider(
                text, event_provider.encode(text)
            )
        con = _connect_write_with_handoff_retry(
            db_path,
            purpose="knowledge_event_projector",
            deadline=time.monotonic() + 2.0,
        )
        try:
            con.execute("BEGIN")
            try:
                outcome = _project_one(
                    con,
                    investigation_id,
                    event,
                    embedding_provider=event_provider,
                    checkpoint=checkpoint,
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            if outcome == "already_received":
                report.already_received += 1
            else:
                if checkpoint:
                    checkpoint("after_commit", str(event.get("event_id")))
                if outcome == "succeeded":
                    report.succeeded += 1
                else:
                    report.quarantined += 1
        finally:
            con.close()
    return report


def drain(
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    batch_size: int = 100,
    wall_time_s: float = 1.0,
    embedding_provider: Any = None,
) -> RecoveryReport:
    """Run bounded recovery batches until no unseen candidate remains."""
    total = RecoveryReport()
    while True:
        batch = recover(
            db_path=db_path,
            events_dir=events_dir,
            candidate_limit=batch_size,
            wall_time_s=wall_time_s,
            embedding_provider=embedding_provider,
        )
        total.scanned += batch.scanned
        total.succeeded += batch.succeeded
        total.already_received += batch.already_received
        total.quarantined += batch.quarantined
        total.errors.extend(batch.errors)
        if not batch.catching_up:
            total.remaining = 0
            total.catching_up = False
            return total
        if batch.succeeded + batch.quarantined == 0:
            raise TimeoutError("recovery batch made no progress within its wall-time bound")

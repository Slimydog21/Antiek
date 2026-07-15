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
from substrate.event_log import (
    default_events_dir,
    normalize_semantic_event,
    read_physical_event_page,
)
from substrate.event_log.events import PhysicalStorageCursor
from substrate.schemas.events import ActionType

from .insight_question import (
    graph_db_path,
    promote_from_marginalia_event,
    promote_from_note_event,
    promote_from_question_event,
)

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


class SchemaUnavailableError(RuntimeError):
    """The deployment-owned graph schema is not yet available."""


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
    unsupported: int = 0
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
            normalize_semantic_event(event),
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
                close_log_max_wait_s=0.0,
            )
        except duckdb.IOException as exc:
            if "Conflicting lock is held" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


def _resolve_one(
    con: LockedConnection,
    investigation_id: str,
    prior_cursor: PhysicalStorageCursor,
    event_cursor: PhysicalStorageCursor,
    event: dict[str, Any],
    normalized_sha256: str,
    *,
    embedding_provider: Any,
    checkpoint: Callable[[str, str], None] | None,
) -> str:
    event_id = event.get("event_id")
    action_type = event.get("action_type")
    if not isinstance(event_id, str) or not event_id:
        raise EventConsumerCorruption("knowledge event is missing event_id")
    if not isinstance(action_type, str) or not action_type:
        raise EventConsumerCorruption("knowledge event has invalid action_type")
    if event.get("investigation_id") != investigation_id:
        raise EventConsumerCorruption("event investigation_id conflicts with its trajectory")
    con.execute(
        "INSERT INTO event_consumer_frontiers "
        "(consumer_name, consumer_version, investigation_id, next_ordinal, chain_sha256) "
        "VALUES (?, ?, ?, 0, NULL) "
        "ON CONFLICT DO NOTHING",
        [CONSUMER_NAME, CONSUMER_VERSION, investigation_id],
    )
    frontier = con.execute(
        "SELECT next_ordinal, chain_sha256, snapshot_generation, snapshot_row_count, "
        "next_snapshot_row_offset, jsonl_byte_offset "
        "FROM event_consumer_frontiers "
        "WHERE consumer_name=? AND consumer_version=? AND investigation_id=?",
        [CONSUMER_NAME, CONSUMER_VERSION, investigation_id],
    ).fetchone()
    if frontier is None or frontier[2:] != (
        prior_cursor.snapshot_generation, prior_cursor.snapshot_row_count,
        prior_cursor.next_snapshot_row_offset, prior_cursor.jsonl_byte_offset,
    ):
        raced_identity = con.execute(
            "SELECT investigation_id, action_type, normalized_sha256 "
            "FROM event_consumer_events WHERE consumer_name=? AND consumer_version=? "
            "AND event_id=?", [CONSUMER_NAME, CONSUMER_VERSION, event_id]
        ).fetchone()
        if (
            raced_identity == (investigation_id, action_type, normalized_sha256)
            and frontier
            and frontier[2:]
            == (
                event_cursor.snapshot_generation,
                event_cursor.snapshot_row_count,
                event_cursor.next_snapshot_row_offset,
                event_cursor.jsonl_byte_offset,
            )
        ):
            return "raced"
        raise EventConsumerCorruption(f"physical frontier conflict for {investigation_id}")
    ordinal, prior_chain = frontier[:2]

    def advance_frontier(next_ordinal: int, chain_sha256: str | None) -> None:
        con.execute(
            "UPDATE event_consumer_frontiers SET next_ordinal=?, chain_sha256=?, "
            "snapshot_generation=?, snapshot_row_count=?, next_snapshot_row_offset=?, "
            "jsonl_byte_offset=?, updated_at=CURRENT_TIMESTAMP WHERE consumer_name=? "
            "AND consumer_version=? AND investigation_id=? AND next_ordinal=? "
            "AND chain_sha256 IS NOT DISTINCT FROM ? "
            "AND snapshot_generation IS NOT DISTINCT FROM ? AND snapshot_row_count=? "
            "AND next_snapshot_row_offset=? AND jsonl_byte_offset=?",
            [next_ordinal, chain_sha256,
             event_cursor.snapshot_generation, event_cursor.snapshot_row_count,
             event_cursor.next_snapshot_row_offset,
             event_cursor.jsonl_byte_offset, CONSUMER_NAME,
             CONSUMER_VERSION, investigation_id, ordinal, prior_chain,
             prior_cursor.snapshot_generation, prior_cursor.snapshot_row_count,
             prior_cursor.next_snapshot_row_offset, prior_cursor.jsonl_byte_offset],
        )
        current = con.execute(
            "SELECT next_ordinal, chain_sha256, snapshot_generation, snapshot_row_count, "
            "next_snapshot_row_offset, jsonl_byte_offset "
            "FROM event_consumer_frontiers WHERE consumer_name=? "
            "AND consumer_version=? AND investigation_id=?",
            [CONSUMER_NAME, CONSUMER_VERSION, investigation_id],
        ).fetchone()
        if current != (
            next_ordinal, chain_sha256,
            event_cursor.snapshot_generation, event_cursor.snapshot_row_count,
            event_cursor.next_snapshot_row_offset,
            event_cursor.jsonl_byte_offset,
        ):
            raise EventConsumerCorruption(f"frontier compare-and-swap failed at ordinal {ordinal}")

    existing = con.execute(
        "SELECT investigation_id, action_type, normalized_sha256 FROM event_consumer_events "
        "WHERE consumer_name=? AND consumer_version=? AND event_id=?",
        [CONSUMER_NAME, CONSUMER_VERSION, event_id],
    ).fetchone()
    if existing:
        if existing != (investigation_id, action_type, normalized_sha256):
            raise EventConsumerCorruption(f"event identity conflict for event {event_id}")
        advance_frontier(ordinal, prior_chain)
        return "already_received"

    chain_sha256 = hashlib.sha256("\0".join([
        prior_chain or "", str(ordinal), event_id, normalized_sha256,
    ]).encode()).hexdigest()
    resolution = "unsupported" if action_type not in _ACTIONS else "succeeded"

    payload_error = _payload_error(event) if action_type in _ACTIONS else None
    if payload_error is not None:
        con.execute(
            "INSERT INTO event_consumer_receipts "
            "(consumer_name, consumer_version, investigation_id, event_id, action_type, "
            "normalized_sha256, status, error_class, error_digest, attempt_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 'quarantined', ?, ?, 1)",
            [
                CONSUMER_NAME,
                CONSUMER_VERSION,
                investigation_id,
                event_id,
                action_type,
                normalized_sha256,
                LegacyEventPayloadError.__name__,
                _bounded_digest(payload_error),
            ],
        )
        resolution = "quarantined"
    elif action_type in _ACTIONS:
        output_ref = _ACTIONS[action_type](
            event, con=con, enabled=True, embedding_provider=embedding_provider,
            emit_graph_events=False,
        )
        if not output_ref:
            raise EventConsumerCorruption("validated knowledge event produced no graph node")
        if checkpoint:
            checkpoint("after_projection_before_receipt", event_id)
        con.execute(
            "INSERT INTO event_consumer_receipts "
            "(consumer_name, consumer_version, investigation_id, event_id, action_type, "
            "normalized_sha256, status, output_ref, attempt_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 'succeeded', ?, 1)",
            [CONSUMER_NAME, CONSUMER_VERSION, investigation_id, event_id,
             action_type, normalized_sha256, output_ref],
        )

    con.execute(
        "INSERT INTO event_consumer_events (consumer_name, consumer_version, "
        "investigation_id, logical_ordinal, event_id, action_type, normalized_sha256, "
        "resolution, chain_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [CONSUMER_NAME, CONSUMER_VERSION, investigation_id, ordinal, event_id,
         action_type, normalized_sha256, resolution, chain_sha256],
    )
    advance_frontier(ordinal + 1, chain_sha256)
    return resolution


def recover(
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    candidate_limit: int = 100,
    wall_time_s: float = 1.0,
    embedding_provider: Any = None,
    checkpoint: Callable[[str, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> RecoveryReport:
    """Admit work within a lock/admission budget; finish admitted transactions."""
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    if wall_time_s <= 0:
        raise ValueError("wall_time_s must be positive")
    db_path = db_path or graph_db_path()
    events_dir = events_dir or default_events_dir()
    # Schema ownership belongs to deployment. In particular, API startup must
    # never create a fresh DuckDB file that merely resembles an initialized DB.
    if not os.path.isfile(db_path):
        raise SchemaUnavailableError(f"graph database is unavailable: {db_path}")
    deadline = time.monotonic() + wall_time_s
    report = RecoveryReport()
    candidates: list[tuple[str, PhysicalStorageCursor, PhysicalStorageCursor,
                           dict[str, Any], str, bool]] = []
    with _connect_write_with_handoff_retry(
        db_path,
        purpose="knowledge_event_frontier_snapshot",
        deadline=deadline,
    ) as snapshot_con:
        frontier_snapshot = {
            row[0]: (row[1], row[2], row[3], row[4], row[5], row[6])
            for row in snapshot_con.execute(
                "SELECT investigation_id, next_ordinal, chain_sha256, snapshot_generation, "
                "snapshot_row_count, next_snapshot_row_offset, jsonl_byte_offset "
                "FROM event_consumer_frontiers "
                "WHERE consumer_name=? AND consumer_version=?",
                [CONSUMER_NAME, CONSUMER_VERSION],
            ).fetchall()
        }
        known_event_ids = {row[0] for row in snapshot_con.execute(
            "SELECT event_id FROM event_consumer_events WHERE consumer_name=? "
            "AND consumer_version=?", [CONSUMER_NAME, CONSUMER_VERSION]
        ).fetchall()}
    investigations = discover_investigations(events_dir)
    # Least-advanced trajectories run first. A perpetually hot lexicographic
    # predecessor therefore cannot monopolize every bounded recovery pass.
    investigations.sort(
        key=lambda value: (
            frontier_snapshot.get(value, (0, None, None, 0, 0, 0))[0], value
        )
    )
    per_investigation_limit = max(1, candidate_limit // max(1, len(investigations)))
    admitted_event_ids = set(known_event_ids)
    for investigation_id in investigations:
        if len(candidates) >= candidate_limit or time.monotonic() >= deadline:
            report.catching_up = True
            report.remaining = None
            break
        _ordinal, _chain, generation, row_count, snapshot_offset, tail_offset = (
            frontier_snapshot.get(investigation_id, (0, None, None, 0, 0, 0))
        )
        prior_cursor = PhysicalStorageCursor(
            generation, row_count, snapshot_offset, tail_offset
        )
        remaining_budget = min(
            per_investigation_limit, candidate_limit - len(candidates)
        )
        page = read_physical_event_page(
            investigation_id,
            storage_cursor=prior_cursor,
            limit=remaining_budget,
            scan_limit=remaining_budget,
            deadline=deadline,
            events_dir=events_dir,
            lock_timeout_s=max(0.001, deadline - time.monotonic()),
        )
        transaction_cursor = prior_cursor
        for observation in page.observations:
            event_id = observation.event.get("event_id")
            candidates.append(
                (
                    investigation_id,
                    transaction_cursor,
                    observation.cursor_after,
                    observation.event,
                    observation.normalized_sha256,
                    event_id in admitted_event_ids,
                )
            )
            if isinstance(event_id, str):
                admitted_event_ids.add(event_id)
            transaction_cursor = observation.cursor_after
        report.scanned += page.scanned
        if page.has_more:
            report.catching_up = True
            report.remaining = None
            continue

    # Event locks are closed before embeddings. Each graph transaction then
    # holds the global writer only for deterministic mutation and its receipt.
    provider = embedding_provider
    for (investigation_id, prior_cursor, event_cursor, event,
         normalized_sha256, known_at_admission) in candidates:
        if should_stop is not None and should_stop():
            report.catching_up = True
            report.remaining = None
            break
        event_provider = provider
        if (not known_at_admission and event.get("action_type") in _ACTIONS
                and _payload_error(event) is None):
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
        # Embedding providers are not interruptible. Re-check immediately after
        # that potentially slow call so shutdown cannot begin a new mutation.
        if should_stop is not None and should_stop():
            report.catching_up = True
            report.remaining = None
            break
        con = _connect_write_with_handoff_retry(
            db_path,
            purpose="knowledge_event_projector",
            deadline=max(deadline, time.monotonic() + wall_time_s),
        )
        try:
            con.execute("BEGIN")
            try:
                outcome = _resolve_one(
                    con,
                    investigation_id,
                    prior_cursor,
                    event_cursor,
                    event,
                    normalized_sha256,
                    embedding_provider=event_provider,
                    checkpoint=checkpoint,
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            if outcome in ("already_received", "raced"):
                report.already_received += 1
            else:
                if checkpoint:
                    checkpoint("after_commit", str(event.get("event_id")))
                if outcome == "succeeded":
                    report.succeeded += 1
                elif outcome == "quarantined":
                    report.quarantined += 1
                elif outcome == "unsupported":
                    report.unsupported += 1
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
        total.unsupported += batch.unsupported
        total.errors.extend(batch.errors)
        if not batch.catching_up:
            total.remaining = 0
            total.catching_up = False
            return total
        if (
            batch.succeeded
            + batch.quarantined
            + batch.unsupported
            + batch.already_received
            == 0
        ):
            raise TimeoutError("recovery batch made no progress within its wall-time bound")

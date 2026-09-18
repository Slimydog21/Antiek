"""Durable, at-most-once automatic replay for recursive note synthesis."""

from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from runtime.db_lock import connect_write
from substrate.event_log import default_events_dir, iter_physical_events
from substrate.graph import default_db_path
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import ConfidenceLevel, NoteEmergedPayload
from substrate.write.event_outbox import (
    build_typed_envelope,
    dispatch_aggregate_pending,
    enqueue_event,
)

from .parser import parse_notes_response
from .prompt import NOTE_TAKER_SYSTEM_PROMPT

CONSUMER_VERSION = 3  # v3: passage-aligned prompt + doc excerpts in window
QUALIFYING_ACTION_TYPES = frozenset(
    {
        "distillation.delivered",
        "claim.grounding_check_passed",
        "claim.grounding_check_failed",
        # Loop One / spin-research (Mini dogfood 2026-09-18)
        "evidence.retrieve.delivered",
        "synthesize.delivered",
        "decompose.delivered",
        "connector.delivered",
        "parameter_extract.delivered",
    }
)


class NoteTakerReplayCorruption(RuntimeError):
    """Stored replay evidence or an immutable identity conflicts."""


_locks_guard = threading.Lock()
_locks: dict[tuple[str, str], threading.Lock] = {}
_schema_locks: dict[str, threading.Lock] = {}


@contextmanager
def _replay_lock(
    investigation_id: str, events_dir: str, timeout_s: float = 30.0
) -> Iterator[None]:
    """Cross-process ownership for discovery, provider entry, and recovery."""
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    if (
        not investigation_id
        or investigation_id[0] not in safe.replace("-", "")
        or any(c not in safe for c in investigation_id)
    ):
        raise ValueError("investigation_id is not safe for replay storage")
    os.makedirs(events_dir, mode=0o700, exist_ok=True)
    path = os.path.join(events_dir, f".{investigation_id}.note-taker-replay.lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "timed out waiting for note-taker replay ownership"
                    ) from None
                time.sleep(0.05)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _window_id(investigation_id: str, threshold: int, event_ids: list[str]) -> str:
    identity = _canonical(
        {
            "consumer": "note-taker",
            "consumer_version": CONSUMER_VERSION,
            "investigation_id": investigation_id,
            "threshold": threshold,
            "source_event_ids": event_ids,
        }
    )
    return _digest(identity)


def _configuration_fingerprint(threshold: int) -> tuple[str, str]:
    prompt_sha256 = _digest(NOTE_TAKER_SYSTEM_PROMPT)
    configuration = _canonical(
        {
            "consumer": "note-taker",
            "consumer_version": CONSUMER_VERSION,
            "threshold": threshold,
            "prompt_sha256": prompt_sha256,
        }
    )
    return prompt_sha256, _digest(configuration)


def _assert_complete_tail(investigation_id: str, events_dir: str) -> None:
    path = Path(events_dir) / f"{investigation_id}.jsonl"
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("rb") as stream:
        stream.seek(-1, os.SEEK_END)
        if stream.read(1) != b"\n":
            raise NoteTakerReplayCorruption("incomplete JSONL tail")


def _document_excerpts_for_prompt(db_path: str, document_id: str | None) -> str:
    """Best-effort book surface for the note-taker window (read-oriented).

    Caps total characters so the provider prompt stays bounded. Empty when
    the document is unknown or the DB cannot be opened.
    """
    if not isinstance(document_id, str) or not document_id.strip():
        return ""
    if document_id.startswith("research:"):
        return ""
    try:
        from runtime.db_lock import connect_read
    except ImportError:
        return ""
    try:
        with connect_read(db_path) as con:
            rows = con.execute(
                "SELECT text FROM chunks WHERE document_id = ? "
                "ORDER BY chunk_id ASC LIMIT 8",
                [document_id.strip()],
            ).fetchall()
    except Exception:
        return ""
    parts: list[str] = []
    total = 0
    for (text,) in rows:
        if not text:
            continue
        snippet = str(text).strip()
        if not snippet:
            continue
        if total + len(snippet) > 2400:
            snippet = snippet[: max(0, 2400 - total)]
        parts.append(snippet)
        total += len(snippet)
        if total >= 2400:
            break
    return "\n---\n".join(parts)


def _render_event(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return f"[{event['event_id']}] {event.get('action_type')}: {_canonical(payload or {})}"




def _resolve_note_document_id(
    investigation_id: str,
    request: dict[str, Any],
    *,
    events_dir: str,
) -> str:
    """note.emerged requires envelope document_id (sec 9.1).

    Loop One may omit document_id; parse spawn_context or use research: synthetic.
    """
    doc = request.get("document_id")
    if isinstance(doc, str) and doc.strip():
        return doc.strip()
    for event in iter_physical_events(investigation_id, events_dir=events_dir):
        env_doc = event.get("document_id")
        if isinstance(env_doc, str) and env_doc.strip():
            return env_doc.strip()
        payload = event.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                payload = {}
        sc = payload.get("spawn_context") if isinstance(payload, dict) else None
        if isinstance(sc, str) and sc.startswith("read: passage "):
            parts = sc.split()
            if len(parts) >= 3 and parts[2].strip():
                return parts[2].strip()
    return f"research:{investigation_id}"


def _promote_delivered_notes(
    investigation_id: str,
    delivered_ids: list[str],
    *,
    events_dir: str,
    db_path: str,
) -> None:
    """Project note.emerged into insight nodes for distill/AutoNotebook.

    Mini dogfood disables knowledge-projector recovery; without inline
    promote, note.emerged never becomes GRAPH_NODE_INSERTED.
    """
    if not delivered_ids:
        return
    try:
        from substrate.graph.insight_question import promote_from_note_event
    except ImportError:  # pragma: no cover
        return
    want = set(delivered_ids)
    for event in iter_physical_events(investigation_id, events_dir=events_dir):
        if event.get("event_id") not in want:
            continue
        if event.get("action_type") != "note.emerged":
            continue
        try:
            # emit_graph_events=False: GRAPH_NODE_INSERTED uses the same
            # investigation delivery.lock as outbox dispatch; nesting/racing
            # it after note.emerged delivery can TimeoutError for 10s and
            # still leave distill empty. Nodes land in DuckDB here;
            # distillation_for also resolves insight ids from note.emerged.
            promote_from_note_event(
                event,
                enabled=True,
                emit_graph_events=False,
                events_dir=events_dir,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"note_taker.replay: promote_from_note_event failed for "
                f"{event.get('event_id')}: {type(exc).__name__}: {exc}",
                flush=True,
            )


class DurableNoteTakerReplay:
    """Discover fixed physical windows and advance their durable state machine."""

    def __init__(
        self,
        dispatcher: Callable[..., Any],
        *,
        db_path: str | None = None,
        events_dir: str | None = None,
        threshold: int = 5,
        checkpoint: Callable[[str, str], None] | None = None,
    ) -> None:
        if threshold < 1:
            raise ValueError("threshold must be positive")
        self.dispatcher = dispatcher
        self.db_path = db_path or default_db_path()
        self.events_dir = events_dir or default_events_dir()
        self.threshold = threshold
        self.checkpoint = checkpoint

    def _check(self, name: str, window_id: str) -> None:
        if self.checkpoint:
            self.checkpoint(name, window_id)

    def _ensure_schema(self) -> None:
        absolute_db_path = os.path.abspath(self.db_path)
        with _locks_guard:
            schema_lock = _schema_locks.setdefault(absolute_db_path, threading.Lock())
        with schema_lock:
            init_database_at_path(self.db_path)

    def catch_up(self, investigation_id: str) -> list[str]:
        absolute_db_path = os.path.abspath(self.db_path)
        key = (absolute_db_path, investigation_id)
        with _locks_guard:
            lock = _locks.setdefault(key, threading.Lock())
        with lock, _replay_lock(investigation_id, self.events_dir):
            delivered = self._catch_up_locked(investigation_id)
        # Promote AFTER releasing the replay/delivery locks — emitting
        # GRAPH_NODE_INSERTED under the replay lock deadlocks the event lock.
        _promote_delivered_notes(
            investigation_id,
            delivered,
            events_dir=self.events_dir,
            db_path=self.db_path,
        )
        return delivered

    def _catch_up_locked(self, investigation_id: str) -> list[str]:
        _assert_complete_tail(investigation_id, self.events_dir)
        physical = list(iter_physical_events(investigation_id, events_dir=self.events_dir))
        qualifying: list[dict[str, Any]] = []
        observed: dict[str, str] = {}
        for event in physical:
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                raise NoteTakerReplayCorruption("physical event has no event_id")
            if event.get("investigation_id") != investigation_id:
                raise NoteTakerReplayCorruption("physical event investigation identity conflicts")
            normalized = _canonical(event)
            prior = observed.get(event_id)
            if prior is not None:
                if prior != normalized:
                    raise NoteTakerReplayCorruption(
                        f"physical event identity conflicts for {event_id}"
                    )
                continue
            observed[event_id] = normalized
            if (
                event.get("action_type") in QUALIFYING_ACTION_TYPES
                and event.get("role") != "note_taker"
            ):
                qualifying.append(event)

        complete = len(qualifying) // self.threshold
        # A stream with no qualifying events has no replay identity to create,
        # validate, or recover. Return before opening DuckDB at all: even a
        # read-only connection in the API process can race a cross-process
        # deploy writer at DuckDB's native file lock. Non-empty partial windows
        # still validate configuration drift below.
        if not qualifying:
            return []

        self._ensure_schema()
        prompt_sha256, configuration_sha256 = _configuration_fingerprint(self.threshold)
        expected_configuration = (
            self.threshold,
            prompt_sha256,
            configuration_sha256,
        )
        with connect_write(self.db_path, purpose="note_taker/replay_discovery") as con:
            existing_configuration = con.execute(
                "SELECT threshold, prompt_sha256, configuration_sha256 "
                "FROM note_taker_configurations WHERE consumer_version=? "
                "AND investigation_id=?",
                [CONSUMER_VERSION, investigation_id],
            ).fetchone()
            if existing_configuration is None:
                con.execute(
                    "INSERT INTO note_taker_configurations (consumer_version, "
                    "investigation_id, threshold, prompt_sha256, "
                    "configuration_sha256) VALUES (?, ?, ?, ?, ?)",
                    [
                        CONSUMER_VERSION,
                        investigation_id,
                        self.threshold,
                        prompt_sha256,
                        configuration_sha256,
                    ],
                )
            elif existing_configuration != expected_configuration:
                raise NoteTakerReplayCorruption(
                    "note-taker configuration drift requires an explicit "
                    "consumer-version migration"
                )
            con.execute(
                "UPDATE note_taker_windows SET state='uncertain', "
                "uncertainty_reason='process ownership lost while provider outcome was unknown', "
                "updated_at=CURRENT_TIMESTAMP WHERE investigation_id=? AND consumer_version=? "
                "AND state='calling'",
                [investigation_id, CONSUMER_VERSION],
            )
        # Historical streams can contain thousands of windows. Never hold the
        # global DuckDB writer lock across the complete backfill: one bounded
        # transaction per window lets API writes and deploy verifiers make
        # progress while preserving deterministic ordinal discovery.
        for ordinal in range(complete):
            window = qualifying[ordinal * self.threshold : (ordinal + 1) * self.threshold]
            ids = [row["event_id"] for row in window]
            window_id = _window_id(investigation_id, self.threshold, ids)
            source_json = _canonical(ids)
            source_digest = _digest(source_json)
            document_id = window[-1].get("document_id") or _resolve_note_document_id(
                investigation_id, {}, events_dir=self.events_dir
            )
            doc_excerpts = _document_excerpts_for_prompt(
                self.db_path, document_id
            )
            prompt_body = NOTE_TAKER_SYSTEM_PROMPT + "\n\n"
            if doc_excerpts:
                prompt_body += (
                    "Document excerpts (ground notes against these):\n"
                    + doc_excerpts
                    + "\n\n"
                )
            prompt_body += (
                "\n".join(map(_render_event, window))
                + "\n\nNow produce the JSON object."
            )
            request = {
                "document_id": document_id,
                "investigation_id": investigation_id,
                "prompt": prompt_body,
                "role": "note_taker",
                "source_event_ids": ids,
            }
            request_json = _canonical(request)
            prepared = False
            with connect_write(
                self.db_path, purpose="note_taker/replay_discover_window"
            ) as con:
                existing = con.execute(
                    "SELECT window_id, source_event_ids_json, source_digest, request_json, request_sha256, "
                    "provider_idempotency_key FROM note_taker_windows WHERE consumer_version=? "
                    "AND investigation_id=? AND threshold=? AND ordinal=?",
                    [CONSUMER_VERSION, investigation_id, self.threshold, ordinal],
                ).fetchone()
                fingerprint = (
                    window_id,
                    source_json,
                    source_digest,
                    request_json,
                    _digest(request_json),
                    window_id,
                )
                if existing and existing != fingerprint:
                    raise NoteTakerReplayCorruption(
                        f"window identity conflict at ordinal {ordinal}"
                    )
                if not existing:
                    con.execute(
                        "INSERT INTO note_taker_windows (window_id, consumer_version, investigation_id, "
                        "threshold, ordinal, first_event_id, last_event_id, source_event_ids_json, "
                        "source_digest, request_json, request_sha256, provider_idempotency_key, state) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared')",
                        [
                            window_id,
                            CONSUMER_VERSION,
                            investigation_id,
                            self.threshold,
                            ordinal,
                            ids[0],
                            ids[-1],
                            source_json,
                            source_digest,
                            request_json,
                            _digest(request_json),
                            window_id,
                        ],
                    )
                    prepared = True
            if prepared:
                self._check("prepared", window_id)

        delivered: list[str] = []
        for ordinal in range(complete):
            delivered.extend(self._advance(investigation_id, ordinal))
        return delivered

    def _validated_call(self, request_json: str, key: str) -> Callable[[], Any]:
        """Complete local validation before recording provider entry."""
        request = json.loads(request_json)
        if not isinstance(request, dict):
            raise TypeError("stored provider request must be an object")
        try:
            params = inspect.signature(self.dispatcher).parameters
        except (TypeError, ValueError) as exc:
            # CPython 3.12+ may raise ValueError for bogus __signature__;
            # keep the local-validation contract as TypeError so the window
            # stays prepared (test_local_pre_dispatch_validation_*).
            raise TypeError("dispatcher signature is not inspectable") from exc
        if "idempotency_key" in params:
            return lambda: self.dispatcher(request, idempotency_key=key)
        if len(params) >= 2:
            return lambda: self.dispatcher(request, key)
        return lambda: self.dispatcher(request)

    def _advance(self, investigation_id: str, ordinal: int) -> list[str]:
        with connect_write(self.db_path, purpose="note_taker/replay_advance") as con:
            row = con.execute(
                "SELECT window_id, state, request_json, request_sha256, provider_idempotency_key, "
                "raw_result, raw_result_sha256, source_event_ids_json FROM note_taker_windows "
                "WHERE consumer_version=? AND investigation_id=? AND threshold=? AND ordinal=?",
                [CONSUMER_VERSION, investigation_id, self.threshold, ordinal],
            ).fetchone()
            if row is None:
                raise NoteTakerReplayCorruption("discovered window disappeared")
            window_id, state, request_json, request_sha, key, raw, raw_sha, source_json = row
            if _digest(request_json) != request_sha:
                raise NoteTakerReplayCorruption("stored request digest mismatch")
            if state in ("uncertain", "completed"):
                return []
            if state == "prepared":
                self._check("before_provider_call", window_id)
                call = self._validated_call(request_json, key)
                changed = con.execute(
                    "UPDATE note_taker_windows SET state='calling', attempt_count=attempt_count+1, "
                    "updated_at=CURRENT_TIMESTAMP WHERE window_id=? AND state='prepared' RETURNING window_id",
                    [window_id],
                ).fetchone()
                if changed is None:
                    raise NoteTakerReplayCorruption("prepared window ownership changed")
                state = "calling"
        if state == "calling":
            self._check("after_calling_commit", window_id)
            try:
                result = call()
                self._check("after_provider_return", window_id)
                text = result if isinstance(result, str) else result.text
                provider = getattr(result, "provider", None)
                model = getattr(result, "model", None)
                policy_id = f"{provider}/{model}" if provider and model else None
                if not isinstance(text, str):
                    raise TypeError("provider result text must be a string")
                with connect_write(self.db_path, purpose="note_taker/replay_store_result") as con:
                    changed = con.execute(
                        "UPDATE note_taker_windows SET state='result_stored', raw_result=?, "
                        "raw_result_sha256=?, provider=?, model=?, policy_id=?, updated_at=CURRENT_TIMESTAMP "
                        "WHERE window_id=? AND state='calling' RETURNING window_id",
                        [text, _digest(text), provider, model, policy_id, window_id],
                    ).fetchone()
                    if changed is None:
                        raise NoteTakerReplayCorruption("calling window ownership changed")
                self._check("after_result_commit", window_id)
                raw, raw_sha, state = text, _digest(text), "result_stored"
            except Exception as exc:
                with connect_write(self.db_path, purpose="note_taker/replay_uncertain") as con:
                    changed = con.execute(
                        "UPDATE note_taker_windows SET state='uncertain', uncertainty_reason=?, "
                        "updated_at=CURRENT_TIMESTAMP WHERE window_id=? AND state='calling' RETURNING window_id",
                        [f"provider outcome unknown: {type(exc).__name__}", window_id],
                    ).fetchone()
                    if changed is None:
                        raise NoteTakerReplayCorruption("calling window ownership changed") from exc
                raise
        if state == "result_stored":
            if raw is None or raw_sha is None or _digest(raw) != raw_sha:
                raise NoteTakerReplayCorruption("stored provider result digest mismatch")
            source_ids = json.loads(source_json)
            notes = parse_notes_response(raw, canonical_event_ids=source_ids)
            with connect_write(self.db_path, purpose="note_taker/replay_materialize") as con:
                con.execute("BEGIN TRANSACTION")
                try:
                    for index, note in enumerate(notes):
                        normalized = note.text.strip()
                        identity = _canonical(
                            {
                                "window_id": window_id,
                                "index": index,
                                "text": normalized,
                                "confidence": note.confidence,
                                "source_event_ids": list(note.source_event_ids),
                            }
                        )
                        note_id = "n-" + _digest(identity)[:24]
                        event_id = "evt-note-" + _digest("event:" + identity)[:24]
                        event = build_typed_envelope(
                            investigation_id,
                            NoteEmergedPayload(
                                note_id=note_id,
                                note_text=normalized,
                                source_event_ids=list(note.source_event_ids),
                                confidence=cast(ConfidenceLevel, note.confidence),
                                node_id=None,
                            ),
                            parent_event_id=source_ids[-1],
                            role="note_taker",
                            policy_id=con.execute(
                                "SELECT policy_id FROM note_taker_windows WHERE window_id=?",
                                [window_id],
                            ).fetchone()[0],
                            event_id=event_id,
                            emitted_at=datetime.now(UTC),
                            document_id=_resolve_note_document_id(
                                investigation_id,
                                json.loads(request_json),
                                events_dir=self.events_dir,
                            ),
                        )
                        enqueue_event(
                            con,
                            operation_id=f"note-taker-v2:{window_id}:{index}",
                            aggregate_kind="note_taker_window",
                            aggregate_id=window_id,
                            event=event,
                        )
                    changed = con.execute(
                        "UPDATE note_taker_windows SET state='materialized', updated_at=CURRENT_TIMESTAMP "
                        "WHERE window_id=? AND state='result_stored' RETURNING window_id",
                        [window_id],
                    ).fetchone()
                    if changed is None:
                        raise NoteTakerReplayCorruption("result-stored window ownership changed")
                    con.execute("COMMIT")
                except Exception:
                    con.execute("ROLLBACK")
                    raise
            self._check("after_materialize_commit", window_id)
        with connect_write(self.db_path, purpose="note_taker/replay_delivery") as con:
            delivered = dispatch_aggregate_pending(
                con,
                investigation_id,
                aggregate_kind="note_taker_window",
                aggregate_id=window_id,
                events_dir=self.events_dir,
                checkpoint=self.checkpoint,
            )
            pending = con.execute(
                "SELECT COUNT(*) FROM write_event_outbox WHERE aggregate_kind='note_taker_window' "
                "AND aggregate_id=? AND state!='delivered'",
                [window_id],
            ).fetchone()[0]
            if not pending:
                changed = con.execute(
                    "UPDATE note_taker_windows SET state='completed', updated_at=CURRENT_TIMESTAMP "
                    "WHERE window_id=? AND state='materialized' RETURNING window_id",
                    [window_id],
                ).fetchone()
                if changed is None:
                    current = con.execute(
                        "SELECT state FROM note_taker_windows WHERE window_id=?", [window_id]
                    ).fetchone()
                    if current != ("completed",):
                        raise NoteTakerReplayCorruption("materialized window ownership changed")
            return delivered


__all__ = [
    "CONSUMER_VERSION",
    "DurableNoteTakerReplay",
    "NoteTakerReplayCorruption",
    "QUALIFYING_ACTION_TYPES",
]

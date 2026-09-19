#!/usr/bin/env python3
"""
Typed event log for Antiek — the on-policy RL trajectory substrate.

Migrated from Researchmaxx ``events.py`` (2026-05-16). The shape is
unchanged; what's new is the Section "Wrestling" of the ActionType enum,
which captures the document-wrestling loop documented in
``docs/architecture_notes.md`` §9.

This is the "typed events first" recommendation, refined by the
architectural directive: **trajectory data is Parquet, append-only,
separated from the graph (DuckDB).** The graph stays in
``~/.antiek/research_graph.duckdb``; events live independently at
``~/.antiek/research_events/``.

Storage model
-------------
Per investigation:
  Live phase  : ``{ANTIEK_RESEARCH_EVENTS_DIR}/{investigation_id}.jsonl``
                One JSON object per line, append-only. No read-modify-write.
  Sealed phase: ``{ANTIEK_RESEARCH_EVENTS_DIR}/{investigation_id}.parquet``
                Atomic rewrite of the JSONL at investigation completion.
                After sealing, the JSONL is deleted.

Why append-only JSONL → sealed Parquet (not direct Parquet)?
  Parquet is columnar and not append-friendly mid-investigation. Writing
  to JSONL during the live run gives us crash-safety and zero contention;
  sealing to Parquet at completion gives us the columnar, schema-typed
  long-term format the downstream RL pipelines want. This is the common
  pattern in event-sourcing systems (write-ahead log → compacted snapshot).

Why not DuckDB?
  The graph DB is the substrate for the knowledge graph. Trajectory data
  is conceptually different: append-only, schema-versioned over time,
  consumed by a different toolchain (Prime Intellect verifiers / prime-rl /
  Hosted Training). Mixing them in DuckDB couples lifecycle, complicates
  per-policy data partitioning, and forecloses moving the trajectory store
  to object storage later without a migration. Querying remains
  DuckDB-native via ``read_parquet('research_events/*.parquet')``.

Schema (v3)
-----------
Each event row carries:
  event_id          stable unique id
  investigation_id  scope key
  synthesis_id      nullable; set once archive_synthesis returns
  phase             nullable; maps to AUTONOMOUS_RESEARCH_PHASES
  role              nullable; e.g. 'decomposer', 'note_taker', 'grounder'
  action_type       typed; see ActionType enum
  payload           opaque JSON dict (action-type-specific)
  parent_event_id   nullable; lets us reconstruct nested spans
  policy_id         REQUIRED; identifies the policy that produced the
                    artifact. Format: ``{model_id}/{prompt_version}`` for
                    LLM calls; ``orchestrator-deterministic`` for code-only
                    events. This is what lets downstream pipelines exclude
                    closed-weight trajectories from open-weight RL training.
  param_version     ANTIEK_PARAM_VERSION at emission time
  schema_version    bumps when payload shape changes for a given action
  emitted_at        ISO8601 UTC
  document_id       nullable; set for wrestling-loop events anchored to a
                    document. Optional on every other event.

Failure handling
----------------
Ordinary telemetry emits remain non-fatal through ``_safe``. Durable command
paths use ``append_event_once`` instead: append failures propagate so their
database receipt can drive an exact retry.

Environment toggles
-------------------
ANTIEK_RESEARCH_EVENTS_DIR    override default events dir
ANTIEK_EVENTS_DISABLED        "1"/"true"/"yes" → no events written
ANTIEK_HOME                   override base dir (defaults to ~/.antiek)
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import stat
import sys
import time
import traceback
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Package-relative imports work in installed mode (`pip install -e .`).
# For direct-script execution (`python events.py ...`), fall back to a
# sys.path-based lookup so the CLI still works in dev.
try:
    from ..constants import ANTIEK_PARAM_VERSION
    from ..investigation_streams import (
        OpenedInvestigationStream,
        open_investigation_stream,
    )
    from ..investigation_tenancy import InvestigationAuthority
    from ..schemas.events import (
        DEFAULT_POLICY_ID,
        EVENT_SCHEMA_VERSION,
        ActionType,
        Event,
        InvestigationExecutionClaimedPayload,
        InvestigationExecutionCompletedPayload,
        InvestigationExecutionRenewedPayload,
        InvestigationExecutionTakenOverPayload,
        InvestigationStartRequestedPayload,
        ResearchCallReleasedPayload,
        ResearchCallReservedPayload,
        ResearchCallSettledPayload,
        ResearchDelegationAcceptedPayload,
        ResearchDelegationIssuedPayload,
        ResearchDelegationReleasedPayload,
        ResearchDelegationReservedPayload,
        ResearchDelegationSettledPayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from constants import (  # type: ignore[no-redef,import-not-found]
        ANTIEK_PARAM_VERSION,
    )
    from investigation_streams import (  # type: ignore[no-redef,import-not-found]
        OpenedInvestigationStream,
        open_investigation_stream,
    )
    from investigation_tenancy import (  # type: ignore[no-redef,import-not-found]
        InvestigationAuthority,
    )
    from schemas.events import (  # type: ignore[no-redef,import-not-found]
        DEFAULT_POLICY_ID,
        EVENT_SCHEMA_VERSION,
        ActionType,
        Event,
        InvestigationExecutionClaimedPayload,
        InvestigationExecutionCompletedPayload,
        InvestigationExecutionRenewedPayload,
        InvestigationExecutionTakenOverPayload,
        InvestigationStartRequestedPayload,
        ResearchCallReleasedPayload,
        ResearchCallReservedPayload,
        ResearchCallSettledPayload,
        ResearchDelegationAcceptedPayload,
        ResearchDelegationIssuedPayload,
        ResearchDelegationReleasedPayload,
        ResearchDelegationReservedPayload,
        ResearchDelegationSettledPayload,
    )

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CURRENT_INVESTIGATION_AUTHORITY: ContextVar[InvestigationAuthority | None] = (
    ContextVar("antiek_current_investigation_authority", default=None)
)
_CURRENT_EXECUTION_FENCE: ContextVar[tuple[str, int, str] | None] = ContextVar(
    "antiek_current_execution_fence", default=None
)


@contextmanager
def investigation_authority_context(
    authority: InvestigationAuthority,
) -> Iterator[None]:
    """Bind machine authority across one in-process event-handler task tree."""
    token = _CURRENT_INVESTIGATION_AUTHORITY.set(authority)
    try:
        yield
    finally:
        _CURRENT_INVESTIGATION_AUTHORITY.reset(token)


def current_investigation_authority(
    investigation_id: str,
) -> InvestigationAuthority | None:
    authority = _CURRENT_INVESTIGATION_AUTHORITY.get()
    if authority is not None and authority.investigation_id == investigation_id:
        return authority
    return None


def trajectory_contextual(investigation_id: str) -> list[dict[str, Any]]:
    """Read the account stream bound to this task, else the legacy stream."""
    authority = current_investigation_authority(investigation_id)
    if authority is not None:
        return trajectory_authorized(authority)
    return trajectory(investigation_id)


@contextmanager
def investigation_execution_context(
    authority: InvestigationAuthority, *, generation: int, holder_digest: str
) -> Iterator[None]:
    """Fence every durable mutation in one executor task tree."""
    if generation < 1 or len(holder_digest) != 64:
        raise ValueError("execution context is invalid")
    authority_token = _CURRENT_INVESTIGATION_AUTHORITY.set(authority)
    execution_token = _CURRENT_EXECUTION_FENCE.set(
        (authority.investigation_id, generation, holder_digest)
    )
    try:
        yield
    finally:
        _CURRENT_EXECUTION_FENCE.reset(execution_token)
        _CURRENT_INVESTIGATION_AUTHORITY.reset(authority_token)


def current_investigation_execution(
    investigation_id: str,
) -> tuple[int, str] | None:
    fence = _CURRENT_EXECUTION_FENCE.get()
    if fence is None or fence[0] != investigation_id:
        return None
    return fence[1], fence[2]


@contextmanager
def investigation_execution_mutation(
    authority: InvestigationAuthority,
) -> Iterator[None]:
    """Hold takeover exclusion across one fenced external mutation."""
    fence = current_investigation_execution(authority.investigation_id)
    if fence is None:
        yield
        return
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_execution_mutation_lock(stream),
    ):
        with _authorized_event_lock(stream):
            rows = _validate_authorized_rows(
                authority, _read_opened_event_rows(stream, reject_malformed=True)
            )
            snapshot, _ = _investigation_execution_ledger(authority, rows)
            if (
                snapshot is None
                or snapshot.completed
                or snapshot.generation != fence[0]
                or snapshot.holder_digest != fence[1]
                or time.time_ns() // 1_000_000 > snapshot.expires_at_ms
            ):
                raise InvestigationExecutionBusy("execution generation is stale")
        yield


def default_events_dir() -> str:
    return os.environ.get(
        "ANTIEK_RESEARCH_EVENTS_DIR",
        os.path.join(
            os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")),
            "research_events",
        ),
    )


def _jsonl_path(investigation_id: str, *, events_dir: str | None = None) -> str:
    d = events_dir or default_events_dir()
    return os.path.join(d, f"{investigation_id}.jsonl")


def _parquet_path(investigation_id: str, *, events_dir: str | None = None) -> str:
    d = events_dir or default_events_dir()
    return os.path.join(d, f"{investigation_id}.parquet")


# NOTE: ``ActionType``, ``EVENT_SCHEMA_VERSION``, ``DEFAULT_POLICY_ID`` and the
# typed ``Event`` envelope live in ``substrate/schemas/events.py``. They are
# imported above and re-exported by ``substrate/event_log/__init__.py`` so
# legacy imports of the form ``from substrate.event_log import ActionType``
# keep working. Schemas is the bottom of the dependency stack; this module
# is purely operations (emit, seal, query).


# ---------------------------------------------------------------------------
# Low-level emit
# ---------------------------------------------------------------------------


def _safe(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Telemetry must never break a real synthesis."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # pragma: no cover — diagnostic only
        print(f"events emit failed (non-fatal): {e!r}", file=sys.stderr)
        return None


def _new_event_id() -> str:
    return f"evt-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}"


def _coerce(at: str | ActionType) -> str:
    return at.value if isinstance(at, ActionType) else at


def _events_disabled() -> bool:
    return os.environ.get("ANTIEK_EVENTS_DISABLED", "").lower() in ("1", "true", "yes")


def require_event_persistence() -> None:
    """Fail before a durable command commits when its audit store is disabled."""
    if _events_disabled():
        raise RuntimeError("typed event persistence is disabled")


@contextmanager
def _event_file_lock(path: str) -> Iterator[None]:
    """Serialize append and seal operations for one investigation stream."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(f"{path}.lock", "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _authorized_event_lock(stream: OpenedInvestigationStream) -> Iterator[None]:
    name = f"{stream.jsonl_name}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, 0o600, dir_fd=stream.directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("authorized event stream lock is unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def _authorized_execution_mutation_lock(
    stream: OpenedInvestigationStream,
) -> Iterator[None]:
    name = f"{stream.jsonl_name}.execution-mutation.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, 0o600, dir_fd=stream.directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("authorized execution mutation lock is unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _open_regular_at(
    stream: OpenedInvestigationStream, name: str, flags: int, mode: int = 0o600
) -> int:
    try:
        fd = os.open(
            name,
            flags | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=stream.directory_fd,
        )
    except OSError as exc:
        raise RuntimeError("authorized event stream file is unsafe") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise RuntimeError("authorized event stream file is unsafe")
    return fd


def _append_jsonl_authorized_unlocked(
    stream: OpenedInvestigationStream, row: dict[str, Any]
) -> None:
    fd = _open_regular_at(
        stream,
        stream.jsonl_name,
        os.O_RDWR | os.O_CREAT,
    )
    try:
        size = os.fstat(fd).st_size
        if size:
            os.lseek(fd, -1, os.SEEK_END)
            if os.read(fd, 1) != b"\n":
                position = size - 1
                while position > 0:
                    position -= 1
                    os.lseek(fd, position, os.SEEK_SET)
                    if os.read(fd, 1) == b"\n":
                        position += 1
                        break
                else:
                    position = 0
                os.ftruncate(fd, position)
        line = json.dumps(row, default=str, separators=(",", ":"))
        if "\n" in line:
            line = line.replace("\n", "\\n")
        os.lseek(fd, 0, os.SEEK_END)
        payload = (line + "\n").encode("utf-8")
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_jsonl_unlocked(path: str, row: dict[str, Any]) -> None:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r+b") as existing:
            existing.seek(-1, os.SEEK_END)
            if existing.read(1) != b"\n":
                position = existing.tell() - 1
                while position > 0:
                    position -= 1
                    existing.seek(position)
                    if existing.read(1) == b"\n":
                        position += 1
                        break
                else:
                    position = 0
                existing.truncate(position)
                existing.flush()
                os.fsync(existing.fileno())
    line = json.dumps(row, default=str, separators=(",", ":"))
    if "\n" in line:
        line = line.replace("\n", "\\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _append_jsonl(path: str, row: dict[str, Any]) -> None:
    """Append one fsynced JSON line while excluding concurrent sealing."""
    with _event_file_lock(path):
        _append_jsonl_unlocked(path, row)


@dataclass
class EventAppendBatch:
    """One investigation's exhaustively validated, exclusively locked batch."""

    investigation_id: str
    path: str
    events_dir: str | None
    _rows: list[dict[str, Any]]
    _load_error: str | None = None

    def validate(self, events: tuple[Event, ...]) -> None:
        if self._load_error is not None:
            raise ValueError(self._load_error)
        desired = {event.event_id: event.model_dump(mode="json") for event in events}
        if len(desired) != len(events):
            raise ValueError("event batch contains duplicate ids")
        if any(event.investigation_id != self.investigation_id for event in events):
            raise ValueError("event batch crosses investigation streams")
        stored_by_id: dict[str, dict[str, Any]] = {}
        for row in self._rows:
            stored_event = Event.model_validate(row)
            if stored_event.investigation_id != self.investigation_id:
                raise ValueError("stored event crosses investigation streams")
            event_id = stored_event.event_id
            stored = stored_event.model_dump(mode="json")
            prior = stored_by_id.get(event_id)
            if prior is not None and prior != stored:
                raise ValueError(f"event id collision: {event_id}")
            stored_by_id[event_id] = stored
            expected = desired.get(event_id)
            if expected is None:
                continue
            if stored != expected:
                raise ValueError(f"event id collision: {event_id}")

    def append(self, events: tuple[Event, ...]) -> None:
        self.validate(events)
        present = {str(row.get("event_id") or "") for row in self._rows}
        for event in events:
            if event.event_id in present:
                continue
            row = event.model_dump(mode="json")
            _append_jsonl_unlocked(self.path, row)
            self._rows.append(row)
            present.add(event.event_id)


@contextmanager
def event_append_batch(
    investigation_id: str, *, events_dir: str | None = None
) -> Iterator[EventAppendBatch]:
    """Hold the stream lock across deterministic preflight and batch append."""

    require_event_persistence()
    path = _jsonl_path(investigation_id, events_dir=events_dir)
    with _event_file_lock(path):
        load_error: str | None = None
        try:
            rows = _read_event_rows(
                investigation_id,
                events_dir=events_dir,
                reject_malformed=True,
            )
        except (TypeError, ValueError) as exc:
            rows = []
            load_error = str(exc)
        yield EventAppendBatch(
            investigation_id=investigation_id,
            path=path,
            events_dir=events_dir,
            _rows=rows,
            _load_error=load_error,
        )


def log_event(
    investigation_id: str,
    action_type: str | ActionType,
    *,
    payload: dict[str, Any] | None = None,
    parent_event_id: str | None = None,
    synthesis_id: str | None = None,
    phase: int | None = None,
    role: str | None = None,
    policy_id: str | None = None,
    document_id: str | None = None,
    events_dir: str | None = None,
) -> str | None:
    """Emit a single typed event into the investigation's JSONL trajectory.

    Returns event_id on success, None when events are disabled or on failure.
    Non-fatal: errors print to stderr.

    ``document_id`` is set on wrestling-loop events to anchor them to a
    specific source document. It is None for all Loop 1 events.
    """
    if _events_disabled():
        return None
    if authority := current_investigation_authority(investigation_id):
        return log_event_authorized(
            authority,
            action_type,
            payload=payload,
            parent_event_id=parent_event_id,
            synthesis_id=synthesis_id,
            phase=phase,
            role=role,
            policy_id=policy_id,
            document_id=document_id,
        )

    event_id = _new_event_id()
    row = {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "synthesis_id": synthesis_id,
        "phase": phase,
        "role": role,
        "action_type": _coerce(action_type),
        "payload": payload or {},
        "parent_event_id": parent_event_id,
        "policy_id": policy_id or DEFAULT_POLICY_ID,
        "param_version": ANTIEK_PARAM_VERSION,
        "schema_version": EVENT_SCHEMA_VERSION,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "document_id": document_id,
    }
    path = _jsonl_path(investigation_id, events_dir=events_dir)
    if _safe(_append_jsonl, path, row) is None:
        return event_id
    return event_id


# ---------------------------------------------------------------------------
# Typed emit — validated against substrate/schemas/events.py
#
# Use this path for any action_type whose payload model is defined in
# substrate/schemas/events.py (the 19 currently-schemaed variants).
# The legacy ``log_event`` path above still works for untyped action types
# (the Researchmaxx vocabulary that hasn't been schemaed yet — see
# architecture_notes §7 for the discipline that all variants get schemas
# over time).
# ---------------------------------------------------------------------------


def emit_typed(
    investigation_id: str,
    payload: Any,  # one of the TypedPayload variants — validated by Event below
    *,
    parent_event_id: str | None = None,
    synthesis_id: str | None = None,
    phase: int | None = None,
    role: str | None = None,
    policy_id: str | None = None,
    document_id: str | None = None,
    events_dir: str | None = None,
    execution_generation: int | None = None,
    event_id: str | None = None,
) -> str | None:
    """Emit a typed event. ``action_type`` is derived from the payload's
    discriminator; the Event envelope validates that the payload matches a
    known variant, that wrestling events carry ``document_id``, and that
    timestamps serialize as ISO 8601 with the ``Z`` suffix.

    Returns event_id on success, None when events are disabled.
    Non-fatal: validation errors are RE-RAISED (because a malformed event
    is a substrate bug, not telemetry noise), but write errors print to
    stderr and return the event_id so the caller's parent-stack stays
    consistent.
    """
    if _events_disabled():
        return None
    if authority := current_investigation_authority(investigation_id):
        return emit_typed_authorized(
            authority,
            payload,
            parent_event_id=parent_event_id,
            synthesis_id=synthesis_id,
            phase=phase,
            role=role,
            policy_id=policy_id,
            document_id=document_id,
            execution_generation=execution_generation,
            event_id=event_id,
        )

    event = prepare_typed_event(
        investigation_id,
        payload,
        parent_event_id=parent_event_id,
        synthesis_id=synthesis_id,
        phase=phase,
        role=role,
        policy_id=policy_id,
        document_id=document_id,
        execution_generation=execution_generation,
        event_id=event_id,
    )

    row = event.model_dump(mode="json")
    path = _jsonl_path(investigation_id, events_dir=events_dir)
    _safe(_append_jsonl, path, row)
    return event.event_id


def _require_new_paid_start_authority(payload: Any) -> None:
    """Reject newly written paid starts that lack a complete quote receipt.

    Historical rows remain readable because validation happens only at the
    write boundary, not while reconstructing an older Event.
    """
    if not isinstance(payload, InvestigationStartRequestedPayload):
        return
    if payload.approved_run_ceiling_usd is None:
        return
    if not all(
        (
            payload.research_quote_id,
            payload.research_quote_payload_sha256,
            payload.research_route_manifest_fingerprint,
            payload.research_quote_expires_at_ms,
            payload.research_route_manifest,
        )
    ):
        raise ValueError("positive-ceiling research start requires quote authority")


def prepare_typed_event(
    investigation_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    parent_event_id: str | None = None,
    synthesis_id: str | None = None,
    phase: int | None = None,
    role: str | None = None,
    policy_id: str | None = None,
    document_id: str | None = None,
    emitted_at: datetime | None = None,
    execution_generation: int | None = None,
) -> Event:
    """Validate an exact typed envelope without writing it.

    Durable command paths prepare the envelope inside their database
    transaction, then append that same object after commit. This preserves the
    original timestamp and payload across transport retries.
    """
    _require_new_paid_start_authority(payload)
    return Event(
        event_id=event_id or _new_event_id(),
        investigation_id=investigation_id,
        synthesis_id=synthesis_id,
        phase=phase,
        role=role,
        action_type=payload.action_type,
        payload=payload,
        parent_event_id=parent_event_id,
        policy_id=policy_id or DEFAULT_POLICY_ID,
        param_version=ANTIEK_PARAM_VERSION,
        schema_version=EVENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(UTC),
        document_id=document_id,
        execution_generation=execution_generation,
    )


def append_event_once(event: Event, *, events_dir: str | None = None) -> str:
    """Strictly append a prepared event unless its stable id already exists.

    Unlike ordinary telemetry emission, storage failures propagate so a caller
    can retry from its durable command receipt. An existing event id must carry
    the same envelope; treating a collision as success would corrupt the audit
    trail.
    """
    require_event_persistence()
    _require_new_paid_start_authority(event.payload)
    desired = event.model_dump(mode="json")
    path = _jsonl_path(event.investigation_id, events_dir=events_dir)
    with _event_file_lock(path):
        found = False
        for row in _read_event_rows(event.investigation_id, events_dir=events_dir):
            if row.get("event_id") != event.event_id:
                continue
            found = True
            stored = Event.model_validate(row).model_dump(mode="json")
            if stored != desired:
                raise ValueError(f"event id collision: {event.event_id}")
        if found:
            return event.event_id
        _append_jsonl_unlocked(path, desired)
    return event.event_id


def _validate_authorized_rows(
    authority: InvestigationAuthority, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    for row in rows:
        if row.get("investigation_id") != authority.investigation_id:
            raise ValueError("stored event crosses authorized investigation stream")
    return rows


def _read_opened_event_rows(
    stream: OpenedInvestigationStream, *, reject_malformed: bool
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        parquet_fd = _open_regular_at(stream, stream.parquet_name, os.O_RDONLY)
    except RuntimeError as exc:
        try:
            os.stat(
                stream.parquet_name,
                dir_fd=stream.directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            parquet_fd = None
        else:
            raise exc
    if parquet_fd is not None:
        try:
            try:
                import pyarrow.parquet as pq_reader
            except ImportError:
                if reject_malformed:
                    raise ValueError(
                        "sealed event stream cannot be validated without pyarrow"
                    ) from None
            else:
                with os.fdopen(os.dup(parquet_fd), "rb") as handle:
                    rows.extend(pq_reader.read_table(handle).to_pylist())
        finally:
            os.close(parquet_fd)
    try:
        jsonl_fd = _open_regular_at(stream, stream.jsonl_name, os.O_RDONLY)
    except RuntimeError as exc:
        try:
            os.stat(
                stream.jsonl_name,
                dir_fd=stream.directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            jsonl_fd = None
        else:
            raise exc
    if jsonl_fd is not None:
        try:
            with os.fdopen(os.dup(jsonl_fd), encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        if reject_malformed:
                            raise ValueError(
                                "event stream contains malformed JSON"
                            ) from exc
        finally:
            os.close(jsonl_fd)
    for row in rows:
        if isinstance(row.get("payload"), str):
            with contextlib.suppress(TypeError, ValueError):
                row["payload"] = json.loads(row["payload"])
    return rows


def append_event_once_authorized(authority: InvestigationAuthority, event: Event) -> str:
    """Strict append through account-scoped stream authority."""
    require_event_persistence()
    _require_new_paid_start_authority(event.payload)
    if event.investigation_id != authority.investigation_id:
        raise ValueError("event crosses authorized investigation stream")
    desired = event.model_dump(mode="json")
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority,
            _read_opened_event_rows(stream, reject_malformed=True),
        )
        fence = current_investigation_execution(authority.investigation_id)
        if fence is not None:
            snapshot, _ = _investigation_execution_ledger(authority, rows)
            if (
                snapshot is None
                or snapshot.completed
                or snapshot.generation != fence[0]
                or snapshot.holder_digest != fence[1]
                or time.time_ns() // 1_000_000 > snapshot.expires_at_ms
            ):
                raise InvestigationExecutionBusy("execution generation is stale")
        found = False
        for row in rows:
            if row.get("event_id") != event.event_id:
                continue
            found = True
            if Event.model_validate(row).model_dump(mode="json") != desired:
                raise ValueError(f"event id collision: {event.event_id}")
        if not found:
            _append_jsonl_authorized_unlocked(stream, desired)
    return event.event_id


class IdempotencyConflict(ValueError):
    """A mutation key was already committed with a different request."""


class ResearchBudgetLedgerInvalid(ValueError):
    """The durable research-call money ledger is ambiguous or inconsistent."""


class ResearchBudgetExceeded(ValueError):
    """A new provider-call hold would exceed explicit launch authority."""


class InvestigationExecutionBusy(ValueError):
    """Another non-expired holder owns the investigation execution lease."""


class InvestigationExecutionInvalid(ValueError):
    """The durable execution lease history is ambiguous or inconsistent."""


@dataclass(frozen=True)
class InvestigationExecutionSnapshot:
    execution_id: str
    start_event_id: str
    generation: int
    holder_digest: str
    expires_at_ms: int
    lease_event_id: str
    completed_event_id: str | None = None
    terminal_event_id: str | None = None

    @property
    def completed(self) -> bool:
        return self.completed_event_id is not None


def investigation_execution_id(authority: InvestigationAuthority, start: Event) -> str:
    quote_id = getattr(start.payload, "research_quote_id", None)
    body = json.dumps(
        {
            "account_digest": authority.account_digest,
            "investigation_id": authority.investigation_id,
            "start_event_id": start.event_id,
            "research_quote_id": quote_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"antiek.investigation-execution.v1\x00" + body).hexdigest()


def _event_sha256(event: Event) -> str:
    encoded = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _investigation_execution_ledger(
    authority: InvestigationAuthority, rows: list[dict[str, Any]]
) -> tuple[InvestigationExecutionSnapshot | None, Event]:
    events = [Event.model_validate(row) for row in rows]
    starts = [
        event
        for event in events
        if event.action_type == ActionType.INVESTIGATION_START_REQUESTED
    ]
    if len(starts) != 1:
        raise InvestigationExecutionInvalid(
            "execution lease requires exactly one investigation start"
        )
    start = starts[0]
    if getattr(start.payload, "approved_run_ceiling_usd", None) is None:
        raise InvestigationExecutionInvalid("execution lease requires a paid start")
    expected_execution_id = investigation_execution_id(authority, start)
    receipts = [
        event
        for event in events
        if event.action_type
        in {
            ActionType.INVESTIGATION_EXECUTION_CLAIMED,
            ActionType.INVESTIGATION_EXECUTION_RENEWED,
            ActionType.INVESTIGATION_EXECUTION_TAKEN_OVER,
            ActionType.INVESTIGATION_EXECUTION_COMPLETED,
        }
    ]
    if not receipts:
        return None, start
    current_event: Event | None = None
    current_payload: InvestigationExecutionClaimedPayload | InvestigationExecutionRenewedPayload | InvestigationExecutionTakenOverPayload | None = None
    completion_event: Event | None = None
    terminal_id: str | None = None
    event_positions = {event.event_id: index for index, event in enumerate(events)}
    if len(event_positions) != len(events):
        raise InvestigationExecutionInvalid("execution history has duplicate event ids")
    for receipt in receipts:
        payload = receipt.payload
        if getattr(payload, "execution_id", None) != expected_execution_id:
            raise InvestigationExecutionInvalid("execution receipt identity conflicts")
        if isinstance(payload, InvestigationExecutionClaimedPayload):
            if current_event is not None or payload.start_event_id != start.event_id:
                raise InvestigationExecutionInvalid("execution has multiple initial claims")
            if payload.expires_at_ms <= payload.claimed_at_ms:
                raise InvestigationExecutionInvalid("execution claim lifetime is invalid")
            current_event, current_payload = receipt, payload
        elif isinstance(payload, InvestigationExecutionRenewedPayload):
            if current_event is None or current_payload is None:
                raise InvestigationExecutionInvalid("execution renewal has no lease")
            if (
                completion_event is not None
                or payload.prior_receipt_event_id != current_event.event_id
                or payload.generation != current_payload.generation
                or payload.holder_digest != current_payload.holder_digest
                or payload.expires_at_ms <= payload.renewed_at_ms
            ):
                raise InvestigationExecutionInvalid("execution renewal conflicts")
            current_event, current_payload = receipt, payload
        elif isinstance(payload, InvestigationExecutionTakenOverPayload):
            if current_event is None or current_payload is None:
                raise InvestigationExecutionInvalid("execution takeover has no lease")
            if (
                completion_event is not None
                or payload.prior_receipt_event_id != current_event.event_id
                or payload.prior_generation != current_payload.generation
                or payload.generation != current_payload.generation + 1
                or payload.prior_holder_digest != current_payload.holder_digest
                or payload.prior_expires_at_ms != current_payload.expires_at_ms
                or payload.taken_over_at_ms
                < payload.prior_expires_at_ms + payload.clock_skew_margin_ms
                or payload.expires_at_ms <= payload.taken_over_at_ms
            ):
                raise InvestigationExecutionInvalid("execution takeover conflicts")
            current_event, current_payload = receipt, payload
        elif isinstance(payload, InvestigationExecutionCompletedPayload):
            if current_event is None or current_payload is None:
                raise InvestigationExecutionInvalid("execution completion has no lease")
            terminals = [
                event
                for event in events
                if event.event_id == payload.terminal_event_id
                and event.action_type
                in {ActionType.INVESTIGATION_COMPLETED, ActionType.INVESTIGATION_FAILED}
            ]
            if (
                completion_event is not None
                or payload.lease_receipt_event_id != current_event.event_id
                or payload.generation != current_payload.generation
                or payload.holder_digest != current_payload.holder_digest
                or len(terminals) != 1
                or _event_sha256(terminals[0]) != payload.terminal_sha256
                or terminals[0].execution_generation != current_payload.generation
                or event_positions[terminals[0].event_id]
                >= event_positions[receipt.event_id]
            ):
                raise InvestigationExecutionInvalid("execution completion conflicts")
            completion_event = receipt
            terminal_id = terminals[0].event_id
    if current_event is None or current_payload is None:
        raise InvestigationExecutionInvalid("execution lease is missing")
    return (
        InvestigationExecutionSnapshot(
            execution_id=expected_execution_id,
            start_event_id=start.event_id,
            generation=current_payload.generation,
            holder_digest=current_payload.holder_digest,
            expires_at_ms=current_payload.expires_at_ms,
            lease_event_id=current_event.event_id,
            completed_event_id=(completion_event.event_id if completion_event else None),
            terminal_event_id=terminal_id,
        ),
        start,
    )


def claim_investigation_execution_authorized(
    authority: InvestigationAuthority,
    *,
    holder_digest: str,
    now_ms: int,
    ttl_ms: int = 60_000,
    clock_skew_margin_ms: int = 5_000,
) -> tuple[Event | None, InvestigationExecutionSnapshot, bool]:
    if (
        len(holder_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in holder_digest)
        or type(now_ms) is not int
        or type(ttl_ms) is not int
        or not 5_000 <= ttl_ms <= 300_000
        or type(clock_skew_margin_ms) is not int
        or not 0 <= clock_skew_margin_ms <= 60_000
    ):
        raise ValueError("execution lease request is invalid")
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_execution_mutation_lock(stream),
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        snapshot, start = _investigation_execution_ledger(authority, rows)
        if snapshot is not None and snapshot.completed:
            return None, snapshot, False
        if snapshot is not None:
            unsealed_terminals = [
                Event.model_validate(row)
                for row in rows
                if row.get("action_type")
                in {
                    ActionType.INVESTIGATION_COMPLETED.value,
                    ActionType.INVESTIGATION_FAILED.value,
                }
                and row.get("execution_generation") == snapshot.generation
            ]
            if len(unsealed_terminals) > 1:
                raise InvestigationExecutionInvalid(
                    "execution has multiple unsealed terminal events"
                )
            if unsealed_terminals:
                terminal = unsealed_terminals[0]
                completion = prepare_typed_event(
                    authority.investigation_id,
                    InvestigationExecutionCompletedPayload(
                        execution_id=snapshot.execution_id,
                        lease_receipt_event_id=snapshot.lease_event_id,
                        generation=snapshot.generation,
                        holder_digest=snapshot.holder_digest,
                        terminal_event_id=terminal.event_id,
                        terminal_sha256=_event_sha256(terminal),
                        completed_at_ms=now_ms,
                    ),
                    parent_event_id=terminal.event_id,
                    role="orchestrator",
                    policy_id="orchestrator-execution-lease",
                    execution_generation=snapshot.generation,
                )
                completed_snapshot, _ = _investigation_execution_ledger(
                    authority, [*rows, completion.model_dump(mode="json")]
                )
                assert completed_snapshot is not None
                _append_jsonl_authorized_unlocked(
                    stream, completion.model_dump(mode="json")
                )
                return None, completed_snapshot, False
        if snapshot is None:
            payload: InvestigationExecutionClaimedPayload | InvestigationExecutionTakenOverPayload = InvestigationExecutionClaimedPayload(
                execution_id=investigation_execution_id(authority, start),
                start_event_id=start.event_id,
                holder_digest=holder_digest,
                claimed_at_ms=now_ms,
                expires_at_ms=now_ms + ttl_ms,
            )
            parent_id = start.event_id
        elif snapshot.holder_digest == holder_digest and now_ms <= snapshot.expires_at_ms:
            current = next(
                Event.model_validate(row)
                for row in rows
                if row.get("event_id") == snapshot.lease_event_id
            )
            return current, snapshot, True
        elif now_ms < snapshot.expires_at_ms + clock_skew_margin_ms:
            raise InvestigationExecutionBusy("investigation execution lease is active")
        else:
            payload = InvestigationExecutionTakenOverPayload(
                execution_id=snapshot.execution_id,
                prior_receipt_event_id=snapshot.lease_event_id,
                prior_generation=snapshot.generation,
                generation=snapshot.generation + 1,
                prior_holder_digest=snapshot.holder_digest,
                holder_digest=holder_digest,
                prior_expires_at_ms=snapshot.expires_at_ms,
                clock_skew_margin_ms=clock_skew_margin_ms,
                taken_over_at_ms=now_ms,
                expires_at_ms=now_ms + ttl_ms,
            )
            parent_id = snapshot.lease_event_id
        event = prepare_typed_event(
            authority.investigation_id,
            payload,
            parent_event_id=parent_id,
            role="orchestrator",
            policy_id="orchestrator-execution-lease",
            execution_generation=payload.generation,
        )
        candidate_snapshot, _ = _investigation_execution_ledger(
            authority, [*rows, event.model_dump(mode="json")]
        )
        assert candidate_snapshot is not None
        _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
        return event, candidate_snapshot, True


def renew_investigation_execution_authorized(
    authority: InvestigationAuthority,
    *,
    generation: int,
    holder_digest: str,
    now_ms: int,
    ttl_ms: int = 60_000,
) -> tuple[Event, InvestigationExecutionSnapshot]:
    if type(now_ms) is not int or type(ttl_ms) is not int or not 5_000 <= ttl_ms <= 300_000:
        raise ValueError("execution renewal request is invalid")
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        snapshot, _ = _investigation_execution_ledger(authority, rows)
        if (
            snapshot is None
            or snapshot.completed
            or snapshot.generation != generation
            or snapshot.holder_digest != holder_digest
            or now_ms > snapshot.expires_at_ms
        ):
            raise InvestigationExecutionBusy("execution lease cannot be renewed")
        payload = InvestigationExecutionRenewedPayload(
            execution_id=snapshot.execution_id,
            prior_receipt_event_id=snapshot.lease_event_id,
            generation=generation,
            holder_digest=holder_digest,
            renewed_at_ms=now_ms,
            expires_at_ms=now_ms + ttl_ms,
        )
        event = prepare_typed_event(
            authority.investigation_id,
            payload,
            parent_event_id=snapshot.lease_event_id,
            role="orchestrator",
            policy_id="orchestrator-execution-lease",
            execution_generation=generation,
        )
        candidate, _ = _investigation_execution_ledger(
            authority, [*rows, event.model_dump(mode="json")]
        )
        assert candidate is not None
        _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
        return event, candidate


def assert_investigation_execution_authorized(
    authority: InvestigationAuthority,
    *,
    generation: int,
    holder_digest: str,
    now_ms: int,
) -> InvestigationExecutionSnapshot:
    with (
        open_investigation_stream(authority, writable=False) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        snapshot, _ = _investigation_execution_ledger(authority, rows)
    if (
        snapshot is None
        or snapshot.completed
        or snapshot.generation != generation
        or snapshot.holder_digest != holder_digest
        or now_ms > snapshot.expires_at_ms
    ):
        raise InvestigationExecutionBusy("execution generation is stale")
    return snapshot


def complete_investigation_execution_authorized(
    authority: InvestigationAuthority,
    *,
    generation: int,
    holder_digest: str,
    terminal_event: Event,
    completed_at_ms: int,
) -> tuple[Event, InvestigationExecutionSnapshot]:
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        snapshot, _ = _investigation_execution_ledger(authority, rows)
        if snapshot is None:
            raise InvestigationExecutionInvalid("execution lease is missing")
        if snapshot.completed:
            completion = next(
                Event.model_validate(row)
                for row in rows
                if row.get("event_id") == snapshot.completed_event_id
            )
            stored_terminal = next(
                Event.model_validate(row)
                for row in rows
                if row.get("event_id") == snapshot.terminal_event_id
            )
            if (
                snapshot.generation != generation
                or snapshot.holder_digest != holder_digest
                or stored_terminal.model_dump(mode="json")
                != terminal_event.model_dump(mode="json")
            ):
                raise IdempotencyConflict("execution completed with another terminal")
            return completion, snapshot
        stored = [
            Event.model_validate(row)
            for row in rows
            if row.get("event_id") == terminal_event.event_id
        ]
        if (
            snapshot.generation != generation
            or snapshot.holder_digest != holder_digest
            or len(stored) != 1
            or stored[0].model_dump(mode="json")
            != terminal_event.model_dump(mode="json")
            or terminal_event.execution_generation != generation
        ):
            raise InvestigationExecutionInvalid("execution terminal is not authorized")
        payload = InvestigationExecutionCompletedPayload(
            execution_id=snapshot.execution_id,
            lease_receipt_event_id=snapshot.lease_event_id,
            generation=generation,
            holder_digest=holder_digest,
            terminal_event_id=terminal_event.event_id,
            terminal_sha256=_event_sha256(terminal_event),
            completed_at_ms=completed_at_ms,
        )
        event = prepare_typed_event(
            authority.investigation_id,
            payload,
            parent_event_id=terminal_event.event_id,
            role="orchestrator",
            policy_id="orchestrator-execution-lease",
            execution_generation=generation,
        )
        candidate, _ = _investigation_execution_ledger(
            authority, [*rows, event.model_dump(mode="json")]
        )
        assert candidate is not None
        _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
        return event, candidate


@dataclass(frozen=True)
class ResearchBudgetSnapshot:
    ceiling_usd: Decimal
    settled_usd: Decimal
    outstanding_usd: Decimal

    @property
    def remaining_usd(self) -> Decimal:
        return self.ceiling_usd - self.settled_usd - self.outstanding_usd


@dataclass(frozen=True)
class _ResearchBudgetLedger:
    snapshot: ResearchBudgetSnapshot
    reservations: dict[str, tuple[Event, ResearchCallReservedPayload]]
    terminals: dict[
        str, tuple[Event, ResearchCallSettledPayload | ResearchCallReleasedPayload]
    ]


def _money(value: float) -> Decimal:
    return Decimal(str(value))


def research_call_dispatch_event_id(reservation_event_id: str) -> str:
    """Return the one canonical dispatch receipt ID for a reserved call."""
    suffix = hashlib.sha256(reservation_event_id.encode("utf-8")).hexdigest()[:24]
    return f"evt-research-dispatch-{suffix}"


def _dispatch_matches_reservation(
    dispatch_event: Event,
    reservation_event: Event,
    reservation: ResearchCallReservedPayload,
) -> bool:
    dispatch_payload = dispatch_event.payload
    return dispatch_event.action_type == ActionType.DISPATCH_CALL and all(
        (
            dispatch_event.event_id
            == research_call_dispatch_event_id(reservation_event.event_id),
            getattr(dispatch_payload, "provider", None) == reservation.provider,
            getattr(dispatch_payload, "model", None) == reservation.model,
            getattr(dispatch_payload, "tier", None) == reservation.tier,
            getattr(dispatch_payload, "target_role", None) == reservation.target_role,
            getattr(dispatch_payload, "verification_required", None)
            == reservation.verification_required,
            getattr(dispatch_payload, "fallback_chain_index", None)
            == reservation.fallback_chain_index,
            getattr(dispatch_payload, "prompt_hash", None) == reservation.prompt_hash,
            getattr(dispatch_payload, "context_pack_event_id", None)
            == reservation.context_pack_event_id,
            dispatch_event.parent_event_id == reservation.parent_request_event_id,
        )
    )


def _validate_research_budget_envelope(
    reservation: ResearchCallReservedPayload, *, role: str, policy_id: str
) -> None:
    if role != reservation.target_role or policy_id != (
        f"{reservation.provider}/{reservation.model}"
    ):
        raise ResearchBudgetLedgerInvalid(
            "budget event envelope conflicts with reserved route"
        )


def _validate_reservation_quote_route(
    start_payload: Any, reservation: ResearchCallReservedPayload
) -> None:
    quote_id = getattr(start_payload, "research_quote_id", None)
    manifest_fingerprint = getattr(
        start_payload, "research_route_manifest_fingerprint", None
    )
    manifest = getattr(start_payload, "research_route_manifest", None)
    if not quote_id or not manifest_fingerprint or not manifest:
        raise ResearchBudgetLedgerInvalid(
            "investigation has no accepted research quote manifest"
        )
    accepted_routes = {(row.role, row.fallback_index): row for row in manifest}
    if len(accepted_routes) != len(manifest):
        raise ResearchBudgetLedgerInvalid("research quote manifest routes are ambiguous")
    selected_role = getattr(start_payload, "selected_driver_role", None)
    if selected_role == reservation.target_role:
        selected = [
            row
            for row in manifest
            if row.role == selected_role
            and row.provider == getattr(
                start_payload, "selected_driver_provider", None
            )
            and row.model == getattr(start_payload, "selected_driver_model", None)
            and row.pricing_fingerprint
            == getattr(start_payload, "selected_driver_pricing_fingerprint", None)
        ]
        accepted = selected[0] if len(selected) == 1 else None
        selected_index_valid = reservation.fallback_chain_index == 0
    else:
        accepted = accepted_routes.get(
            (reservation.target_role, reservation.fallback_chain_index)
        )
        selected_index_valid = True
    if (
        accepted is None
        or not selected_index_valid
        or reservation.research_quote_id != quote_id
        or reservation.research_route_manifest_fingerprint != manifest_fingerprint
        or reservation.provider != accepted.provider
        or reservation.model != accepted.model
        or reservation.tier != accepted.logical_tier_name
        or reservation.route_tier_name != accepted.route_tier_name
        or reservation.max_tokens > accepted.max_output_tokens
        or reservation.temperature != accepted.temperature
        or reservation.context_budget_tokens != accepted.context_budget_tokens
        or reservation.pricing_fingerprint != accepted.pricing_fingerprint
    ):
        raise ResearchBudgetLedgerInvalid(
            "reservation conflicts with accepted research quote route"
        )


def _research_budget_ledger(
    authority: InvestigationAuthority, rows: list[dict[str, Any]]
) -> _ResearchBudgetLedger:
    """Parse one already-locked stream and fail closed on every ambiguity."""
    starts = [
        Event.model_validate(row)
        for row in rows
        if row.get("action_type") == ActionType.INVESTIGATION_START_REQUESTED.value
    ]
    if len(starts) != 1:
        raise ResearchBudgetLedgerInvalid(
            "research budget requires exactly one investigation start"
        )
    start_payload = starts[0].payload
    ceiling = getattr(start_payload, "approved_run_ceiling_usd", None)
    if ceiling is None or _money(ceiling) <= 0:
        raise ResearchBudgetLedgerInvalid(
            "investigation has no explicit initial-run ceiling"
        )
    manifest = getattr(start_payload, "research_route_manifest", None)
    if not manifest:
        raise ResearchBudgetLedgerInvalid(
            "investigation has no accepted research quote manifest"
        )

    reservations: dict[str, tuple[Event, ResearchCallReservedPayload]] = {}
    requests: dict[str, str] = {}
    terminals: dict[
        str, tuple[Event, ResearchCallSettledPayload | ResearchCallReleasedPayload]
    ] = {}
    events_by_id: dict[str, list[Event]] = {}
    event_positions: dict[str, list[int]] = {}
    for position, row in enumerate(rows):
        event = Event.model_validate(row)
        events_by_id.setdefault(event.event_id, []).append(event)
        event_positions.setdefault(event.event_id, []).append(position)
        if event.action_type == ActionType.RESEARCH_CALL_RESERVED:
            payload = event.payload
            if not isinstance(payload, ResearchCallReservedPayload):
                raise ResearchBudgetLedgerInvalid("reservation payload is not typed")
            _validate_reservation_quote_route(start_payload, payload)
            if payload.reservation_id in reservations:
                raise ResearchBudgetLedgerInvalid("duplicate research reservation id")
            prior_id = requests.get(payload.request_sha256)
            if prior_id is not None and prior_id != payload.reservation_id:
                raise ResearchBudgetLedgerInvalid("request has multiple reservations")
            reservations[payload.reservation_id] = (event, payload)
            requests[payload.request_sha256] = payload.reservation_id
        elif event.action_type in {
            ActionType.RESEARCH_CALL_SETTLED,
            ActionType.RESEARCH_CALL_RELEASED,
        }:
            payload = event.payload
            if not isinstance(
                payload, (ResearchCallSettledPayload, ResearchCallReleasedPayload)
            ):
                raise ResearchBudgetLedgerInvalid("terminal payload is not typed")
            if payload.reservation_id in terminals:
                raise ResearchBudgetLedgerInvalid("reservation has multiple terminals")
            terminals[payload.reservation_id] = (event, payload)

    settled = Decimal("0")
    outstanding = Decimal("0")
    consumed_dispatches: dict[str, str] = {}
    for reservation_id, (reservation_event, reservation) in reservations.items():
        terminal_entry = terminals.get(reservation_id)
        if terminal_entry is None:
            outstanding += _money(reservation.projected_max_cost_usd)
            continue
        terminal_event, terminal = terminal_entry
        if (
            terminal.reservation_event_id != reservation_event.event_id
            or terminal.request_sha256 != reservation.request_sha256
        ):
            raise ResearchBudgetLedgerInvalid("terminal does not bind its reservation")
        if isinstance(terminal, ResearchCallReleasedPayload):
            reservation_positions = event_positions.get(
                reservation_event.event_id, []
            )
            if len(reservation_positions) != 1 or any(
                _dispatch_matches_reservation(
                    Event.model_validate(row), reservation_event, reservation
                )
                for position, row in enumerate(rows)
                if position > reservation_positions[0]
            ):
                raise ResearchBudgetLedgerInvalid(
                    "released reservation has a post-reservation dispatch"
                )
            continue
        dispatches = events_by_id.get(terminal.dispatch_call_event_id, [])
        if len(dispatches) != 1:
            raise ResearchBudgetLedgerInvalid("settlement dispatch receipt is missing")
        dispatch_event = dispatches[0]
        dispatch_payload = dispatch_event.payload
        if dispatch_event.action_type != ActionType.DISPATCH_CALL:
            raise ResearchBudgetLedgerInvalid("settlement references a non-dispatch event")
        reservation_positions = event_positions.get(reservation_event.event_id, [])
        dispatch_positions = event_positions.get(dispatch_event.event_id, [])
        terminal_positions = event_positions.get(terminal_event.event_id, [])
        if (
            len(reservation_positions) != 1
            or len(dispatch_positions) != 1
            or len(terminal_positions) != 1
            or not reservation_positions[0]
            < dispatch_positions[0]
            < terminal_positions[0]
        ):
            raise ResearchBudgetLedgerInvalid(
                "settlement must follow a post-reservation dispatch"
            )
        dispatch_cost = getattr(dispatch_payload, "cost_usd", None)
        if dispatch_cost is None or _money(dispatch_cost) != _money(
            terminal.actual_cost_usd
        ):
            raise ResearchBudgetLedgerInvalid("settlement cost disagrees with dispatch")
        if not _dispatch_matches_reservation(
            dispatch_event, reservation_event, reservation
        ):
            raise ResearchBudgetLedgerInvalid("settlement dispatch bindings conflict")
        prior_reservation = consumed_dispatches.get(dispatch_event.event_id)
        if prior_reservation is not None and prior_reservation != reservation_id:
            raise ResearchBudgetLedgerInvalid(
                "dispatch receipt settles multiple reservations"
            )
        consumed_dispatches[dispatch_event.event_id] = reservation_id
        exceeded = _money(terminal.actual_cost_usd) > _money(
            reservation.projected_max_cost_usd
        )
        if terminal.exceeded_reservation is not exceeded:
            raise ResearchBudgetLedgerInvalid("settlement overrun flag is false")
        settled += _money(terminal.actual_cost_usd)

    unknown_terminals = set(terminals).difference(reservations)
    if unknown_terminals:
        raise ResearchBudgetLedgerInvalid("terminal references unknown reservation")
    snapshot = ResearchBudgetSnapshot(
        ceiling_usd=_money(ceiling),
        settled_usd=settled,
        outstanding_usd=outstanding,
    )
    return _ResearchBudgetLedger(snapshot, reservations, terminals)


def _append_research_budget_event_unlocked(
    authority: InvestigationAuthority,
    stream: OpenedInvestigationStream,
    payload: ResearchCallReservedPayload
    | ResearchCallSettledPayload
    | ResearchCallReleasedPayload,
    *,
    role: str,
    policy_id: str,
    parent_event_id: str | None = None,
    execution_generation: int | None = None,
) -> Event:
    event = prepare_typed_event(
        authority.investigation_id,
        payload,
        parent_event_id=parent_event_id,
        role=role,
        policy_id=policy_id,
        execution_generation=execution_generation,
    )
    _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
    return event


def _fenced_execution_generation_for_rows(
    authority: InvestigationAuthority,
    rows: list[dict[str, Any]],
    *,
    operation: str,
) -> int | None:
    fence = current_investigation_execution(authority.investigation_id)
    if fence is None:
        return None
    generation, holder_digest = fence
    snapshot, _ = _investigation_execution_ledger(authority, rows)
    now_ms = time.time_ns() // 1_000_000
    if (
        snapshot is None
        or snapshot.completed
        or snapshot.generation != generation
        or snapshot.holder_digest != holder_digest
        or now_ms > snapshot.expires_at_ms
    ):
        raise InvestigationExecutionBusy(f"stale execution cannot {operation}")
    return generation


def reserve_research_call_authorized(
    authority: InvestigationAuthority,
    payload: ResearchCallReservedPayload,
    *,
    role: str,
    policy_id: str,
) -> tuple[Event, ResearchBudgetSnapshot]:
    """Atomically replay or reserve provider-call capacity before network I/O."""
    require_event_persistence()
    _validate_research_budget_envelope(payload, role=role, policy_id=policy_id)
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        execution_generation = _fenced_execution_generation_for_rows(
            authority, rows, operation="reserve provider spend"
        )
        ledger = _research_budget_ledger(authority, rows)
        start_rows = [
            Event.model_validate(row)
            for row in rows
            if row.get("action_type")
            == ActionType.INVESTIGATION_START_REQUESTED.value
        ]
        _validate_reservation_quote_route(start_rows[0].payload, payload)
        existing = ledger.reservations.get(payload.reservation_id)
        if existing is not None:
            event, stored = existing
            if (
                stored.model_dump(mode="json") != payload.model_dump(mode="json")
                or event.role != role
                or event.policy_id != policy_id
                or event.parent_event_id != payload.parent_request_event_id
            ):
                raise IdempotencyConflict(
                    "research reservation id was used for another request"
                )
            return event, ledger.snapshot
        if payload.request_sha256 in {
            item.request_sha256 for _, item in ledger.reservations.values()
        }:
            raise IdempotencyConflict("research request already has a reservation")
        projected = _money(payload.projected_max_cost_usd)
        if projected > ledger.snapshot.remaining_usd:
            raise ResearchBudgetExceeded("research call exceeds approved run ceiling")
        if payload.parent_request_event_id is not None and not any(
            row.get("event_id") == payload.parent_request_event_id for row in rows
        ):
            raise ResearchBudgetLedgerInvalid("parent request event is missing")
        event = _append_research_budget_event_unlocked(
            authority,
            stream,
            payload,
            role=role,
            policy_id=policy_id,
            parent_event_id=payload.parent_request_event_id,
            execution_generation=execution_generation,
        )
        snapshot = ResearchBudgetSnapshot(
            ceiling_usd=ledger.snapshot.ceiling_usd,
            settled_usd=ledger.snapshot.settled_usd,
            outstanding_usd=ledger.snapshot.outstanding_usd + projected,
        )
        return event, snapshot


def settle_research_call_authorized(
    authority: InvestigationAuthority,
    payload: ResearchCallSettledPayload,
    *,
    role: str,
    policy_id: str,
) -> tuple[Event, ResearchBudgetSnapshot]:
    """Atomically bind normalized DispatchCall truth to one capacity hold."""
    require_event_persistence()
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        ledger = _research_budget_ledger(authority, rows)
        reservation_entry = ledger.reservations.get(payload.reservation_id)
        if reservation_entry is None:
            raise ResearchBudgetLedgerInvalid("settlement reservation is missing")
        reservation_event, reservation = reservation_entry
        _validate_research_budget_envelope(
            reservation, role=role, policy_id=policy_id
        )
        expected_overrun = _money(payload.actual_cost_usd) > _money(
            reservation.projected_max_cost_usd
        )
        if (
            payload.reservation_event_id != reservation_event.event_id
            or payload.request_sha256 != reservation.request_sha256
            or payload.exceeded_reservation is not expected_overrun
        ):
            raise ResearchBudgetLedgerInvalid("settlement conflicts with reservation")
        existing = ledger.terminals.get(payload.reservation_id)
        if existing is not None:
            event, stored = existing
            if not isinstance(stored, ResearchCallSettledPayload) or (
                stored.model_dump(mode="json") != payload.model_dump(mode="json")
            ) or event.role != role or event.policy_id != policy_id or (
                event.parent_event_id != reservation_event.event_id
            ):
                raise IdempotencyConflict("reservation already has another terminal")
            return event, ledger.snapshot
        execution_generation = _fenced_execution_generation_for_rows(
            authority, rows, operation="settle provider spend"
        )
        # Validate the candidate terminal using the same canonical parser that
        # all later operations use before making it durable.
        candidate = prepare_typed_event(
            authority.investigation_id,
            payload,
            role=role,
            policy_id=policy_id,
            parent_event_id=reservation_event.event_id,
            execution_generation=execution_generation,
        )
        candidate_ledger = _research_budget_ledger(
            authority, [*rows, candidate.model_dump(mode="json")]
        )
        _append_jsonl_authorized_unlocked(stream, candidate.model_dump(mode="json"))
        return candidate, candidate_ledger.snapshot


def release_research_call_authorized(
    authority: InvestigationAuthority,
    payload: ResearchCallReleasedPayload,
    *,
    role: str,
    policy_id: str,
) -> tuple[Event, ResearchBudgetSnapshot]:
    """Atomically release only an explicitly classified no-call hold."""
    require_event_persistence()
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        ledger = _research_budget_ledger(authority, rows)
        reservation_entry = ledger.reservations.get(payload.reservation_id)
        if reservation_entry is None:
            raise ResearchBudgetLedgerInvalid("release reservation is missing")
        reservation_event, reservation = reservation_entry
        _validate_research_budget_envelope(
            reservation, role=role, policy_id=policy_id
        )
        if (
            payload.reservation_event_id != reservation_event.event_id
            or payload.request_sha256 != reservation.request_sha256
        ):
            raise ResearchBudgetLedgerInvalid("release conflicts with reservation")
        existing = ledger.terminals.get(payload.reservation_id)
        if existing is not None:
            event, stored = existing
            if not isinstance(stored, ResearchCallReleasedPayload) or (
                stored.model_dump(mode="json") != payload.model_dump(mode="json")
            ) or event.role != role or event.policy_id != policy_id or (
                event.parent_event_id != reservation_event.event_id
            ):
                raise IdempotencyConflict("reservation already has another terminal")
            return event, ledger.snapshot
        reservation_positions = [
            index
            for index, row in enumerate(rows)
            if row.get("event_id") == reservation_event.event_id
        ]
        if len(reservation_positions) != 1:
            raise ResearchBudgetLedgerInvalid("reservation event position is ambiguous")
        if any(
            _dispatch_matches_reservation(
                Event.model_validate(row), reservation_event, reservation
            )
            for row in rows[reservation_positions[0] + 1 :]
        ):
            raise ResearchBudgetLedgerInvalid(
                "a recorded dispatch cannot be released as unattempted"
            )
        execution_generation = _fenced_execution_generation_for_rows(
            authority, rows, operation="release provider spend"
        )
        event = _append_research_budget_event_unlocked(
            authority,
            stream,
            payload,
            role=role,
            policy_id=policy_id,
            parent_event_id=reservation_event.event_id,
            execution_generation=execution_generation,
        )
        projected = _money(reservation.projected_max_cost_usd)
        snapshot = ResearchBudgetSnapshot(
            ceiling_usd=ledger.snapshot.ceiling_usd,
            settled_usd=ledger.snapshot.settled_usd,
            outstanding_usd=ledger.snapshot.outstanding_usd - projected,
        )
        return event, snapshot


@dataclass(frozen=True)
class ResearchDelegationSnapshot:
    ceiling_usd: Decimal
    root_call_spend_usd: Decimal
    delegated_spend_usd: Decimal
    outstanding_usd: Decimal

    @property
    def remaining_usd(self) -> Decimal:
        return (
            self.ceiling_usd
            - self.root_call_spend_usd
            - self.delegated_spend_usd
            - self.outstanding_usd
        )


@dataclass(frozen=True)
class _ResearchDelegationLedger:
    snapshot: ResearchDelegationSnapshot
    reservations: dict[str, tuple[Event, ResearchDelegationReservedPayload]]
    issued: dict[str, tuple[Event, ResearchDelegationIssuedPayload]]
    accepted: dict[str, tuple[Event, ResearchDelegationAcceptedPayload]]
    terminals: dict[
        str,
        tuple[
            Event,
            ResearchDelegationReleasedPayload | ResearchDelegationSettledPayload,
        ],
    ]


def _research_delegation_ledger(
    authority: InvestigationAuthority, rows: list[dict[str, Any]]
) -> _ResearchDelegationLedger:
    starts = [
        Event.model_validate(row)
        for row in rows
        if row.get("action_type") == ActionType.INVESTIGATION_START_REQUESTED.value
    ]
    if len(starts) != 1:
        raise ResearchBudgetLedgerInvalid(
            "research delegation requires exactly one root start"
        )
    start = starts[0].payload
    ceiling = _money(getattr(start, "chase_budget_usd", 0.0))
    root_quote_id = getattr(start, "research_quote_id", None)
    root_manifest_fingerprint = getattr(
        start, "research_route_manifest_fingerprint", None
    )
    if ceiling <= 0 or not root_quote_id:
        raise ResearchBudgetLedgerInvalid("root has no recursive quote authority")
    call_spend = _research_budget_ledger(authority, rows).snapshot.settled_usd
    reservations: dict[str, tuple[Event, ResearchDelegationReservedPayload]] = {}
    operations: dict[str, str] = {}
    issued: dict[str, tuple[Event, ResearchDelegationIssuedPayload]] = {}
    accepted: dict[str, tuple[Event, ResearchDelegationAcceptedPayload]] = {}
    terminals: dict[
        str,
        tuple[
            Event,
            ResearchDelegationReleasedPayload | ResearchDelegationSettledPayload,
        ],
    ] = {}
    positions: dict[str, int] = {}
    for position, row in enumerate(rows):
        event = Event.model_validate(row)
        if event.event_id in positions:
            raise ResearchBudgetLedgerInvalid("delegation event id is duplicated")
        positions[event.event_id] = position
        payload = event.payload
        if isinstance(payload, ResearchDelegationReservedPayload):
            if (
                payload.root_investigation_id != authority.investigation_id
                or payload.root_quote_id != root_quote_id
                or payload.route_manifest_fingerprint != root_manifest_fingerprint
            ):
                raise ResearchBudgetLedgerInvalid(
                    "delegation reservation conflicts with root authority"
                )
            if payload.delegation_id in reservations:
                raise ResearchBudgetLedgerInvalid("duplicate delegation id")
            prior = operations.get(payload.operation_sha256)
            if prior is not None and prior != payload.delegation_id:
                raise ResearchBudgetLedgerInvalid(
                    "delegation operation has multiple reservations"
                )
            reservations[payload.delegation_id] = (event, payload)
            operations[payload.operation_sha256] = payload.delegation_id
        elif isinstance(payload, ResearchDelegationIssuedPayload):
            if payload.delegation_id in issued:
                raise ResearchBudgetLedgerInvalid("delegation has multiple issue receipts")
            issued[payload.delegation_id] = (event, payload)
        elif isinstance(payload, ResearchDelegationAcceptedPayload):
            if payload.delegation_id in accepted:
                raise ResearchBudgetLedgerInvalid(
                    "delegation has multiple acceptance receipts"
                )
            accepted[payload.delegation_id] = (event, payload)
        elif isinstance(
            payload,
            (ResearchDelegationReleasedPayload, ResearchDelegationSettledPayload),
        ):
            if payload.delegation_id in terminals:
                raise ResearchBudgetLedgerInvalid("delegation has multiple terminals")
            terminals[payload.delegation_id] = (event, payload)

    delegated_spend = Decimal("0")
    outstanding = Decimal("0")
    for delegation_id, (reservation_event, reservation) in reservations.items():
        if reservation.generation == 1:
            if (
                reservation.parent_investigation_id != authority.investigation_id
                or reservation.parent_quote_id != root_quote_id
            ):
                raise ResearchBudgetLedgerInvalid(
                    "first delegation does not descend from the root"
                )
        else:
            parents = []
            for parent_id, (parent_event, parent) in reservations.items():
                parent_issue = issued.get(parent_id)
                parent_terminal = terminals.get(parent_id)
                if (
                    parent.child_investigation_id
                    == reservation.parent_investigation_id
                    and parent.generation + 1 == reservation.generation
                    and parent_issue is not None
                    and parent_issue[1].quote_id == reservation.parent_quote_id
                    and parent_terminal is not None
                    and isinstance(parent_terminal[1], ResearchDelegationSettledPayload)
                    and positions[parent_terminal[0].event_id]
                    < positions[reservation_event.event_id]
                    and positions[parent_event.event_id]
                    < positions[reservation_event.event_id]
                ):
                    parents.append(parent_id)
            if len(parents) != 1:
                raise ResearchBudgetLedgerInvalid(
                    "delegation generation has no unique settled parent"
                )
        issue_entry = issued.get(delegation_id)
        accept_entry = accepted.get(delegation_id)
        terminal_entry = terminals.get(delegation_id)
        if issue_entry is not None:
            issue_event, issue = issue_entry
            if (
                issue.reservation_event_id != reservation_event.event_id
                or positions[issue_event.event_id] <= positions[reservation_event.event_id]
            ):
                raise ResearchBudgetLedgerInvalid(
                    "delegation issue does not follow its reservation"
                )
        if accept_entry is not None:
            if issue_entry is None:
                raise ResearchBudgetLedgerInvalid("unissued delegation was accepted")
            accept_event, accept = accept_entry
            issue_event, _ = issue_entry
            if (
                accept.reservation_event_id != reservation_event.event_id
                or accept.issued_event_id != issue_event.event_id
                or accept.child_investigation_id != reservation.child_investigation_id
                or positions[accept_event.event_id] <= positions[issue_event.event_id]
            ):
                raise ResearchBudgetLedgerInvalid(
                    "delegation acceptance conflicts with its issued authority"
                )
        if terminal_entry is None:
            outstanding += _money(reservation.delegated_ceiling_usd)
            continue
        terminal_event, terminal = terminal_entry
        if (
            terminal.reservation_event_id != reservation_event.event_id
            or positions[terminal_event.event_id] <= positions[reservation_event.event_id]
        ):
            raise ResearchBudgetLedgerInvalid(
                "delegation terminal conflicts with its reservation"
            )
        if isinstance(terminal, ResearchDelegationReleasedPayload):
            if issue_entry is not None or accept_entry is not None:
                raise ResearchBudgetLedgerInvalid("issued delegation cannot be released")
            continue
        if accept_entry is None:
            raise ResearchBudgetLedgerInvalid("unaccepted delegation was settled")
        accept_event, _ = accept_entry
        if (
            terminal.accepted_event_id != accept_event.event_id
            or positions[terminal_event.event_id] <= positions[accept_event.event_id]
        ):
            raise ResearchBudgetLedgerInvalid(
                "delegation settlement conflicts with acceptance"
            )
        delegated_spend += _money(terminal.actual_cost_usd)
    known = set(reservations)
    if set(issued) - known or set(accepted) - known or set(terminals) - known:
        raise ResearchBudgetLedgerInvalid("delegation receipt references unknown hold")
    snapshot = ResearchDelegationSnapshot(
        ceiling_usd=ceiling,
        root_call_spend_usd=call_spend,
        delegated_spend_usd=delegated_spend,
        outstanding_usd=outstanding,
    )
    return _ResearchDelegationLedger(
        snapshot=snapshot,
        reservations=reservations,
        issued=issued,
        accepted=accepted,
        terminals=terminals,
    )


def _append_delegation_event_unlocked(
    authority: InvestigationAuthority,
    stream: OpenedInvestigationStream,
    payload: ResearchDelegationReservedPayload
    | ResearchDelegationIssuedPayload
    | ResearchDelegationAcceptedPayload
    | ResearchDelegationReleasedPayload
    | ResearchDelegationSettledPayload,
    *,
    parent_event_id: str | None,
) -> Event:
    event = prepare_typed_event(
        authority.investigation_id,
        payload,
        parent_event_id=parent_event_id,
        role="orchestrator",
        policy_id="orchestrator-chase-delegation",
    )
    _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
    return event


def reserve_research_delegation_authorized(
    authority: InvestigationAuthority,
    payload: ResearchDelegationReservedPayload,
) -> tuple[Event, ResearchDelegationSnapshot]:
    """Atomically replay or reserve root-family recursive capacity."""
    require_event_persistence()
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        ledger = _research_delegation_ledger(authority, rows)
        existing = ledger.reservations.get(payload.delegation_id)
        if existing is not None:
            event, stored = existing
            if stored.model_dump(mode="json") != payload.model_dump(mode="json"):
                raise IdempotencyConflict("delegation id was used for another operation")
            return event, ledger.snapshot
        if payload.operation_sha256 in {
            stored.operation_sha256 for _, stored in ledger.reservations.values()
        }:
            raise IdempotencyConflict("delegation operation is already reserved")
        amount = _money(payload.delegated_ceiling_usd)
        if amount > ledger.snapshot.remaining_usd:
            raise ResearchBudgetExceeded("delegation exceeds recursive ceiling")
        event = _append_delegation_event_unlocked(
            authority, stream, payload, parent_event_id=None
        )
        return event, ResearchDelegationSnapshot(
            ceiling_usd=ledger.snapshot.ceiling_usd,
            root_call_spend_usd=ledger.snapshot.root_call_spend_usd,
            delegated_spend_usd=ledger.snapshot.delegated_spend_usd,
            outstanding_usd=ledger.snapshot.outstanding_usd + amount,
        )


def research_delegation_snapshot_authorized(
    authority: InvestigationAuthority,
) -> ResearchDelegationSnapshot:
    """Read a validated root-family recursive-capacity projection."""
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        return _research_delegation_ledger(authority, rows).snapshot


def _advance_research_delegation_authorized(
    authority: InvestigationAuthority,
    payload: ResearchDelegationIssuedPayload
    | ResearchDelegationAcceptedPayload
    | ResearchDelegationReleasedPayload
    | ResearchDelegationSettledPayload,
) -> tuple[Event, ResearchDelegationSnapshot]:
    require_event_persistence()
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        ledger = _research_delegation_ledger(authority, rows)
        reservation_entry = ledger.reservations.get(payload.delegation_id)
        if reservation_entry is None:
            raise ResearchBudgetLedgerInvalid("delegation reservation is missing")
        reservation_event, reservation = reservation_entry
        if payload.reservation_event_id != reservation_event.event_id:
            raise ResearchBudgetLedgerInvalid("delegation receipt binds another hold")
        if isinstance(payload, ResearchDelegationIssuedPayload):
            existing = ledger.issued.get(payload.delegation_id)
            parent_id = reservation_event.event_id
        elif isinstance(payload, ResearchDelegationAcceptedPayload):
            issue_entry = ledger.issued.get(payload.delegation_id)
            if issue_entry is None or payload.issued_event_id != issue_entry[0].event_id:
                raise ResearchBudgetLedgerInvalid("delegation issue receipt is missing")
            if payload.child_investigation_id != reservation.child_investigation_id:
                raise ResearchBudgetLedgerInvalid("delegation child identity conflicts")
            existing = ledger.accepted.get(payload.delegation_id)
            parent_id = issue_entry[0].event_id
        else:
            existing = ledger.terminals.get(payload.delegation_id)
            if isinstance(payload, ResearchDelegationReleasedPayload):
                if payload.delegation_id in ledger.issued:
                    raise ResearchBudgetLedgerInvalid("issued delegation cannot be released")
                parent_id = reservation_event.event_id
            else:
                accept_entry = ledger.accepted.get(payload.delegation_id)
                if (
                    accept_entry is None
                    or payload.accepted_event_id != accept_entry[0].event_id
                ):
                    raise ResearchBudgetLedgerInvalid(
                        "delegation acceptance receipt is missing"
                    )
                parent_id = accept_entry[0].event_id
        if existing is not None:
            event, stored = existing
            if type(stored) is not type(payload) or (
                stored.model_dump(mode="json") != payload.model_dump(mode="json")
            ):
                raise IdempotencyConflict("delegation already has another receipt")
            return event, ledger.snapshot
        candidate = prepare_typed_event(
            authority.investigation_id,
            payload,
            parent_event_id=parent_id,
            role="orchestrator",
            policy_id="orchestrator-chase-delegation",
        )
        candidate_ledger = _research_delegation_ledger(
            authority, [*rows, candidate.model_dump(mode="json")]
        )
        _append_jsonl_authorized_unlocked(stream, candidate.model_dump(mode="json"))
        return candidate, candidate_ledger.snapshot


def mark_research_delegation_issued_authorized(
    authority: InvestigationAuthority, payload: ResearchDelegationIssuedPayload
) -> tuple[Event, ResearchDelegationSnapshot]:
    return _advance_research_delegation_authorized(authority, payload)


def accept_research_delegation_authorized(
    authority: InvestigationAuthority,
    payload: ResearchDelegationAcceptedPayload,
    *,
    child_authority: InvestigationAuthority,
    child_start_event: Event,
) -> tuple[Event, ResearchDelegationSnapshot]:
    child = child_start_event.payload
    root_rows = trajectory_authorized_append_order(authority)
    root_ledger = _research_delegation_ledger(authority, root_rows)
    reservation_entry = root_ledger.reservations.get(payload.delegation_id)
    issued_entry = root_ledger.issued.get(payload.delegation_id)
    if reservation_entry is None or issued_entry is None:
        raise ResearchBudgetLedgerInvalid("delegation authority receipts are missing")
    _, reservation = reservation_entry
    _, issued = issued_entry
    encoded = json.dumps(
        child_start_event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if (
        child_start_event.action_type != ActionType.INVESTIGATION_START_REQUESTED
        or child_start_event.event_id != payload.child_start_event_id
        or child_start_event.investigation_id != payload.child_investigation_id
        or hashlib.sha256(encoded).hexdigest() != payload.child_start_sha256
        or getattr(child, "research_delegation_id", None) != payload.delegation_id
        or getattr(child, "research_quote_id", None) != issued.quote_id
        or getattr(child, "research_delegated_from_quote_id", None)
        != reservation.parent_quote_id
        or getattr(child, "research_root_investigation_id", None)
        != reservation.root_investigation_id
        or getattr(child, "research_root_quote_id", None) != reservation.root_quote_id
        or getattr(child, "research_delegation_generation", None)
        != reservation.generation
        or _money(getattr(child, "approved_run_ceiling_usd", 0.0))
        != _money(reservation.delegated_ceiling_usd)
        or getattr(child, "research_route_manifest_fingerprint", None)
        != reservation.route_manifest_fingerprint
        or child_authority.investigation_id != payload.child_investigation_id
        or child_authority.account_id != authority.account_id
        or not any(
            Event.model_validate(row).model_dump(mode="json")
            == child_start_event.model_dump(mode="json")
            for row in trajectory_authorized_append_order(child_authority)
            if row.get("event_id") == child_start_event.event_id
        )
    ):
        raise ResearchBudgetLedgerInvalid(
            "delegation acceptance does not bind the immutable child start"
        )
    return _advance_research_delegation_authorized(authority, payload)


def release_research_delegation_authorized(
    authority: InvestigationAuthority, payload: ResearchDelegationReleasedPayload
) -> tuple[Event, ResearchDelegationSnapshot]:
    return _advance_research_delegation_authorized(authority, payload)


def settle_research_delegation_authorized(
    authority: InvestigationAuthority,
    payload: ResearchDelegationSettledPayload,
    *,
    child_authority: InvestigationAuthority,
    child_terminal_event: Event,
) -> tuple[Event, ResearchDelegationSnapshot]:
    child_rows = trajectory_authorized_append_order(child_authority)
    child_ledger = _research_budget_ledger(child_authority, child_rows)
    if (
        child_terminal_event.event_id != payload.child_terminal_event_id
        or child_authority.investigation_id != child_terminal_event.investigation_id
        or child_authority.account_id != authority.account_id
        or child_terminal_event.action_type
        not in {ActionType.INVESTIGATION_COMPLETED, ActionType.INVESTIGATION_FAILED}
        or not any(
            Event.model_validate(row).model_dump(mode="json")
            == child_terminal_event.model_dump(mode="json")
            for row in child_rows
            if row.get("event_id") == child_terminal_event.event_id
        )
        or _money(payload.actual_cost_usd) != child_ledger.snapshot.settled_usd
    ):
        raise ResearchBudgetLedgerInvalid(
            "delegation settlement does not bind a child terminal event"
        )
    return _advance_research_delegation_authorized(authority, payload)


def append_idempotent_typed_event_authorized(
    authority: InvestigationAuthority,
    payload: Any,
    *,
    document_id: str,
    mutation_key_sha256: str,
    request_sha256: str,
    role: str | None = None,
    policy_id: str | None = None,
) -> Event:
    """Validate, replay-check, create, and append one command under one lock.

    Rows are inspected in physical sealed-prefix/live-tail order. The event ID
    and timestamp are deliberately created only after acquiring the stream
    lock, making append order the command's commit order.
    """
    require_event_persistence()
    if (
        getattr(payload, "mutation_key_sha256", None) != mutation_key_sha256
        or getattr(payload, "request_sha256", None) != request_sha256
    ):
        raise ValueError("idempotency digests do not match the typed payload")
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        action_type = _coerce(payload.action_type)
        for row in rows:
            stored_payload = row.get("payload")
            if (
                row.get("action_type") != action_type
                or not isinstance(stored_payload, dict)
                or stored_payload.get("mutation_key_sha256") != mutation_key_sha256
            ):
                continue
            if stored_payload.get("request_sha256") != request_sha256:
                raise IdempotencyConflict("mutation key was used for another request")
            if row.get("document_id") != document_id:
                raise IdempotencyConflict("mutation key was used for another document")
            return Event.model_validate(row)
        event = prepare_typed_event(
            authority.investigation_id,
            payload,
            document_id=document_id,
            role=role,
            policy_id=policy_id,
        )
        _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
        return event


def trajectory_authorized_append_order(
    authority: InvestigationAuthority,
) -> list[dict[str, Any]]:
    """Return authenticated sealed-prefix/live-tail rows in append order."""
    with (
        open_investigation_stream(authority, writable=False) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
    return _deduplicate_event_rows(rows)


def log_event_authorized(
    authority: InvestigationAuthority,
    action_type: str | ActionType,
    *,
    payload: dict[str, Any] | None = None,
    parent_event_id: str | None = None,
    synthesis_id: str | None = None,
    phase: int | None = None,
    role: str | None = None,
    policy_id: str | None = None,
    document_id: str | None = None,
) -> str | None:
    """Non-fatal telemetry append through account-scoped authority."""
    if _events_disabled():
        return None
    event_id = _new_event_id()
    row = {
        "event_id": event_id,
        "investigation_id": authority.investigation_id,
        "synthesis_id": synthesis_id,
        "phase": phase,
        "role": role,
        "action_type": _coerce(action_type),
        "payload": payload or {},
        "parent_event_id": parent_event_id,
        "policy_id": policy_id or DEFAULT_POLICY_ID,
        "param_version": ANTIEK_PARAM_VERSION,
        "schema_version": EVENT_SCHEMA_VERSION,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "document_id": document_id,
    }

    def _write() -> None:
        with (
            open_investigation_stream(authority, writable=True) as stream,
            _authorized_event_lock(stream),
        ):
            _append_jsonl_authorized_unlocked(stream, row)

    _safe(_write)
    return event_id


def emit_typed_authorized(
    authority: InvestigationAuthority,
    payload: Any,
    **kwargs: Any,
) -> str | None:
    """Typed non-fatal telemetry append through account-scoped authority."""
    if _events_disabled():
        return None
    fence = current_investigation_execution(authority.investigation_id)
    if fence is not None:
        requested_generation = kwargs.pop("execution_generation", None)
        generation, holder_digest = fence
        if requested_generation is not None and requested_generation != generation:
            raise InvestigationExecutionBusy("event generation conflicts with executor")
        event = prepare_typed_event(
            authority.investigation_id,
            payload,
            execution_generation=generation,
            **kwargs,
        )
        with (
            open_investigation_stream(authority, writable=True) as stream,
            _authorized_event_lock(stream),
        ):
            rows = _validate_authorized_rows(
                authority, _read_opened_event_rows(stream, reject_malformed=True)
            )
            snapshot, _ = _investigation_execution_ledger(authority, rows)
            now_ms = time.time_ns() // 1_000_000
            if (
                snapshot is None
                or snapshot.completed
                or snapshot.generation != generation
                or snapshot.holder_digest != holder_digest
                or now_ms > snapshot.expires_at_ms
            ):
                raise InvestigationExecutionBusy("execution generation is stale")
            desired = event.model_dump(mode="json")
            existing = [row for row in rows if row.get("event_id") == event.event_id]
            if existing:
                stored = Event.model_validate(existing[0]) if len(existing) == 1 else None
                if stored is None or any(
                    (
                        stored.investigation_id != event.investigation_id,
                        stored.payload.model_dump(mode="json")
                        != event.payload.model_dump(mode="json"),
                        stored.parent_event_id != event.parent_event_id,
                        stored.synthesis_id != event.synthesis_id,
                        stored.phase != event.phase,
                        stored.role != event.role,
                        stored.policy_id != event.policy_id,
                        stored.document_id != event.document_id,
                    )
                ):
                    raise IdempotencyConflict(
                        f"fenced event id collision: {event.event_id}"
                    )
            else:
                _append_jsonl_authorized_unlocked(stream, desired)
        return event.event_id
    event = prepare_typed_event(authority.investigation_id, payload, **kwargs)

    def _write() -> None:
        with (
            open_investigation_stream(authority, writable=True) as stream,
            _authorized_event_lock(stream),
        ):
            _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))

    _safe(_write)
    return event.event_id


def emit_typed_authorized_strict(
    authority: InvestigationAuthority,
    payload: Any,
    **kwargs: Any,
) -> str:
    """Persist a typed authority event or fail the durable command."""
    event = prepare_typed_event(authority.investigation_id, payload, **kwargs)
    return append_event_once_authorized(authority, event)


# ---------------------------------------------------------------------------
# EventEmitter — orchestrator-side helper with parent linkage + policy hints
# ---------------------------------------------------------------------------


@dataclass
class EventEmitter:
    """Stateful emitter held for the lifetime of an investigation.

    Maintains a parent-event stack so nested spans inherit the right
    parent_event_id. Carries a default policy_id for non-LLM events; LLM
    calls override via ``emit(..., policy_id=...)``.

    Also carries an optional default ``document_id`` which is convenient for
    wrestling-loop callers that emit many document-scoped events in a row.
    """

    investigation_id: str
    synthesis_id: str | None = None
    events_dir: str | None = None
    default_policy_id: str = DEFAULT_POLICY_ID
    default_document_id: str | None = None
    enabled: bool = True
    _parent_stack: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        investigation_id: str,
        synthesis_id: str | None = None,
        events_dir: str | None = None,
        default_policy_id: str = DEFAULT_POLICY_ID,
        default_document_id: str | None = None,
    ) -> EventEmitter:
        return cls(
            investigation_id=investigation_id,
            synthesis_id=synthesis_id,
            events_dir=events_dir,
            default_policy_id=default_policy_id,
            default_document_id=default_document_id,
            enabled=not _events_disabled(),
        )

    def set_synthesis_id(self, synthesis_id: str) -> None:
        self.synthesis_id = synthesis_id

    def set_document_id(self, document_id: str | None) -> None:
        """Convenience for wrestling-loop callers entering a per-document span."""
        self.default_document_id = document_id

    def emit(
        self,
        action_type: str | ActionType,
        *,
        payload: dict[str, Any] | None = None,
        phase: int | None = None,
        role: str | None = None,
        policy_id: str | None = None,
        parent_event_id: str | None = None,
        document_id: str | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        parent = (
            parent_event_id
            if parent_event_id is not None
            else (self._parent_stack[-1] if self._parent_stack else None)
        )
        return log_event(
            self.investigation_id,
            action_type,
            payload=payload,
            parent_event_id=parent,
            synthesis_id=self.synthesis_id,
            phase=phase,
            role=role,
            policy_id=policy_id or self.default_policy_id,
            document_id=document_id if document_id is not None else self.default_document_id,
            events_dir=self.events_dir,
        )

    def emit_typed(
        self,
        payload: Any,  # one of the TypedPayload variants
        *,
        phase: int | None = None,
        role: str | None = None,
        policy_id: str | None = None,
        parent_event_id: str | None = None,
        document_id: str | None = None,
    ) -> str | None:
        """Typed counterpart to ``emit``. Validates the payload against the
        discriminated union in ``substrate/schemas/events.py`` and writes a
        row whose ``action_type`` is derived from the payload variant.

        The same parent-stack and document-id inheritance rules apply as for
        ``emit``.
        """
        if not self.enabled:
            return None
        parent = (
            parent_event_id
            if parent_event_id is not None
            else (self._parent_stack[-1] if self._parent_stack else None)
        )
        return emit_typed(
            self.investigation_id,
            payload,
            parent_event_id=parent,
            synthesis_id=self.synthesis_id,
            phase=phase,
            role=role,
            policy_id=policy_id or self.default_policy_id,
            document_id=document_id if document_id is not None else self.default_document_id,
            events_dir=self.events_dir,
        )

    @contextmanager
    def span(
        self,
        start_action: str | ActionType,
        end_action: str | ActionType,
        *,
        role: str | None = None,
        phase: int | None = None,
        policy_id: str | None = None,
        payload: dict[str, Any] | None = None,
        document_id: str | None = None,
        failed_action: str | ActionType = ActionType.ROLE_CALL_FAILED,
    ) -> Iterator[str | None]:
        """Emit start, push onto parent stack, yield start_id, emit end on
        success or failed_action on exception. Either way, pop the stack."""
        start_id = self.emit(
            start_action,
            role=role,
            phase=phase,
            policy_id=policy_id,
            payload=payload,
            document_id=document_id,
        )
        if start_id and self.enabled:
            self._parent_stack.append(start_id)
        try:
            yield start_id
        except Exception:
            tb = traceback.format_exc(limit=8)
            self.emit(
                failed_action,
                role=role,
                phase=phase,
                policy_id=policy_id,
                document_id=document_id,
                payload={"start_event_id": start_id, "traceback_tail": tb[-2000:]},
                parent_event_id=start_id,
            )
            raise
        else:
            self.emit(
                end_action,
                role=role,
                phase=phase,
                policy_id=policy_id,
                document_id=document_id,
                payload={"start_event_id": start_id},
                parent_event_id=start_id,
            )
        finally:
            if start_id and self._parent_stack and self._parent_stack[-1] == start_id:
                self._parent_stack.pop()


# ---------------------------------------------------------------------------
# Sealing — JSONL → Parquet at investigation completion
# ---------------------------------------------------------------------------


def seal_investigation(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    delete_jsonl: bool = True,
) -> str | None:
    """Seal one stream without racing a concurrent append."""
    if authority := current_investigation_authority(investigation_id):
        return seal_investigation_authorized(
            authority, delete_jsonl=delete_jsonl
        )
    path = _jsonl_path(investigation_id, events_dir=events_dir)
    with _event_file_lock(path):
        return _seal_investigation_unlocked(
            investigation_id,
            events_dir=events_dir,
            delete_jsonl=delete_jsonl,
        )


def _seal_investigation_unlocked(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    delete_jsonl: bool = True,
) -> str | None:
    """Convert the live JSONL trajectory to its sealed Parquet form.

    Called by phase 9 (or by ``archive_synthesis`` if the user wires it there).
    Returns the parquet path on success, None if the JSONL didn't exist or
    pyarrow isn't available.

    Idempotent: if the Parquet already exists, we re-seal (overwrite) only
    if the JSONL is newer (mtime check).
    """
    jl = _jsonl_path(investigation_id, events_dir=events_dir)
    pq = _parquet_path(investigation_id, events_dir=events_dir)
    return _seal_paths_unlocked(investigation_id, jl=jl, pq=pq, delete_jsonl=delete_jsonl)


def _seal_paths_unlocked(
    investigation_id: str, *, jl: str, pq: str, delete_jsonl: bool
) -> str | None:
    """Seal already-resolved paths while their stream lock is held."""

    if not os.path.exists(jl):
        if os.path.exists(pq):
            return pq  # already sealed
        return None

    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq_writer  # type: ignore[import-not-found]
    except ImportError:
        print(
            "events.seal_investigation: pyarrow not installed; "
            "leaving JSONL in place. Install pyarrow to enable Parquet seal.",
            file=sys.stderr,
        )
        return None

    rows: list[dict[str, Any]] = []
    if os.path.exists(pq):
        # A post-seal live tail must extend, never replace, the sealed prefix.
        rows.extend(pq_writer.read_table(pq).to_pylist())
    with open(jl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"events.seal: skipping malformed line: {e!r}", file=sys.stderr)
                continue
    if not rows:
        return None

    rows = _deduplicate_event_rows(rows)

    for r in rows:
        if isinstance(r.get("payload"), (dict, list)):
            r["payload"] = json.dumps(r["payload"], default=str)

    table = pa.Table.from_pylist(rows)
    tmp = pq + ".tmp"
    pq_writer.write_table(table, tmp, compression="zstd")
    os.replace(tmp, pq)

    if delete_jsonl:
        os.remove(jl)
    return pq


def seal_investigation_authorized(
    authority: InvestigationAuthority, *, delete_jsonl: bool = True
) -> str | None:
    """Seal exactly the account-authorized state-selected stream."""
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority,
            _read_opened_event_rows(stream, reject_malformed=True),
        )
        if not rows:
            return None
        try:
            import pyarrow as pa  # type: ignore[import-not-found]
            import pyarrow.parquet as pq_writer  # type: ignore[import-not-found]
        except ImportError:
            print(
                "events.seal_investigation: pyarrow not installed; "
                "leaving JSONL in place. Install pyarrow to enable Parquet seal.",
                file=sys.stderr,
            )
            return None
        rows = _deduplicate_event_rows(rows)
        for row in rows:
            if isinstance(row.get("payload"), (dict, list)):
                row["payload"] = json.dumps(row["payload"], default=str)
        table = pa.Table.from_pylist(rows)
        temporary = f".{stream.parquet_name}.{uuid.uuid4().hex}.tmp"
        fd = _open_regular_at(
            stream,
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        )
        try:
            with os.fdopen(os.dup(fd), "wb") as handle:
                pq_writer.write_table(table, handle, compression="zstd")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary,
                stream.parquet_name,
                src_dir_fd=stream.directory_fd,
                dst_dir_fd=stream.directory_fd,
            )
            os.fsync(stream.directory_fd)
        finally:
            os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=stream.directory_fd)
        if delete_jsonl:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(stream.jsonl_name, dir_fd=stream.directory_fd)
            os.fsync(stream.directory_fd)
        relative = (
            Path()
            if stream.state.value == "legacy"
            else Path("streams") / "v1" / authority.stream_key[:2]
        )
        return str(authority.root / relative / stream.parquet_name)


def _deduplicate_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate only byte-equivalent typed envelopes; never hide collisions."""

    deduplicated: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if not event_id:
            deduplicated.append(row)
            continue
        try:
            canonical = Event.model_validate(row).model_dump(mode="json")
        except (TypeError, ValueError):
            canonical = json.loads(json.dumps(row, sort_keys=True, default=str))
            payload = canonical.get("payload")
            if isinstance(payload, str):
                with contextlib.suppress(TypeError, ValueError):
                    canonical["payload"] = json.loads(payload)
        existing = seen.get(event_id)
        if existing is not None:
            if existing != canonical:
                raise ValueError(f"event id collision: {event_id}")
            continue
        seen[event_id] = canonical
        deduplicated.append(row)
    return deduplicated


# ---------------------------------------------------------------------------
# Query helpers (analytics; not called by orchestrator)
# ---------------------------------------------------------------------------


def _read_event_rows(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    reject_malformed: bool = False,
) -> list[dict[str, Any]]:
    pq = _parquet_path(investigation_id, events_dir=events_dir)
    jl = _jsonl_path(investigation_id, events_dir=events_dir)
    return _read_event_rows_from_paths(
        investigation_id,
        parquet_path=pq,
        jsonl_path=jl,
        reject_malformed=reject_malformed,
    )


def _read_event_rows_from_paths(
    investigation_id: str,
    *,
    parquet_path: str,
    jsonl_path: str,
    reject_malformed: bool = False,
) -> list[dict[str, Any]]:
    del investigation_id  # Row/authority congruence is enforced by authorized callers.
    pq = parquet_path
    jl = jsonl_path

    rows: list[dict[str, Any]] = []
    if os.path.exists(pq):
        try:
            import pyarrow.parquet as pq_reader

            table = pq_reader.read_table(pq)
            rows = table.to_pylist()
        except ImportError:
            if reject_malformed:
                raise ValueError(
                    "sealed event stream cannot be validated without pyarrow"
                ) from None
            print(
                "pyarrow not installed; reading sealed Parquet requires pyarrow.", file=sys.stderr
            )
    # A sealed investigation may receive a later append (for example a book
    # reopened in Wrestle). Merge its new live tail with the sealed prefix;
    # treating Parquet and JSONL as mutually exclusive hides durable events.
    if os.path.exists(jl):
        with open(jl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    if reject_malformed:
                        raise ValueError("event stream contains malformed JSON") from exc
                    continue

    for r in rows:
        if isinstance(r.get("payload"), str):
            with contextlib.suppress(TypeError, ValueError):
                r["payload"] = json.loads(r["payload"])

    return rows


def trajectory_authorized(
    authority: InvestigationAuthority,
) -> list[dict[str, Any]]:
    """Read one state-selected account stream and reject foreign display rows."""
    with (
        open_investigation_stream(authority, writable=False) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority,
            _read_opened_event_rows(stream, reject_malformed=True),
        )
    deduplicated = _deduplicate_event_rows(rows)
    deduplicated.sort(key=lambda row: (row.get("emitted_at") or "", row.get("event_id") or ""))
    return deduplicated


@contextmanager
def locked_trajectory_authorized(
    authority: InvestigationAuthority,
) -> Iterator[list[dict[str, Any]]]:
    """Pin an authorized trajectory against concurrent lifecycle appends.

    Recovery callers may hold this stream lock while committing an external
    fence transition. Normal authorized appends use the same lock, so a new
    start cannot cross the evidence-read/delete boundary.
    """
    with (
        open_investigation_stream(authority, writable=False) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority,
            _read_opened_event_rows(stream, reject_malformed=True),
        )
        deduplicated = _deduplicate_event_rows(rows)
        deduplicated.sort(
            key=lambda row: (row.get("emitted_at") or "", row.get("event_id") or "")
        )
        yield deduplicated


def trajectory(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Read all events for an investigation, ordered by emission time.
    Reads sealed Parquet if present; falls back to live JSONL otherwise.
    """
    if authority := current_investigation_authority(investigation_id):
        return trajectory_authorized(authority)
    rows = _read_event_rows(investigation_id, events_dir=events_dir)
    deduplicated: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if event_id and event_id in seen_event_ids:
            continue
        if event_id:
            seen_event_ids.add(event_id)
        deduplicated.append(row)
    rows = deduplicated
    rows.sort(key=lambda r: (r.get("emitted_at") or "", r.get("event_id") or ""))
    return rows


def action_counts(
    investigation_id: str | None = None,
    *,
    events_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Per-action_type counts. If investigation_id is given, scoped to that
    investigation; otherwise reads every Parquet/JSONL in the events dir.
    """
    counts: dict[str, int] = {}
    if investigation_id:
        for r in trajectory(investigation_id, events_dir=events_dir):
            at = r.get("action_type", "<missing>")
            counts[at] = counts.get(at, 0) + 1
    else:
        d = events_dir or default_events_dir()
        if not os.path.isdir(d):
            return []
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".parquet"):
                iid = fn[: -len(".parquet")]
            elif fn.endswith(".jsonl"):
                iid = fn[: -len(".jsonl")]
            else:
                continue
            for r in trajectory(iid, events_dir=events_dir):
                at = r.get("action_type", "<missing>")
                counts[at] = counts.get(at, 0) + 1
    return [
        {"action_type": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def validate_trajectory(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> dict[str, Any]:
    """Sanity-check a trajectory: dangling parent refs, ordering, required
    fields. Returns a report dict; non-zero ``issues`` count = problems found.
    """
    rows = trajectory(investigation_id, events_dir=events_dir)
    seen_ids: set[str] = set()
    issues: list[str] = []
    policies: set[str] = set()
    for i, r in enumerate(rows):
        eid = r.get("event_id")
        if not eid:
            issues.append(f"row {i}: missing event_id")
            continue
        seen_ids.add(eid)
        if not r.get("action_type"):
            issues.append(f"row {i}: missing action_type")
        if r.get("policy_id"):
            policies.add(r["policy_id"])
    seen2: set[str] = set()
    for i, r in enumerate(rows):
        eid = r.get("event_id")
        parent = r.get("parent_event_id")
        if parent and parent not in seen2:
            issues.append(
                f"row {i} ({r.get('action_type')}): "
                f"parent_event_id {parent} not seen earlier in stream"
            )
        if eid:
            seen2.add(eid)
    return {
        "investigation_id": investigation_id,
        "row_count": len(rows),
        "unique_event_ids": len(seen_ids),
        "policies_seen": sorted(policies),
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Worker-identity helpers (antiek-yegge-execute SPR-01)
# ---------------------------------------------------------------------------


def emit_worker_identity(
    investigation_id: str,
    *,
    worker_id: str,
    role: str,
    session_id: str,
    spawn_kind: str,
    parent_worker_id: str | None = None,
    expected_lifetime_s: int | None = None,
    context_hash: str | None = None,
    events_dir: str | None = None,
) -> str | None:
    """Emit a ``worker.identity`` event for a first-class worker registration.

    Thin wrapper over :func:`emit_typed` that builds the
    ``WorkerIdentityPayload``. The payload validates ``spawn_kind`` against its
    closed set + requires non-empty ``worker_id``/``role``/``session_id``;
    validation errors re-raise (a malformed event is a substrate bug, per the
    emit_typed contract). ``worker_id`` UUID-v7 shape is NOT validated here —
    that is the future registry's (SPR-04) responsibility.

    Example::

        emit_worker_identity(
            "inv-1", worker_id="0192-...", role="extractor",
            session_id="sess-1", spawn_kind="asyncio_task",
        )
    """
    from ..schemas.events import WorkerIdentityPayload

    payload = WorkerIdentityPayload(
        worker_id=worker_id,
        parent_worker_id=parent_worker_id,
        role=role,
        session_id=session_id,
        spawn_kind=spawn_kind,  # type: ignore[arg-type]
        expected_lifetime_s=expected_lifetime_s,
        context_hash=context_hash,
    )
    return emit_typed(investigation_id, payload, events_dir=events_dir)


def query_worker_identity(
    investigation_id: str,
    *,
    worker_id: str | None = None,
    parent_worker_id: str | None = None,
    role: str | None = None,
    events_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Return the ``worker.identity`` rows for an investigation, optionally
    filtered by ``worker_id`` / ``parent_worker_id`` / ``role``.

    Returns the payload dicts (already JSON-decoded) ordered by emission time.
    Empty list when no worker-identity events match — an honest absent, never a
    fabricated row.

    Example::

        rows = query_worker_identity("inv-1", role="extractor")
    """
    rows = [
        r
        for r in trajectory(investigation_id, events_dir=events_dir)
        if r.get("action_type") == ActionType.WORKER_IDENTITY.value
    ]
    payload_list: list[dict[str, Any]] = []
    for r in rows:
        payload = r.get("payload")
        if not isinstance(payload, dict):
            continue
        if worker_id is not None and payload.get("worker_id") != worker_id:
            continue
        if parent_worker_id is not None and payload.get("parent_worker_id") != parent_worker_id:
            continue
        if role is not None and payload.get("role") != role:
            continue
        out = dict(payload)
        out["_event_id"] = r.get("event_id")
        out["_emitted_at"] = r.get("emitted_at")
        payload_list.append(out)
    return payload_list


# ---------------------------------------------------------------------------
# CLI — diagnostic surface only
# ---------------------------------------------------------------------------


def _cmd_emit(args: argparse.Namespace) -> None:
    payload = json.loads(args.payload) if args.payload else None
    eid = log_event(
        args.investigation_id,
        args.action_type,
        payload=payload,
        phase=args.phase,
        role=args.role,
        synthesis_id=args.synthesis_id,
        parent_event_id=args.parent,
        policy_id=args.policy_id,
        document_id=args.document_id,
        events_dir=args.events_dir,
    )
    print(eid or "<failed-or-disabled>")


def _cmd_trajectory(args: argparse.Namespace) -> None:
    print(
        json.dumps(
            trajectory(args.investigation_id, events_dir=args.events_dir), indent=2, default=str
        )
    )


def _cmd_counts(args: argparse.Namespace) -> None:
    print(json.dumps(action_counts(args.investigation_id, events_dir=args.events_dir), indent=2))


def _cmd_seal(args: argparse.Namespace) -> None:
    out = seal_investigation(
        args.investigation_id, events_dir=args.events_dir, delete_jsonl=not args.keep_jsonl
    )
    print(out or "<nothing-to-seal>")


def _cmd_validate(args: argparse.Namespace) -> None:
    print(
        json.dumps(validate_trajectory(args.investigation_id, events_dir=args.events_dir), indent=2)
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Antiek typed event log (Parquet trajectory)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("emit")
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--action-type", required=True)
    sp.add_argument("--payload")
    sp.add_argument("--phase", type=int)
    sp.add_argument("--role")
    sp.add_argument("--synthesis-id")
    sp.add_argument("--parent")
    sp.add_argument("--policy-id")
    sp.add_argument("--document-id")
    sp.add_argument("--events-dir")
    sp.set_defaults(func=_cmd_emit)

    sp = sub.add_parser("trajectory")
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--events-dir")
    sp.set_defaults(func=_cmd_trajectory)

    sp = sub.add_parser("counts")
    sp.add_argument("--investigation-id")
    sp.add_argument("--events-dir")
    sp.set_defaults(func=_cmd_counts)

    sp = sub.add_parser("seal", help="Roll JSONL → Parquet for an investigation")
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--keep-jsonl", action="store_true")
    sp.add_argument("--events-dir")
    sp.set_defaults(func=_cmd_seal)

    sp = sub.add_parser("validate", help="Sanity check a trajectory")
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--events-dir")
    sp.set_defaults(func=_cmd_validate)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

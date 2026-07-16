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
Telemetry must never break a real synthesis. Every emit is wrapped in
``_safe``; errors print to stderr and return None.

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
import json
import os
import re
import stat
import sys
import time
import traceback
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Package-relative imports work in installed mode (`pip install -e .`).
# For direct-script execution (`python events.py ...`), fall back to a
# sys.path-based lookup so the CLI still works in dev.
try:
    from ..constants import ANTIEK_PARAM_VERSION
    from ..schemas.events import (
        DEFAULT_POLICY_ID,
        EVENT_SCHEMA_VERSION,
        ActionType,
        Event,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from constants import (  # type: ignore[no-redef,import-not-found]
        ANTIEK_PARAM_VERSION,
    )
    from schemas.events import (  # type: ignore[no-redef,import-not-found]
        DEFAULT_POLICY_ID,
        EVENT_SCHEMA_VERSION,
        ActionType,
        Event,
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


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


@contextmanager
def investigation_event_lock(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    timeout_s: float = 10.0,
) -> Iterator[int]:
    """Serialize access and yield an fd anchored to the validated event root."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}", investigation_id):
        raise ValueError("investigation_id is not safe for event storage")
    root = events_dir or default_events_dir()
    try:
        os.makedirs(root, mode=0o700, exist_ok=True)
        root_stat = os.lstat(root)
    except OSError as exc:
        raise PhysicalTrajectoryError("event root cannot be secured") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise PhysicalTrajectoryError("event root must be a real directory")
    root_fd = -1
    fd = -1
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened_root = os.fstat(root_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (
            root_stat.st_dev,
            root_stat.st_ino,
        ):
            raise PhysicalTrajectoryError("event root changed during validation")
        fd = os.open(
            f".{investigation_id}.delivery.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
    except OSError as exc:
        if root_fd >= 0:
            os.close(root_fd)
        raise PhysicalTrajectoryError("event lock cannot be opened safely") from exc
    try:
        lock_stat = os.fstat(fd)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
            raise PhysicalTrajectoryError(
                "event lock must be regular and singly linked"
            )
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "timed out waiting for investigation event lock"
                    ) from None
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        yield root_fd
    finally:
        if fd >= 0:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def _append_jsonl(path: str, row: dict[str, Any]) -> None:
    """Append a single JSON line. Open in 'a' mode — atomic at OS level for
    single-line writes ≤ PIPE_BUF. We never write multi-line payloads."""
    root = os.path.dirname(path)
    os.makedirs(root, mode=0o700, exist_ok=True)
    line = json.dumps(row, default=str, separators=(",", ":"))
    if "\n" in line:
        line = line.replace("\n", "\\n")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = -1
    try:
        fd = os.open(
            os.path.basename(path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PhysicalTrajectoryError(
                "event append target must be regular and singly linked"
            )
        data = (line + "\n").encode("utf-8")
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(root_fd)


def _append_jsonl_locked(
    investigation_id: str,
    path: str,
    row: dict[str, Any],
    *,
    events_dir: str | None,
) -> None:
    with investigation_event_lock(investigation_id, events_dir=events_dir):
        _append_jsonl(path, row)


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
    if _safe(
        _append_jsonl_locked,
        investigation_id,
        path,
        row,
        events_dir=events_dir,
    ) is None:
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
    strict_write: bool = False,
    event_id: str | None = None,
    idempotent: bool = False,
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

    if idempotent and event_id is None:
        raise ValueError("idempotent typed emission requires an explicit event_id")
    event_id = event_id or _new_event_id()
    # Construct the typed envelope; Pydantic validates the discriminator,
    # the wrestling document_id requirement, and the payload field types.
    # We intentionally do NOT _safe() this call — schema bugs should fail
    # loudly.
    event = Event(
        event_id=event_id,
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
        emitted_at=datetime.now(UTC),
        document_id=document_id,
    )

    row = event.model_dump(mode="json")
    path = _jsonl_path(investigation_id, events_dir=events_dir)
    def append_once() -> None:
        with investigation_event_lock(investigation_id, events_dir=events_dir):
            if idempotent and os.path.exists(path):
                with open(path, encoding="utf-8") as existing:
                    for line in existing:
                        try:
                            if json.loads(line).get("event_id") == event_id:
                                return
                        except (json.JSONDecodeError, AttributeError):
                            continue
            _append_jsonl(path, row)

    if strict_write:
        append_once()
    else:
        _safe(append_once)
    return event_id


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
        parent = parent_event_id if parent_event_id is not None else (
            self._parent_stack[-1] if self._parent_stack else None
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
        parent = parent_event_id if parent_event_id is not None else (
            self._parent_stack[-1] if self._parent_stack else None
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
            start_action, role=role, phase=phase,
            policy_id=policy_id, payload=payload, document_id=document_id,
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

_DEFAULT_OUTBOX_DB = object()


def seal_investigation(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    delete_jsonl: bool = True,
    outbox_db_path: str | None | object = _DEFAULT_OUTBOX_DB,
) -> str | None:
    """Convert the live JSONL trajectory to its sealed Parquet form.

    Called by phase 9 (or by ``archive_synthesis`` if the user wires it there).
    Returns the parquet path on success, None if the JSONL didn't exist or
    pyarrow isn't available.

    Idempotent: if the Parquet already exists, we re-seal (overwrite) only
    if the JSONL is newer (mtime check).
    """
    if outbox_db_path is _DEFAULT_OUTBOX_DB:
        from substrate.graph import default_db_path
        db_path: str | None = default_db_path()
    elif isinstance(outbox_db_path, str) or outbox_db_path is None:
        db_path = outbox_db_path
    else:
        raise TypeError("outbox_db_path must be a path or None")
    if db_path and os.path.exists(db_path):
        from runtime.db_lock import connect_write
        with (
            connect_write(db_path, purpose="event_log/seal") as con,
            investigation_event_lock(investigation_id, events_dir=events_dir),
        ):
            _refuse_pending_write_events(con, investigation_id)
            return _seal_investigation_unlocked(
                investigation_id, events_dir=events_dir,
                delete_jsonl=delete_jsonl,
            )
    with investigation_event_lock(investigation_id, events_dir=events_dir):
        return _seal_investigation_unlocked(
            investigation_id,
            events_dir=events_dir,
            delete_jsonl=delete_jsonl,
        )


def _refuse_pending_write_events(con: Any, investigation_id: str) -> None:
    exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_name='write_event_outbox'"
    ).fetchone()[0]
    if exists and con.execute(
        "SELECT 1 FROM write_event_outbox WHERE investigation_id=? "
        "AND state='pending' LIMIT 1", [investigation_id],
    ).fetchone():
        raise RuntimeError("cannot seal an investigation with pending Write events")


def _seal_investigation_unlocked(
    investigation_id: str,
    *,
    events_dir: str | None,
    delete_jsonl: bool,
) -> str | None:
    jl = _jsonl_path(investigation_id, events_dir=events_dir)
    pq = _parquet_path(investigation_id, events_dir=events_dir)

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

    # Reopened streams have an existing snapshot plus a live tail. Seal the
    # merged trajectory, not merely the tail, or resealing would erase history.
    tail_before = os.lstat(jl) if os.path.lexists(jl) else None
    rows = list(
        iter_physical_events(
            investigation_id,
            events_dir=events_dir,
            _lock_already_held=True,
        )
    )
    if not rows:
        return None

    for r in rows:
        if isinstance(r.get("payload"), (dict, list)):
            r["payload"] = json.dumps(r["payload"], default=str)

    table = pa.Table.from_pylist(rows)
    root = os.path.dirname(pq)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    tmp_name = f".{os.path.basename(pq)}.{uuid.uuid4().hex}.tmp"
    tmp_fd = -1
    try:
        tmp_fd = os.open(
            tmp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        with os.fdopen(tmp_fd, "wb") as tmp_stream:
            tmp_fd = -1
            pq_writer.write_table(table, tmp_stream, compression="zstd")
            tmp_stream.flush()
            os.fsync(tmp_stream.fileno())
        os.replace(
            tmp_name,
            os.path.basename(pq),
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )

        if delete_jsonl and tail_before is not None:
            tail_name = os.path.basename(jl)
            tail_after = os.stat(tail_name, dir_fd=root_fd, follow_symlinks=False)
            if (
                tail_after.st_dev != tail_before.st_dev
                or tail_after.st_ino != tail_before.st_ino
                or not stat.S_ISREG(tail_after.st_mode)
                or tail_after.st_nlink != 1
            ):
                raise PhysicalTrajectoryError("event tail changed during seal")
            os.unlink(tail_name, dir_fd=root_fd)
    finally:
        if tmp_fd >= 0:
            os.close(tmp_fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name, dir_fd=root_fd)
        os.close(root_fd)

    return pq


# ---------------------------------------------------------------------------
# Query helpers (analytics; not called by orchestrator)
# ---------------------------------------------------------------------------


def trajectory(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Read all events for an investigation, ordered by emission time.

    A sealed Parquet snapshot and a later live JSONL tail are merged by
    immutable event id, so long-lived streams remain visible after reopening.
    """
    pq = _parquet_path(investigation_id, events_dir=events_dir)
    jl = _jsonl_path(investigation_id, events_dir=events_dir)

    rows: list[dict[str, Any]] = []
    if os.path.exists(pq):
        try:
            import pyarrow.parquet as pq_reader
            table = pq_reader.read_table(pq)
            rows = table.to_pylist()
        except ImportError:
            print("pyarrow not installed; reading sealed Parquet requires pyarrow.",
                  file=sys.stderr)
    if os.path.exists(jl):
        with open(jl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if len(rows) == 1 and not isinstance(rows[0].get("payload"), str):
        return rows

    for r in rows:
        if isinstance(r.get("payload"), str):
            with contextlib.suppress(TypeError, ValueError):
                r["payload"] = json.loads(r["payload"])

    # A completed run normally never reopens after sealing. Long-lived product
    # streams can, however, append after a snapshot exists. Keep both layers
    # visible and collapse the overlap by immutable event id.
    by_id: dict[str, dict[str, Any]] = {}
    without_id: list[dict[str, Any]] = []
    for row in rows:
        event_id = row.get("event_id")
        if isinstance(event_id, str) and event_id:
            by_id[event_id] = row
        else:
            without_id.append(row)
    merged = [*by_id.values(), *without_id]
    merged.sort(key=lambda r: (r.get("emitted_at") or "", r.get("event_id") or ""))
    return merged


class PhysicalTrajectoryError(RuntimeError):
    """The durable event trajectory cannot be traversed without guessing."""


def _open_regular_event_file(path: str) -> int | None:
    if not os.path.lexists(path):
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise PhysicalTrajectoryError(
            f"event file must be regular and singly linked: {path}"
        ) from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise PhysicalTrajectoryError(
            f"event file must be regular and singly linked: {path}"
        )
    return fd


def _physical_identity(row: dict[str, Any]) -> str:
    return json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )


def iter_physical_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    lock_timeout_s: float = 10.0,
    _lock_already_held: bool = False,
) -> Iterator[dict[str, Any]]:
    """Yield completed durable events in physical snapshot-then-tail order.

    Delivery authority cannot use presentation timestamps. Incomplete final
    appends remain invisible until newline completion; malformed completed
    records and conflicting immutable identities fail closed.
    """
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}", investigation_id):
        raise ValueError("investigation_id is not safe for event storage")
    root = events_dir or default_events_dir()
    if os.path.lexists(root) and (os.path.islink(root) or not os.path.isdir(root)):
        raise PhysicalTrajectoryError("event root must be a real directory")
    lock = (
        contextlib.nullcontext()
        if _lock_already_held
        else investigation_event_lock(
            investigation_id, events_dir=root, timeout_s=lock_timeout_s
        )
    )
    captured: list[dict[str, Any]] = []
    with lock:
        pq = _parquet_path(investigation_id, events_dir=root)
        jl = _jsonl_path(investigation_id, events_dir=root)
        seen: dict[str, str] = {}
        snapshot_fd = _open_regular_event_file(pq)
        if snapshot_fd is not None:
            try:
                import pyarrow.parquet as pq_reader
            except ImportError as exc:  # pragma: no cover - optional dependency
                os.close(snapshot_fd)
                raise PhysicalTrajectoryError(
                    "reading a snapshot requires pyarrow"
                ) from exc
            try:
                with os.fdopen(snapshot_fd, "rb") as snapshot:
                    snapshot_fd = -1
                    parquet = pq_reader.ParquetFile(snapshot)
                    for batch in parquet.iter_batches(batch_size=128):
                        for row in batch.to_pylist():
                            if not isinstance(row, dict):
                                raise PhysicalTrajectoryError(
                                    "snapshot contains a non-object event"
                                )
                            if isinstance(row.get("payload"), str):
                                with contextlib.suppress(TypeError, ValueError):
                                    row["payload"] = json.loads(row["payload"])
                            event_id = row.get("event_id")
                            if not isinstance(event_id, str) or not event_id:
                                raise PhysicalTrajectoryError(
                                    "snapshot event is missing event_id"
                                )
                            identity = _physical_identity(row)
                            prior = seen.get(event_id)
                            if prior is not None:
                                if prior != identity:
                                    raise PhysicalTrajectoryError(
                                        "snapshot contains conflicting event identities"
                                    )
                                continue
                            seen[event_id] = identity
                            captured.append(row)
            except PhysicalTrajectoryError:
                raise
            except Exception as exc:
                raise PhysicalTrajectoryError(
                    f"unreadable event snapshot: {pq}"
                ) from exc
            finally:
                if snapshot_fd >= 0:
                    os.close(snapshot_fd)

        tail_fd = _open_regular_event_file(jl)
        if tail_fd is not None:
            with os.fdopen(tail_fd, "rb") as stream:
                for line_number, raw_line in enumerate(stream, start=1):
                    if not raw_line.endswith(b"\n"):
                        break
                    try:
                        row = json.loads(raw_line)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise PhysicalTrajectoryError(
                            f"malformed completed JSONL record at {jl}:{line_number}"
                        ) from exc
                    if not isinstance(row, dict):
                        raise PhysicalTrajectoryError(
                            f"non-object JSONL record at {jl}:{line_number}"
                        )
                    event_id = row.get("event_id")
                    if not isinstance(event_id, str) or not event_id:
                        raise PhysicalTrajectoryError(
                            f"event missing event_id at {jl}:{line_number}"
                        )
                    identity = _physical_identity(row)
                    prior = seen.get(event_id)
                    if prior is not None:
                        if prior != identity:
                            raise PhysicalTrajectoryError(
                                "event identity conflicts between snapshot and tail"
                            )
                        continue
                    seen[event_id] = identity
                    captured.append(row)
    yield from captured


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
    return [{"action_type": k, "count": v}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


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
            issues.append(f"row {i} ({r.get('action_type')}): "
                          f"parent_event_id {parent} not seen earlier in stream")
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
        args.investigation_id, args.action_type,
        payload=payload, phase=args.phase, role=args.role,
        synthesis_id=args.synthesis_id, parent_event_id=args.parent,
        policy_id=args.policy_id, document_id=args.document_id,
        events_dir=args.events_dir,
    )
    print(eid or "<failed-or-disabled>")


def _cmd_trajectory(args: argparse.Namespace) -> None:
    print(json.dumps(trajectory(args.investigation_id, events_dir=args.events_dir),
                     indent=2, default=str))


def _cmd_counts(args: argparse.Namespace) -> None:
    print(json.dumps(action_counts(args.investigation_id, events_dir=args.events_dir),
                     indent=2))


def _cmd_seal(args: argparse.Namespace) -> None:
    out = seal_investigation(args.investigation_id, events_dir=args.events_dir,
                             delete_jsonl=not args.keep_jsonl)
    print(out or "<nothing-to-seal>")


def _cmd_validate(args: argparse.Namespace) -> None:
    print(json.dumps(validate_trajectory(args.investigation_id, events_dir=args.events_dir),
                     indent=2))


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

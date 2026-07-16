"""Crash-safe command journal for the wrestling distillation call.

Provider adapters do not expose authoritative idempotency or result lookup.
Consequently a process that dies in ``sending`` is ambiguous forever until an
operator reconciles it; replay must never infer that transport did not happen.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import stat
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from runtime.db_lock import connect_write
from substrate.schemas import DistillationDeliveredPayload


class CommandState(StrEnum):
    RESERVED = "reserved"
    SENDING = "sending"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    AMBIGUOUS = "ambiguous"


class BindingConflict(RuntimeError):
    """The same request event was replayed with different authoritative bytes."""


class InvalidCommandTransition(RuntimeError):
    """The caller attempted a state transition that the journal forbids."""


@dataclass(frozen=True)
class CommandSnapshot:
    request_event_id: str
    binding_sha256: str
    state: CommandState
    delivery_event_id: str
    delivery_payload: DistillationDeliveredPayload | None
    policy_id: str | None
    investigation_id: str
    document_id: str | None


_DDL = """
CREATE TABLE IF NOT EXISTS distillation_dispatch_commands (
    request_event_id TEXT PRIMARY KEY,
    binding_json TEXT NOT NULL,
    binding_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('reserved','sending','completed','delivered','ambiguous')),
    delivery_event_id TEXT NOT NULL UNIQUE,
    delivery_payload_json TEXT,
    delivery_payload_sha256 TEXT,
    policy_id TEXT,
    investigation_id TEXT NOT NULL,
    document_id TEXT,
    created_at TEXT NOT NULL,
    sending_at TEXT,
    completed_at TEXT,
    delivered_at TEXT,
    ambiguous_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK (
        (state IN ('reserved','sending') AND delivery_payload_json IS NULL
            AND delivery_payload_sha256 IS NULL AND policy_id IS NULL)
        OR (state IN ('completed','delivered') AND delivery_payload_json IS NOT NULL
            AND delivery_payload_sha256 IS NOT NULL AND policy_id IS NOT NULL)
        OR (state = 'ambiguous' AND delivery_payload_json IS NULL
            AND delivery_payload_sha256 IS NULL AND policy_id IS NULL)
    ),
    CHECK (
        (state = 'reserved' AND sending_at IS NULL AND completed_at IS NULL
            AND delivered_at IS NULL AND ambiguous_at IS NULL)
        OR (state = 'sending' AND sending_at IS NOT NULL AND completed_at IS NULL
            AND delivered_at IS NULL AND ambiguous_at IS NULL)
        OR (state = 'completed' AND sending_at IS NOT NULL AND completed_at IS NOT NULL
            AND delivered_at IS NULL AND ambiguous_at IS NULL)
        OR (state = 'delivered' AND sending_at IS NOT NULL AND completed_at IS NOT NULL
            AND delivered_at IS NOT NULL AND ambiguous_at IS NULL)
        OR (state = 'ambiguous' AND sending_at IS NOT NULL AND completed_at IS NULL
            AND delivered_at IS NULL AND ambiguous_at IS NOT NULL)
    )
)
"""


def _canonical(value: Mapping[str, object] | dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _required(name: str, value: str) -> None:
    if not value or len(value.encode("utf-8")) > 512:
        raise ValueError(f"{name} must be 1..512 UTF-8 bytes")


def _delivery_event_id(request_event_id: str) -> str:
    return "evt-distill-" + hashlib.sha256(request_event_id.encode("utf-8")).hexdigest()[:32]


async def _finish_cancelled_task(task: asyncio.Task[Any]) -> None:
    """Finish lock cleanup even if the caller receives repeated cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()


class DistillationDispatchJournal:
    def __init__(self, db_path: str):
        if not db_path:
            raise ValueError("db_path is required")
        self.db_path = db_path
        with connect_write(db_path, purpose="distillation-dispatch-init") as connection:
            connection.execute(_DDL)

    @contextmanager
    def execution_guard(self, request_event_id: str) -> Iterator[None]:
        """Serialize one command across processes, including its provider call."""
        _required("request_event_id", request_event_id)
        lock_path = self.db_path + ".distillation-" + _sha256(request_event_id)[:24] + ".lock"
        parent = os.path.dirname(lock_path)
        if parent:
            os.makedirs(parent, mode=0o700, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError("distillation command lock is not a private regular file")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @asynccontextmanager
    async def async_execution_guard(self, request_event_id: str) -> AsyncIterator[None]:
        """Serialize a command without blocking the caller's event loop."""
        guard = self.execution_guard(request_event_id)
        acquire = asyncio.create_task(asyncio.to_thread(guard.__enter__))
        try:
            await asyncio.shield(acquire)
        except asyncio.CancelledError:
            await _finish_cancelled_task(acquire)
            release = asyncio.create_task(
                asyncio.to_thread(guard.__exit__, None, None, None)
            )
            await _finish_cancelled_task(release)
            raise
        try:
            yield
        finally:
            release = asyncio.create_task(
                asyncio.to_thread(guard.__exit__, None, None, None)
            )
            try:
                await asyncio.shield(release)
            except asyncio.CancelledError:
                await _finish_cancelled_task(release)
                raise

    def reserve(
        self,
        request_event_id: str,
        binding: Mapping[str, object],
        *,
        investigation_id: str,
        document_id: str | None,
    ) -> CommandSnapshot:
        _required("request_event_id", request_event_id)
        _required("investigation_id", investigation_id)
        binding_json = _canonical(dict(binding))
        binding_sha256 = _sha256(binding_json)
        if len(binding_json.encode("utf-8")) > 32_768:
            raise ValueError("distillation binding exceeds 32768 UTF-8 bytes")
        now = _now()
        with connect_write(self.db_path, purpose="distillation-dispatch-reserve") as connection:
            connection.execute(_DDL)
            row = connection.execute(
                "SELECT * FROM distillation_dispatch_commands WHERE request_event_id=?",
                [request_event_id],
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO distillation_dispatch_commands "
                    "(request_event_id,binding_json,binding_sha256,state,delivery_event_id,"
                    "investigation_id,document_id,created_at,updated_at) "
                    "VALUES (?,?,?,'reserved',?,?,?,?,?)",
                    [request_event_id, binding_json, binding_sha256,
                     _delivery_event_id(request_event_id), investigation_id, document_id, now, now],
                )
            else:
                columns = [item[0] for item in connection.description]
                existing = dict(zip(columns, row, strict=True))
                if existing["binding_sha256"] != binding_sha256 or existing["binding_json"] != binding_json:
                    raise BindingConflict("request event binding changed")
                if existing["investigation_id"] != investigation_id or existing["document_id"] != document_id:
                    raise BindingConflict("request event scope changed")
            return self._load(connection, request_event_id)

    def mark_sending(self, request_event_id: str) -> CommandSnapshot:
        return self._transition(request_event_id, CommandState.RESERVED, CommandState.SENDING)

    def mark_ambiguous(self, request_event_id: str) -> CommandSnapshot:
        return self._transition(request_event_id, CommandState.SENDING, CommandState.AMBIGUOUS)

    def mark_completed(
        self,
        request_event_id: str,
        payload: DistillationDeliveredPayload,
        *,
        policy_id: str,
    ) -> CommandSnapshot:
        _required("policy_id", policy_id)
        if payload.request_event_id != request_event_id:
            raise BindingConflict("delivery payload request identity changed")
        payload_json = _canonical(payload.model_dump(mode="json"))
        now = _now()
        with connect_write(self.db_path, purpose="distillation-dispatch-complete") as connection:
            updated = connection.execute(
                "UPDATE distillation_dispatch_commands SET state='completed',"
                "delivery_payload_json=?,delivery_payload_sha256=?,policy_id=?,completed_at=?,updated_at=? "
                "WHERE request_event_id=? AND state='sending' RETURNING request_event_id",
                [payload_json, _sha256(payload_json), policy_id, now, now, request_event_id],
            ).fetchone()
            if updated is None:
                raise InvalidCommandTransition("only sending can complete")
            return self._load(connection, request_event_id)

    def mark_delivered(self, request_event_id: str) -> CommandSnapshot:
        return self._transition(request_event_id, CommandState.COMPLETED, CommandState.DELIVERED)

    def load(self, request_event_id: str) -> CommandSnapshot:
        with connect_write(self.db_path, purpose="distillation-dispatch-load") as connection:
            return self._load(connection, request_event_id)

    def _transition(
        self, request_event_id: str, source: CommandState, target: CommandState
    ) -> CommandSnapshot:
        timestamp_column = {
            CommandState.SENDING: "sending_at",
            CommandState.DELIVERED: "delivered_at",
            CommandState.AMBIGUOUS: "ambiguous_at",
        }[target]
        now = _now()
        with connect_write(self.db_path, purpose=f"distillation-dispatch-{target.value}") as connection:
            updated = connection.execute(
                f"UPDATE distillation_dispatch_commands SET state=?,{timestamp_column}=?,updated_at=? "
                "WHERE request_event_id=? AND state=? RETURNING request_event_id",
                [target.value, now, now, request_event_id, source.value],
            ).fetchone()
            if updated is None:
                raise InvalidCommandTransition(f"only {source.value} can become {target.value}")
            return self._load(connection, request_event_id)

    @staticmethod
    def _load(connection: object, request_event_id: str) -> CommandSnapshot:
        cursor = connection.execute(  # type: ignore[attr-defined]
            "SELECT * FROM distillation_dispatch_commands WHERE request_event_id=?",
            [request_event_id],
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(request_event_id)
        columns = [item[0] for item in cursor.description]
        value = dict(zip(columns, row, strict=True))
        payload_json = value["delivery_payload_json"]
        payload = None
        if payload_json is not None:
            if _sha256(payload_json) != value["delivery_payload_sha256"]:
                raise RuntimeError("stored distillation delivery digest mismatch")
            payload = DistillationDeliveredPayload.model_validate_json(payload_json)
        return CommandSnapshot(
            request_event_id=value["request_event_id"],
            binding_sha256=value["binding_sha256"],
            state=CommandState(value["state"]),
            delivery_event_id=value["delivery_event_id"],
            delivery_payload=payload,
            policy_id=value["policy_id"],
            investigation_id=value["investigation_id"],
            document_id=value["document_id"],
        )

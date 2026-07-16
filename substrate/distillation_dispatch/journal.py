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
    spend_run_id: str | None
    fallback_chain_id: str | None
    manifest_sha256: str | None
    fallback_index: int | None
    hold_id: str | None


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
    spend_run_id TEXT,
    fallback_chain_id TEXT,
    manifest_sha256 TEXT,
    fallback_index INTEGER,
    hold_id TEXT,
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

_LOCAL_COMPLETION_DDL = """
CREATE TABLE IF NOT EXISTS distillation_dispatch_local_completions (
    request_event_id TEXT PRIMARY KEY,
    delivery_payload_json TEXT NOT NULL,
    delivery_payload_sha256 TEXT NOT NULL,
    policy_id TEXT NOT NULL CHECK (starts_with(policy_id, 'wrestling-fallback/')),
    completed_at TEXT NOT NULL,
    delivered_at TEXT
)
"""

_CORRELATION_COLUMNS = {
    "spend_run_id": "TEXT",
    "fallback_chain_id": "TEXT",
    "manifest_sha256": "TEXT",
    "fallback_index": "INTEGER",
    "hold_id": "TEXT",
}

_CORRELATION_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS distillation_dispatch_hold_correlations (
    request_event_id TEXT NOT NULL,
    fallback_index INTEGER NOT NULL CHECK (fallback_index >= 0),
    hold_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_event_id, fallback_index),
    UNIQUE (request_event_id, hold_id)
)
"""


def _ensure_schema(connection: object) -> None:
    connection.execute(_DDL)  # type: ignore[attr-defined]
    present = {
        str(row[1])
        for row in connection.execute(  # type: ignore[attr-defined]
            "PRAGMA table_info('distillation_dispatch_commands')"
        ).fetchall()
    }
    for name, column_type in _CORRELATION_COLUMNS.items():
        if name not in present:
            connection.execute(  # type: ignore[attr-defined]
                f"ALTER TABLE distillation_dispatch_commands ADD COLUMN {name} {column_type}"
            )
    connection.execute(_CORRELATION_HISTORY_DDL)  # type: ignore[attr-defined]
    connection.execute(_LOCAL_COMPLETION_DDL)  # type: ignore[attr-defined]


@contextmanager
def _transaction(connection: object) -> Iterator[None]:
    connection.execute("BEGIN TRANSACTION")  # type: ignore[attr-defined]
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK")  # type: ignore[attr-defined]
        raise
    else:
        connection.execute("COMMIT")  # type: ignore[attr-defined]

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
            _ensure_schema(connection)

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
            _ensure_schema(connection)
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

    def authorize_sending(
        self,
        request_event_id: str,
        *,
        spend_run_id: str,
        fallback_chain_id: str,
        manifest_sha256: str,
        fallback_index: int,
        hold_id: str,
    ) -> CommandSnapshot:
        for name, value in (
            ("spend_run_id", spend_run_id),
            ("fallback_chain_id", fallback_chain_id),
            ("hold_id", hold_id),
        ):
            _required(name, value)
        if len(manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in manifest_sha256):
            raise ValueError("manifest_sha256 must be lowercase SHA-256")
        if (
            isinstance(fallback_index, bool)
            or not isinstance(fallback_index, int)
            or fallback_index < 0
        ):
            raise ValueError("fallback_index must be a non-negative integer")
        now = _now()
        authority = (spend_run_id, fallback_chain_id, manifest_sha256)
        with (
            connect_write(
                self.db_path, purpose="distillation-dispatch-authorize"
            ) as connection,
            _transaction(connection),
        ):
            return self._authorize_sending_transaction(
                connection,
                request_event_id=request_event_id,
                authority=authority,
                fallback_index=fallback_index,
                hold_id=hold_id,
                now=now,
            )

    def _authorize_sending_transaction(
        self,
        connection: object,
        *,
        request_event_id: str,
        authority: tuple[str, str, str],
        fallback_index: int,
        hold_id: str,
        now: str,
    ) -> CommandSnapshot:
        snapshot = self._load(connection, request_event_id)
        actual_authority = (
            snapshot.spend_run_id,
            snapshot.fallback_chain_id,
            snapshot.manifest_sha256,
        )
        if snapshot.state is CommandState.RESERVED:
            if fallback_index != 0:
                raise BindingConflict("first distillation hold must be fallback index zero")
            connection.execute(  # type: ignore[attr-defined]
                "UPDATE distillation_dispatch_commands SET state='sending',sending_at=?,"
                "spend_run_id=?,fallback_chain_id=?,manifest_sha256=?,fallback_index=?,"
                "hold_id=?,updated_at=? WHERE request_event_id=? AND state='reserved'",
                [now, *authority, fallback_index, hold_id, now, request_event_id],
            )
        elif snapshot.state is CommandState.SENDING:
            if actual_authority != authority:
                raise BindingConflict("distillation spend authority changed")
            if (snapshot.fallback_index, snapshot.hold_id) == (fallback_index, hold_id):
                return snapshot
            if snapshot.fallback_index is not None and fallback_index < snapshot.fallback_index:
                historical = connection.execute(  # type: ignore[attr-defined]
                    "SELECT hold_id FROM distillation_dispatch_hold_correlations "
                    "WHERE request_event_id=? AND fallback_index=?",
                    [request_event_id, fallback_index],
                ).fetchone()
                if historical is None or str(historical[0]) != hold_id:
                    raise BindingConflict("distillation historical hold changed")
                return snapshot
            if snapshot.fallback_index is None or fallback_index != snapshot.fallback_index + 1:
                raise BindingConflict("distillation fallback hold lineage changed")
            connection.execute(  # type: ignore[attr-defined]
                "UPDATE distillation_dispatch_commands SET fallback_index=?,hold_id=?,updated_at=? "
                "WHERE request_event_id=? AND state='sending' AND fallback_index=?",
                [fallback_index, hold_id, now, request_event_id, snapshot.fallback_index],
            )
        else:
            if actual_authority != authority or (
                snapshot.fallback_index,
                snapshot.hold_id,
            ) != (fallback_index, hold_id):
                raise BindingConflict("distillation spend correlation changed")
            return snapshot
        existing = connection.execute(  # type: ignore[attr-defined]
            "SELECT hold_id FROM distillation_dispatch_hold_correlations "
            "WHERE request_event_id=? AND fallback_index=?",
            [request_event_id, fallback_index],
        ).fetchone()
        if existing is None:
            connection.execute(  # type: ignore[attr-defined]
                "INSERT INTO distillation_dispatch_hold_correlations "
                "(request_event_id,fallback_index,hold_id,created_at) VALUES (?,?,?,?)",
                [request_event_id, fallback_index, hold_id, now],
            )
        elif str(existing[0]) != hold_id:
            raise BindingConflict("distillation fallback hold identity changed")
        return self._load(connection, request_event_id)

    def mark_ambiguous(
        self, request_event_id: str, *, hold_id: str | None = None
    ) -> CommandSnapshot:
        snapshot = self.load(request_event_id)
        if snapshot.hold_id is not None and hold_id != snapshot.hold_id:
            raise BindingConflict("ambiguous provider hold differs from authorized hold")
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

    def mark_proven_unsent_completed(
        self,
        request_event_id: str,
        payload: DistillationDeliveredPayload,
        *,
        policy_id: str,
    ) -> CommandSnapshot:
        """Persist a local result atomically; no committed sending state exists."""
        _required("policy_id", policy_id)
        if not policy_id.startswith("wrestling-fallback/"):
            raise ValueError("proven-unsent policy must be a wrestling fallback")
        if payload.request_event_id != request_event_id:
            raise BindingConflict("delivery payload request identity changed")
        payload_json = _canonical(payload.model_dump(mode="json"))
        now = _now()
        with connect_write(
            self.db_path, purpose="distillation-dispatch-complete-proven-unsent"
        ) as connection:
            state = connection.execute(
                "SELECT state FROM distillation_dispatch_commands WHERE request_event_id=?",
                [request_event_id],
            ).fetchone()
            if state is None or state[0] != CommandState.RESERVED.value:
                raise InvalidCommandTransition("only reserved can complete proven-unsent")
            connection.execute(
                "INSERT INTO distillation_dispatch_local_completions "
                "(request_event_id,delivery_payload_json,delivery_payload_sha256,"
                "policy_id,completed_at) VALUES (?,?,?,?,?)",
                [request_event_id, payload_json, _sha256(payload_json), policy_id, now],
            )
            return self._load(connection, request_event_id)

    def mark_delivered(self, request_event_id: str) -> CommandSnapshot:
        now = _now()
        with connect_write(
            self.db_path, purpose="distillation-dispatch-deliver-local"
        ) as connection:
            updated = connection.execute(
                "UPDATE distillation_dispatch_local_completions SET delivered_at=? "
                "WHERE request_event_id=? AND delivered_at IS NULL RETURNING request_event_id",
                [now, request_event_id],
            ).fetchone()
            if updated is not None:
                return self._load(connection, request_event_id)
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
        correlation = tuple(value.get(name) for name in _CORRELATION_COLUMNS)
        if any(item is None for item in correlation) and any(
            item is not None for item in correlation
        ):
            raise RuntimeError("stored distillation spend correlation is incomplete")
        manifest_sha256 = value.get("manifest_sha256")
        if manifest_sha256 is not None and (
            len(manifest_sha256) != 64
            or any(c not in "0123456789abcdef" for c in manifest_sha256)
        ):
            raise RuntimeError("stored distillation manifest digest is invalid")
        local_row = connection.execute(  # type: ignore[attr-defined]
            "SELECT * FROM distillation_dispatch_local_completions WHERE request_event_id=?",
            [request_event_id],
        ).fetchone()
        if local_row is not None:
            if value["state"] != CommandState.RESERVED.value:
                raise RuntimeError("local completion command is not reserved")
            local_columns = [item[0] for item in connection.description]  # type: ignore[attr-defined]
            local = dict(zip(local_columns, local_row, strict=True))
            payload_json = local["delivery_payload_json"]
            if _sha256(payload_json) != local["delivery_payload_sha256"]:
                raise RuntimeError("stored local completion digest mismatch")
            local_payload = DistillationDeliveredPayload.model_validate_json(payload_json)
            if local_payload.request_event_id != request_event_id:
                raise RuntimeError("stored local completion request identity mismatch")
            return CommandSnapshot(
                request_event_id=value["request_event_id"],
                binding_sha256=value["binding_sha256"],
                state=(
                    CommandState.DELIVERED
                    if local["delivered_at"] is not None
                    else CommandState.COMPLETED
                ),
                delivery_event_id=value["delivery_event_id"],
                delivery_payload=local_payload,
                policy_id=local["policy_id"],
                investigation_id=value["investigation_id"],
                document_id=value["document_id"],
                spend_run_id=None,
                fallback_chain_id=None,
                manifest_sha256=None,
                fallback_index=None,
                hold_id=None,
            )
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
            spend_run_id=value.get("spend_run_id"),
            fallback_chain_id=value.get("fallback_chain_id"),
            manifest_sha256=manifest_sha256,
            fallback_index=value.get("fallback_index"),
            hold_id=value.get("hold_id"),
        )

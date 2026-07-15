"""SQLite owner-bound paid-operation authority store."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from substrate.paid_operations.contracts import MAX_CANONICAL_INTENT_BYTES, canonicalize_intent

_MIGRATION = Path(__file__).with_name("migrations") / "001_authority.sql"
_MAX_SQLITE_INT = 9_223_372_036_854_775_807
_MAX_TEXT_BYTES = 4096
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9_][a-z0-9._:-]{0,191}$")

_STATES = frozenset(
    {
        "intent_created",
        "consent_issued",
        "queued",
        "running",
        "complete",
        "failed",
        "budget_halted",
        "timed_out",
        "failed_reconcile",
    }
)
_TRANSITIONS = {
    "intent_created": frozenset({"consent_issued"}),
    "consent_issued": frozenset({"queued"}),
}
_PATCH_COLUMNS = frozenset({"updated_at_ms"})
_FUTURE_AUTHORITY_PATCH_COLUMNS = frozenset(
    {
        "consent_token_hash",
        "consent_key_id",
        "consent_issued_at_ms",
        "consent_expires_at_ms",
        "consent_claimed_at_ms",
        "lease_worker_id",
        "lease_generation",
        "lease_expires_at_ms",
        "terminal_code",
        "terminal_reason",
        "reconciliation_status",
        "result_checkpoint_hash",
        "settled_cents",
    }
)
_TRANSITION_PATCH_COLUMNS = {
    ("intent_created", "consent_issued"): frozenset(
        {
            "updated_at_ms",
            "consent_token_hash",
            "consent_key_id",
            "consent_issued_at_ms",
            "consent_expires_at_ms",
        }
    ),
    ("consent_issued", "queued"): frozenset(
        {
            "updated_at_ms",
            "consent_claimed_at_ms",
        }
    ),
}
_SNAPSHOT_COLUMNS = (
    "operation_id",
    "owner_user_id",
    "account_id",
    "kind",
    "intent_hash",
    "canonical_intent_json",
    "quote_cents",
    "ceiling_cents",
    "state",
    "version",
    "created_at_ms",
    "updated_at_ms",
    "expires_at_ms",
    "consent_token_hash",
    "consent_key_id",
    "consent_issued_at_ms",
    "consent_expires_at_ms",
    "consent_claimed_at_ms",
    "lease_worker_id",
    "lease_generation",
    "lease_expires_at_ms",
    "terminal_code",
    "terminal_reason",
    "reconciliation_status",
    "result_checkpoint_hash",
    "settled_cents",
)
_QUEUE_COLUMNS = (
    "operation_id",
    "owner_user_id",
    "account_id",
    "operation_kind",
    "intent_hash",
    "canonical_options_json",
    "enqueued_at_ms",
    "queue_state",
)


class OperationConflict(RuntimeError):
    """The operation exists but immutable material or CAS preconditions differ."""


class OperationStateError(RuntimeError):
    """Durable paid-operation state is malformed or violates the frozen graph."""


class PaidOperationCorruptionError(OperationStateError):
    """Startup validation found impossible paid-operation authority state."""


@dataclass(frozen=True)
class Subject:
    owner_user_id: str
    account_id: str


@dataclass(frozen=True)
class OperationSnapshot:
    operation_id: str
    owner_user_id: str
    account_id: str
    kind: str
    intent_hash: str
    canonical_intent_json: str
    quote_cents: int
    ceiling_cents: int
    state: str
    version: int
    created_at_ms: int
    updated_at_ms: int
    expires_at_ms: int
    consent_token_hash: str | None = None
    consent_key_id: str | None = None
    consent_issued_at_ms: int | None = None
    consent_expires_at_ms: int | None = None
    consent_claimed_at_ms: int | None = None
    lease_worker_id: str | None = None
    lease_generation: int | None = None
    lease_expires_at_ms: int | None = None
    terminal_code: str | None = None
    terminal_reason: str | None = None
    reconciliation_status: str | None = None
    result_checkpoint_hash: str | None = None
    settled_cents: int | None = None


@dataclass(frozen=True)
class QueueSnapshot:
    operation_id: str
    owner_user_id: str
    account_id: str
    operation_kind: str
    intent_hash: str
    canonical_options_json: str
    enqueued_at_ms: int
    queue_state: str


class PaidOperationStore:
    """One injected-path SQLite WAL authority store."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if not str(path).strip():
            raise ValueError("db_path is required")
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = path
        self._ensure_schema()
        self.validate_startup()

    def create_or_replay(
        self,
        subject: Subject,
        operation_id: str,
        kind: str,
        payload: Mapping[str, Any],
    ) -> OperationSnapshot:
        intent = canonicalize_intent(
            owner_user_id=subject.owner_user_id,
            account_id=subject.account_id,
            operation_id=operation_id,
            kind=kind,
            payload=payload,
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute(
                    f"SELECT {', '.join(_SNAPSHOT_COLUMNS)} FROM paid_operations "
                    "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ?",
                    (intent.operation_id, intent.owner_user_id, intent.account_id),
                ).fetchone()
                if row is not None:
                    snapshot = _snapshot(row)
                    if (
                        snapshot.kind != intent.kind
                        or snapshot.intent_hash != intent.intent_hash
                        or snapshot.canonical_intent_json.encode("utf-8")
                        != intent.canonical_bytes
                        or snapshot.quote_cents != intent.quote_cents
                        or snapshot.ceiling_cents != intent.ceiling_cents
                    ):
                        raise OperationConflict("operation id already has different material")
                    _validate_snapshot(snapshot)
                    con.execute("COMMIT")
                    return snapshot
                con.execute(
                    "INSERT INTO paid_operations ("
                    "operation_id, owner_user_id, account_id, kind, intent_hash, "
                    "canonical_intent_json, quote_cents, ceiling_cents, state, version, "
                    "created_at_ms, updated_at_ms, expires_at_ms"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'intent_created', 0, ?, ?, ?)",
                    (
                        intent.operation_id,
                        intent.owner_user_id,
                        intent.account_id,
                        intent.kind,
                        intent.intent_hash,
                        intent.canonical_bytes,
                        intent.quote_cents,
                        intent.ceiling_cents,
                        intent.created_at_ms,
                        intent.created_at_ms,
                        intent.expires_at_ms,
                    ),
                )
                inserted_snapshot = self._get_owned_in_tx(con, subject, intent.operation_id)
                if inserted_snapshot is None:  # pragma: no cover - insert just succeeded.
                    raise OperationStateError("inserted paid operation disappeared")
                con.execute("COMMIT")
                return inserted_snapshot
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def get_owned(self, subject: Subject, operation_id: str) -> OperationSnapshot | None:
        with self._connect() as con:
            snapshot = self._get_owned_in_tx(con, subject, operation_id)
            if snapshot is not None:
                _validate_snapshot(snapshot)
            return snapshot

    def compare_and_swap(
        self,
        subject: Subject,
        operation_id: str,
        expected_version: int,
        allowed_from: Sequence[str],
        to_state: str,
        patch: Mapping[str, Any] | None = None,
    ) -> OperationSnapshot:
        if isinstance(expected_version, bool) or expected_version < 0:
            raise ValueError("expected_version must be a non-negative integer")
        allowed = tuple(_state(state) for state in allowed_from)
        if not allowed:
            raise ValueError("allowed_from must be non-empty")
        target = _state(to_state)
        for state in allowed:
            if target not in _TRANSITIONS.get(state, frozenset()):
                raise OperationStateError(f"invalid transition {state}->{target}")
        patch_values = dict(patch or {})
        assignments = ["state = ?", "version = version + 1"]
        params: list[Any] = [target]
        for key in sorted(patch_values):
            assignments.append(f"{key} = ?")
            params.append(patch_values[key])
        params.extend(
            [
                operation_id,
                subject.owner_user_id,
                subject.account_id,
                expected_version,
                *allowed,
            ]
        )
        placeholders = ",".join("?" for _ in allowed)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                before = self._get_owned_in_tx(con, subject, operation_id)
                if before is not None:
                    _validate_snapshot(before)
                    _validate_patch(before, allowed, target, patch_values)
                cur = con.execute(
                    f"UPDATE paid_operations SET {', '.join(assignments)} "
                    "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ? "
                    f"AND version = ? AND state IN ({placeholders})",
                    params,
                )
                if cur.rowcount != 1:
                    raise OperationConflict("paid operation CAS precondition failed")
                snapshot = self._get_owned_in_tx(con, subject, operation_id)
                if snapshot is None:  # pragma: no cover - update just succeeded.
                    raise OperationStateError("updated paid operation disappeared")
                _validate_snapshot(snapshot)
                con.execute("COMMIT")
                return snapshot
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def claim_and_enqueue(
        self,
        subject: Subject,
        operation_id: str,
        *,
        token_hash: str,
        now_ms: int,
        canonical_options_json: bytes,
    ) -> tuple[OperationSnapshot, QueueSnapshot]:
        _hash("token_hash", token_hash)
        _required_int("now_ms", now_ms)
        if len(canonical_options_json) > MAX_CANONICAL_INTENT_BYTES:
            raise ValueError("canonical options exceed durable limit")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                before = self._get_owned_in_tx(con, subject, operation_id)
                if before is None:
                    raise OperationConflict("paid operation is unavailable")
                _validate_snapshot(before)
                if before.state == "queued":
                    queue = self._get_queue_in_tx(con, subject, operation_id)
                    if queue is None:
                        raise PaidOperationCorruptionError("queued operation is missing queue row")
                    if queue.canonical_options_json != canonical_options_json.decode("utf-8"):
                        raise OperationConflict("consent is not claimable")
                    con.execute("COMMIT")
                    return before, queue
                if before.state != "consent_issued":
                    raise OperationConflict("consent is not claimable")
                if before.consent_token_hash is None or not _constant_time_equal(
                    before.consent_token_hash, token_hash
                ):
                    raise OperationConflict("consent is not claimable")
                if before.consent_expires_at_ms is None or now_ms >= before.consent_expires_at_ms:
                    raise OperationConflict("consent is not claimable")
                if before.consent_claimed_at_ms is not None:
                    raise PaidOperationCorruptionError("claimed consent is missing queue row")
                con.execute(
                    "INSERT INTO paid_operation_queue ("
                    "account_id, owner_user_id, operation_id, operation_kind, intent_hash, "
                    "canonical_options_json, enqueued_at_ms, queue_state"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')",
                    (
                        before.account_id,
                        before.owner_user_id,
                        before.operation_id,
                        before.kind,
                        before.intent_hash,
                        canonical_options_json,
                        now_ms,
                    ),
                )
                cur = con.execute(
                    "UPDATE paid_operations SET state = 'queued', version = version + 1, "
                    "updated_at_ms = ?, consent_claimed_at_ms = ? "
                    "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ? "
                    "AND version = ? AND state = 'consent_issued'",
                    (
                        now_ms,
                        now_ms,
                        before.operation_id,
                        before.owner_user_id,
                        before.account_id,
                        before.version,
                    ),
                )
                if cur.rowcount != 1:
                    raise OperationConflict("paid operation CAS precondition failed")
                snapshot = self._get_owned_in_tx(con, subject, operation_id)
                queue = self._get_queue_in_tx(con, subject, operation_id)
                if snapshot is None or queue is None:  # pragma: no cover - writes just succeeded.
                    raise PaidOperationCorruptionError("claim did not persist atomically")
                _validate_snapshot(snapshot)
                _validate_queue(queue, snapshot)
                con.execute("COMMIT")
                return snapshot, queue
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def get_queue(self, subject: Subject, operation_id: str) -> QueueSnapshot | None:
        with self._connect() as con:
            snapshot = self._get_owned_in_tx(con, subject, operation_id)
            queue = self._get_queue_in_tx(con, subject, operation_id)
            if snapshot is not None:
                _validate_snapshot(snapshot)
            if queue is not None:
                if snapshot is None:
                    raise PaidOperationCorruptionError("queue row is missing authority")
                _validate_queue(queue, snapshot)
            return queue

    def validate_startup(self) -> None:
        with self._connect() as con:
            con.execute("BEGIN")
            try:
                snapshots = [
                    _snapshot(row)
                    for row in con.execute(
                        f"SELECT {', '.join(_SNAPSHOT_COLUMNS)} FROM paid_operations"
                    )
                ]
                queues = [
                    _queue(row)
                    for row in con.execute(
                        f"SELECT {', '.join(_QUEUE_COLUMNS)} FROM paid_operation_queue"
                    )
                ]
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        by_key = {(s.account_id, s.owner_user_id, s.operation_id): s for s in snapshots}
        if len(by_key) != len(snapshots):
            raise PaidOperationCorruptionError("duplicate authority identity")
        queues_by_key: dict[tuple[str, str, str], QueueSnapshot] = {}
        for queue in queues:
            key = (queue.account_id, queue.owner_user_id, queue.operation_id)
            if key in queues_by_key:
                raise PaidOperationCorruptionError("duplicate queue identity")
            queues_by_key[key] = queue
        for key, queue in queues_by_key.items():
            snapshot = by_key.get(key)
            if snapshot is None:
                raise PaidOperationCorruptionError("queue row is missing authority")
            _validate_queue(queue, snapshot)
        for key, snapshot in by_key.items():
            _validate_snapshot(snapshot)
            maybe_queue = queues_by_key.get(key)
            if snapshot.state == "consent_issued":
                if maybe_queue is not None:
                    raise PaidOperationCorruptionError("unclaimed consent has queue row")
                if snapshot.consent_claimed_at_ms is not None:
                    raise PaidOperationCorruptionError("claimed consent is missing queue row")
            elif snapshot.state != "intent_created":
                if maybe_queue is None:
                    raise PaidOperationCorruptionError("post-consent operation is missing queue row")

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.executescript(_MIGRATION.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(
            self._db_path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
        return con

    def _get_owned_in_tx(
        self,
        con: sqlite3.Connection,
        subject: Subject,
        operation_id: str,
    ) -> OperationSnapshot | None:
        row = con.execute(
            f"SELECT {', '.join(_SNAPSHOT_COLUMNS)} FROM paid_operations "
            "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ?",
            (operation_id, subject.owner_user_id, subject.account_id),
        ).fetchone()
        return None if row is None else _snapshot(row)

    def _get_queue_in_tx(
        self,
        con: sqlite3.Connection,
        subject: Subject,
        operation_id: str,
    ) -> QueueSnapshot | None:
        row = con.execute(
            f"SELECT {', '.join(_QUEUE_COLUMNS)} FROM paid_operation_queue "
            "WHERE operation_id = ? AND owner_user_id = ? AND account_id = ?",
            (operation_id, subject.owner_user_id, subject.account_id),
        ).fetchone()
        return None if row is None else _queue(row)


def _raise_not_found() -> OperationSnapshot:
    raise OperationConflict("paid operation is unavailable")


def _snapshot(row: sqlite3.Row | tuple[Any, ...]) -> OperationSnapshot:
    values = dict(zip(_SNAPSHOT_COLUMNS, row, strict=True))
    canonical = values["canonical_intent_json"]
    if isinstance(canonical, bytes):
        if len(canonical) > MAX_CANONICAL_INTENT_BYTES:
            raise OperationStateError("canonical intent bytes exceed durable limit")
        values["canonical_intent_json"] = canonical.decode("utf-8")
    elif not isinstance(canonical, str):
        raise OperationStateError("canonical intent bytes are malformed")
    elif len(canonical.encode("utf-8")) > MAX_CANONICAL_INTENT_BYTES:
        raise OperationStateError("canonical intent bytes exceed durable limit")
    return OperationSnapshot(**values)


def _queue(row: sqlite3.Row | tuple[Any, ...]) -> QueueSnapshot:
    values = dict(zip(_QUEUE_COLUMNS, row, strict=True))
    options = values["canonical_options_json"]
    if isinstance(options, bytes):
        if len(options) > MAX_CANONICAL_INTENT_BYTES:
            raise PaidOperationCorruptionError("canonical options bytes exceed durable limit")
        values["canonical_options_json"] = options.decode("utf-8")
    elif not isinstance(options, str):
        raise PaidOperationCorruptionError("canonical options bytes are malformed")
    elif len(options.encode("utf-8")) > MAX_CANONICAL_INTENT_BYTES:
        raise PaidOperationCorruptionError("canonical options bytes exceed durable limit")
    return QueueSnapshot(**values)


def _validate_queue(queue: QueueSnapshot, snapshot: OperationSnapshot) -> None:
    if queue.queue_state != "queued":
        raise PaidOperationCorruptionError("queue row has invalid state")
    for name, value in (
        ("operation_id", queue.operation_id),
        ("owner_user_id", queue.owner_user_id),
        ("account_id", queue.account_id),
        ("operation_kind", queue.operation_kind),
    ):
        _identifier(name, value)
    _hash("intent_hash", queue.intent_hash)
    _required_int("enqueued_at_ms", queue.enqueued_at_ms)
    if (
        queue.operation_id != snapshot.operation_id
        or queue.owner_user_id != snapshot.owner_user_id
        or queue.account_id != snapshot.account_id
        or queue.operation_kind != snapshot.kind
        or queue.intent_hash != snapshot.intent_hash
    ):
        raise PaidOperationCorruptionError("queue row conflicts with authority")
    if queue.enqueued_at_ms < snapshot.created_at_ms:
        raise PaidOperationCorruptionError("queue predates authority")
    try:
        decoded = json.loads(queue.canonical_options_json)
    except json.JSONDecodeError as exc:
        raise PaidOperationCorruptionError("canonical options JSON is malformed") from exc
    if not isinstance(decoded, dict):
        raise PaidOperationCorruptionError("canonical options JSON is not an object")
    try:
        _validate_queue_option_value(decoded, path="$")
        canonical = json.dumps(
            decoded,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PaidOperationCorruptionError("canonical options JSON is unstable") from exc
    if canonical != queue.canonical_options_json:
        raise PaidOperationCorruptionError("canonical options bytes are noncanonical")


def _validate_queue_option_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, float):
        raise ValueError(f"{path} has unstable value")
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{path} integer out of range")
        return
    if isinstance(value, str):
        if not value or unicodedata.normalize("NFC", value) != value:
            raise ValueError(f"{path} string is noncanonical")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_queue_option_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key or unicodedata.normalize("NFC", key) != key:
                raise ValueError(f"{path} key is noncanonical")
            _validate_queue_option_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} has unsupported value")


def _validate_snapshot(snapshot: OperationSnapshot) -> None:
    _state(snapshot.state)
    _identifier("operation_id", snapshot.operation_id)
    _identifier("owner_user_id", snapshot.owner_user_id)
    _identifier("account_id", snapshot.account_id)
    _identifier("kind", snapshot.kind)
    _hash("intent_hash", snapshot.intent_hash)
    quote_cents = _required_int("quote_cents", snapshot.quote_cents)
    ceiling_cents = _required_int("ceiling_cents", snapshot.ceiling_cents)
    version = _required_int("version", snapshot.version)
    created_at_ms = _required_int("created_at_ms", snapshot.created_at_ms)
    updated_at_ms = _required_int("updated_at_ms", snapshot.updated_at_ms)
    expires_at_ms = _required_int("expires_at_ms", snapshot.expires_at_ms)
    if quote_cents > ceiling_cents:
        raise OperationStateError("quote exceeds ceiling")
    if updated_at_ms < created_at_ms:
        raise OperationStateError("updated_at_ms predates created_at_ms")
    if expires_at_ms <= created_at_ms:
        raise OperationStateError("expires_at_ms must be after created_at_ms")
    if version < 0:  # pragma: no cover - _required_int already rejects.
        raise OperationStateError("version is malformed")
    _validate_nullable_columns(snapshot)
    _validate_state_coherence(snapshot)
    try:
        decoded = json.loads(snapshot.canonical_intent_json)
    except json.JSONDecodeError as exc:
        raise OperationStateError("canonical intent JSON is malformed") from exc
    if not isinstance(decoded, dict):
        raise OperationStateError("canonical intent JSON is not an object")
    expected = canonicalize_intent(
        owner_user_id=snapshot.owner_user_id,
        account_id=snapshot.account_id,
        operation_id=snapshot.operation_id,
        kind=snapshot.kind,
        payload={
            k: v
            for k, v in decoded.items()
            if k not in {"owner_user_id", "account_id", "operation_id", "kind"}
        },
    )
    if (
        expected.intent_hash != snapshot.intent_hash
        or expected.canonical_json != snapshot.canonical_intent_json
        or expected.quote_cents != snapshot.quote_cents
        or expected.ceiling_cents != snapshot.ceiling_cents
    ):
        raise OperationStateError("persisted canonical intent conflicts with row columns")


def _validate_nullable_columns(snapshot: OperationSnapshot) -> None:
    _optional_hash("consent_token_hash", snapshot.consent_token_hash)
    _optional_identifier("consent_key_id", snapshot.consent_key_id)
    _optional_int("consent_issued_at_ms", snapshot.consent_issued_at_ms)
    _optional_int("consent_expires_at_ms", snapshot.consent_expires_at_ms)
    _optional_int("consent_claimed_at_ms", snapshot.consent_claimed_at_ms)
    _optional_identifier("lease_worker_id", snapshot.lease_worker_id)
    _optional_int("lease_generation", snapshot.lease_generation)
    _optional_int("lease_expires_at_ms", snapshot.lease_expires_at_ms)
    _optional_identifier("terminal_code", snapshot.terminal_code)
    _optional_text("terminal_reason", snapshot.terminal_reason)
    _optional_identifier("reconciliation_status", snapshot.reconciliation_status)
    _optional_hash("result_checkpoint_hash", snapshot.result_checkpoint_hash)
    _optional_int("settled_cents", snapshot.settled_cents)


def _validate_state_coherence(snapshot: OperationSnapshot) -> None:
    consent_fields = (
        snapshot.consent_token_hash,
        snapshot.consent_key_id,
        snapshot.consent_issued_at_ms,
        snapshot.consent_expires_at_ms,
    )
    if snapshot.state == "intent_created" and any(value is not None for value in consent_fields):
        raise OperationStateError("intent_created cannot carry consent metadata")
    if snapshot.state != "intent_created":
        if any(value is None for value in consent_fields):
            raise OperationStateError("post-intent state requires consent metadata")
        if snapshot.consent_issued_at_ms is not None and snapshot.consent_issued_at_ms < snapshot.created_at_ms:
            raise OperationStateError("consent issued before creation")
        if (
            snapshot.consent_expires_at_ms is not None
            and snapshot.consent_issued_at_ms is not None
            and snapshot.consent_expires_at_ms <= snapshot.consent_issued_at_ms
        ):
            raise OperationStateError("consent expires before issuance")
    if (
        snapshot.consent_claimed_at_ms is not None
        and snapshot.consent_issued_at_ms is not None
        and snapshot.consent_claimed_at_ms < snapshot.consent_issued_at_ms
    ):
        raise OperationStateError("consent claimed before issuance")
    if snapshot.lease_expires_at_ms is not None and snapshot.lease_generation is None:
        raise OperationStateError("lease expiry requires lease generation")
    terminal_fields = (
        snapshot.terminal_code,
        snapshot.terminal_reason,
        snapshot.result_checkpoint_hash,
        snapshot.settled_cents,
    )
    if snapshot.state not in {"complete", "failed", "budget_halted", "timed_out", "failed_reconcile"} and any(
        value is not None for value in terminal_fields
    ):
        raise OperationStateError("nonterminal state cannot carry terminal metadata")


def _validate_patch(
    before: OperationSnapshot,
    allowed_from: Sequence[str],
    to_state: str,
    patch: Mapping[str, Any],
) -> None:
    unknown = set(patch) - (_PATCH_COLUMNS | _FUTURE_AUTHORITY_PATCH_COLUMNS)
    if unknown:
        raise ValueError(f"unknown patch columns: {sorted(unknown)}")
    if "updated_at_ms" not in patch:
        raise ValueError("updated_at_ms is required")
    updated_at_ms = _required_int("updated_at_ms", patch["updated_at_ms"])
    if updated_at_ms < before.updated_at_ms:
        raise ValueError("updated_at_ms must be monotonic")
    permitted = set(_PATCH_COLUMNS)
    for state in allowed_from:
        permitted |= set(_TRANSITION_PATCH_COLUMNS.get((state, to_state), frozenset()))
    forbidden = set(patch) - permitted
    if forbidden:
        raise OperationStateError(f"patch columns forbidden for transition: {sorted(forbidden)}")
    for key, value in patch.items():
        if key.endswith("_ms") or key in {"lease_generation", "settled_cents"}:
            _optional_int(key, value)
        elif key in {"consent_token_hash", "result_checkpoint_hash"}:
            _optional_hash(key, value)
        elif key == "terminal_reason":
            _optional_text(key, value)
        else:
            _optional_identifier(key, value)
    if to_state == "consent_issued":
        for key in (
            "consent_token_hash",
            "consent_key_id",
            "consent_issued_at_ms",
            "consent_expires_at_ms",
        ):
            if patch.get(key) is None:
                raise ValueError(f"{key} is required for consent issuance")
        if patch["consent_issued_at_ms"] < before.created_at_ms:
            raise ValueError("consent_issued_at_ms must not predate creation")
        if patch["consent_expires_at_ms"] <= patch["consent_issued_at_ms"]:
            raise ValueError("consent_expires_at_ms must follow consent_issued_at_ms")
    if to_state == "queued":
        if patch.get("consent_claimed_at_ms") is None:
            raise ValueError("consent_claimed_at_ms is required for queueing")
        if before.consent_issued_at_ms is not None and patch["consent_claimed_at_ms"] < before.consent_issued_at_ms:
            raise ValueError("consent_claimed_at_ms must not predate issuance")


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))


def _required_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OperationStateError(f"{name} must be an exact integer")
    if value < 0 or value > _MAX_SQLITE_INT:
        raise OperationStateError(f"{name} integer out of range")
    return value


def _optional_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    return _required_int(name, value)


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise OperationStateError(f"{name} must be a non-empty string")
    if unicodedata.normalize("NFC", value) != value:
        raise OperationStateError(f"{name} must be NFC-normalized")
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise OperationStateError(f"{name} is too long")
    return value


def _optional_text(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _text(name, value)


def _identifier(name: str, value: object) -> str:
    text = _text(name, value)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise OperationStateError(f"{name} must be a lowercase canonical identifier")
    return text


def _optional_identifier(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _identifier(name, value)


def _hash(name: str, value: object) -> str:
    text = _text(name, value)
    if not _HASH_RE.fullmatch(text):
        raise OperationStateError(f"{name} must be a lowercase sha256 hex digest")
    return text


def _optional_hash(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _hash(name, value)


def _state(value: str) -> str:
    if value not in _STATES:
        raise OperationStateError(f"unknown paid operation state {value!r}")
    return value


__all__ = [
    "OperationConflict",
    "OperationSnapshot",
    "OperationStateError",
    "PaidOperationCorruptionError",
    "PaidOperationStore",
    "QueueSnapshot",
    "Subject",
]

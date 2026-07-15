"""SQLite owner-bound paid-operation authority store."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from substrate.paid_operations.contracts import MAX_CANONICAL_INTENT_BYTES, canonicalize_intent

_MIGRATION = Path(__file__).with_name("migrations") / "001_authority.sql"
_MAX_SQLITE_INT = 9_223_372_036_854_775_807
_MAX_TEXT_BYTES = 4096
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9_][a-z0-9._:-]{0,191}$")
_IDEMPOTENCY_DOMAIN = b"antiek.paid-operation.dispatch.v1\0"
_MOVEMENT_KEY_DOMAIN = b"antiek.paid-operation.movement.v1\0"
_CHECKPOINT_DOMAIN = b"antiek.paid-operation.checkpoint.v1\0"

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
        "external_charged_cents",
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
    "external_charged_cents",
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
    external_charged_cents: int | None = None

    @property
    def external_overage_cents(self) -> int | None:
        if self.external_charged_cents is None or self.settled_cents is None:
            return None
        return self.external_charged_cents - self.settled_cents


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
                ledger_rows = con.execute(
                    "SELECT movement_key, account_id, owner_user_id, operation_id, period_id, intent_hash, "
                    "step_id, movement_type, cents, lease_worker_id, lease_generation, "
                    "expected_operation_version, operation_version, prior_movement_key "
                    "FROM paid_operation_ledger"
                ).fetchall()
                budget_rows = con.execute(
                    "SELECT account_id, period_id, limit_cents, reserved_cents, settled_cents "
                    "FROM paid_account_budgets"
                ).fetchall()
                checkpoint_rows = con.execute(
                    "SELECT account_id, owner_user_id, operation_id, step_id, intent_hash, "
                    "lease_worker_id, lease_generation, expected_operation_version, operation_version, "
                    "provider_id, endpoint_id, idempotency_key, response_body_hash, response_body_json, "
                    "provider_receipt, "
                    "observed_cost_cents, checkpoint_material_hash, created_at_ms "
                    "FROM paid_operation_checkpoints"
                ).fetchall()
                audit_rows = con.execute(
                    "SELECT command_id, account_id, owner_user_id, operation_id, operator_user_id, "
                    "operation_version, evidence_hash, decision, reason, charged_cents, "
                    "authorized_settled_cents, step_id, "
                    "movement_key, created_at_ms FROM paid_operation_reconciliation_audit"
                ).fetchall()
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
            if snapshot.state == "running" and (
                snapshot.lease_worker_id is None
                or snapshot.lease_generation is None
                or snapshot.lease_expires_at_ms is None
            ):
                raise PaidOperationCorruptionError("running operation is missing lease generation")
        _validate_dispatch_invariants(by_key, queues_by_key, ledger_rows, budget_rows, checkpoint_rows, audit_rows)

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.executescript(_MIGRATION.read_text(encoding="utf-8"))
            checkpoint_columns = {
                row[1] for row in con.execute("PRAGMA table_info(paid_operation_checkpoints)")
            }
            if "response_body_json" not in checkpoint_columns:
                con.execute("ALTER TABLE paid_operation_checkpoints ADD COLUMN response_body_json TEXT")
            operation_columns = {row[1] for row in con.execute("PRAGMA table_info(paid_operations)")}
            if "external_charged_cents" not in operation_columns:
                con.execute(
                    "ALTER TABLE paid_operations ADD COLUMN external_charged_cents INTEGER "
                    "CHECK (external_charged_cents IS NULL OR "
                    "(typeof(external_charged_cents) = 'integer' AND external_charged_cents >= 0))"
                )
            audit_columns = {
                row[1] for row in con.execute("PRAGMA table_info(paid_operation_reconciliation_audit)")
            }
            if "authorized_settled_cents" not in audit_columns:
                con.execute(
                    "ALTER TABLE paid_operation_reconciliation_audit "
                    "ADD COLUMN authorized_settled_cents INTEGER NOT NULL DEFAULT 0 "
                    "CHECK (typeof(authorized_settled_cents) = 'integer' "
                    "AND authorized_settled_cents >= 0 "
                    "AND authorized_settled_cents <= charged_cents)"
                )
                con.execute(
                    "UPDATE paid_operation_reconciliation_audit "
                    "SET authorized_settled_cents = CASE WHEN decision = 'confirm_charged' THEN ("
                    "SELECT cents FROM paid_operation_ledger "
                    "WHERE movement_key = paid_operation_reconciliation_audit.movement_key"
                    ") ELSE 0 END"
                )
                con.execute(
                    "UPDATE paid_operations SET external_charged_cents = ("
                    "SELECT charged_cents FROM paid_operation_reconciliation_audit audit "
                    "WHERE audit.account_id = paid_operations.account_id "
                    "AND audit.owner_user_id = paid_operations.owner_user_id "
                    "AND audit.operation_id = paid_operations.operation_id"
                    ") WHERE reconciliation_status = 'resolved'"
                )

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        con = sqlite3.connect(
            self._db_path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
        return closing(con)

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


def _validate_dispatch_invariants(
    snapshots: Mapping[tuple[str, str, str], OperationSnapshot],
    queues: Mapping[tuple[str, str, str], QueueSnapshot],
    ledger_rows: Sequence[sqlite3.Row | tuple[Any, ...]],
    budget_rows: Sequence[sqlite3.Row | tuple[Any, ...]],
    checkpoint_rows: Sequence[sqlite3.Row | tuple[Any, ...]],
    audit_rows: Sequence[sqlite3.Row | tuple[Any, ...]],
) -> None:
    movements: dict[str, dict[str, Any]] = {}
    checkpoints: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    account_reserved: dict[str, int] = {}
    account_settled: dict[str, int] = {}
    cumulative_reserved_by_operation: dict[tuple[str, str, str], int] = {}
    unresolved_by_operation: dict[tuple[str, str, str], int] = {}
    retain_count_by_operation: dict[tuple[str, str, str], int] = {}
    budget_account_ids: set[str] = set()
    current_period_by_account: dict[str, str] = {}
    checked_budgets: list[tuple[str, int, int, int]] = []
    for row in budget_rows:
        account_id = _identifier("account_id", row[0])
        if account_id in budget_account_ids:
            raise PaidOperationCorruptionError("duplicate account budget")
        period_id = _identifier("period_id", row[1])
        limit = _required_int("limit_cents", row[2])
        reserved = _required_int("reserved_cents", row[3])
        settled = _required_int("settled_cents", row[4])
        budget_account_ids.add(account_id)
        current_period_by_account[account_id] = period_id
        checked_budgets.append((account_id, limit, reserved, settled))
    movement_account_ids: set[str] = set()
    operation_versions: dict[tuple[str, str, str], set[int]] = {}
    for row in ledger_rows:
        movement_key = _identifier("movement_key", row[0])
        if movement_key in movements:
            raise PaidOperationCorruptionError("duplicate logical movement")
        key = (_identifier("account_id", row[1]), _identifier("owner_user_id", row[2]), _identifier("operation_id", row[3]))
        movement_account_ids.add(key[0])
        snapshot = snapshots.get(key)
        if snapshot is None:
            raise PaidOperationCorruptionError("ledger movement is missing authority")
        period_id = _identifier("period_id", row[4])
        intent_hash = _hash("intent_hash", row[5])
        step_id = _identifier("step_id", row[6])
        movement_type = _identifier("movement_type", row[7])
        cents = _required_int("cents", row[8])
        lease_worker_id = _identifier("lease_worker_id", row[9])
        lease_generation = _required_int("lease_generation", row[10])
        expected_version = _required_int("expected_operation_version", row[11])
        operation_version = _required_int("operation_version", row[12])
        prior = None if row[13] is None else _identifier("prior_movement_key", row[13])
        if movement_type not in {"reserve", "settle", "release", "retain", "reconcile"}:
            raise PaidOperationCorruptionError("ledger movement type is invalid")
        if intent_hash != snapshot.intent_hash:
            raise PaidOperationCorruptionError("ledger movement intent conflicts with authority")
        if movement_key != _logical_movement_key(*key, step_id, movement_type):
            raise PaidOperationCorruptionError("ledger movement key conflicts with material")
        if lease_generation <= 0 or snapshot.lease_generation is None or lease_generation > snapshot.lease_generation:
            raise PaidOperationCorruptionError("ledger movement lease generation conflicts with authority")
        if lease_generation == snapshot.lease_generation and lease_worker_id != snapshot.lease_worker_id:
            raise PaidOperationCorruptionError("ledger movement lease owner conflicts with authority")
        if operation_version != expected_version + 1 or operation_version > snapshot.version:
            raise PaidOperationCorruptionError("ledger movement operation version is incoherent")
        versions = operation_versions.setdefault(key, set())
        if operation_version in versions:
            raise PaidOperationCorruptionError("duplicate operation mutation version")
        versions.add(operation_version)
        movements[movement_key] = {
            "key": key,
            "movement_key": movement_key,
            "account_id": key[0],
            "period_id": period_id,
            "intent_hash": intent_hash,
            "step_id": step_id,
            "type": movement_type,
            "cents": cents,
            "worker_id": lease_worker_id,
            "generation": lease_generation,
            "expected_version": expected_version,
            "operation_version": operation_version,
            "prior": prior,
        }
    resolved_by_reserve: dict[str, int] = {}
    retained_by_reserve: dict[str, int] = {}
    for movement in movements.values():
        account_id = movement["account_id"]
        current_period = current_period_by_account.get(account_id)
        movement_type = movement["type"]
        cents = movement["cents"]
        is_current_period = current_period is not None and movement["period_id"] == current_period
        if movement_type == "reserve":
            key = movement["key"]
            cumulative_reserved_by_operation[key] = cumulative_reserved_by_operation.get(key, 0) + cents
            if is_current_period:
                account_reserved[account_id] = account_reserved.get(account_id, 0) + cents
            continue
        prior = movement["prior"]
        reserve = movements.get(prior)
        if reserve is None or reserve["type"] != "reserve" or reserve["key"] != movement["key"]:
            raise PaidOperationCorruptionError("ledger resolution is missing reserve")
        if movement["period_id"] != reserve["period_id"] or movement["step_id"] != reserve["step_id"]:
            raise PaidOperationCorruptionError("ledger resolution material conflicts with reserve")
        if movement["operation_version"] <= reserve["operation_version"]:
            raise PaidOperationCorruptionError("ledger resolution version predates reserve")
        if movement_type == "retain" and cents != 0:
            raise PaidOperationCorruptionError("retain movement must carry zero cents")
        if movement_type in {"settle", "release", "reconcile"}:
            resolved_by_reserve[prior] = resolved_by_reserve.get(prior, 0) + cents
            if is_current_period:
                account_reserved[account_id] = account_reserved.get(account_id, 0) - cents
            if movement_type in {"settle", "reconcile"} and is_current_period:
                account_settled[account_id] = account_settled.get(account_id, 0) + cents
        elif movement_type == "retain":
            retained_by_reserve[prior] = retained_by_reserve.get(prior, 0) + 1
    for reserve_key, reserve in movements.items():
        if reserve["type"] != "reserve":
            continue
        unresolved = reserve["cents"] - resolved_by_reserve.get(reserve_key, 0)
        if unresolved < 0:
            raise PaidOperationCorruptionError("ledger resolved more than reserved")
        if unresolved:
            current_period = current_period_by_account.get(reserve["account_id"])
            if current_period is not None and reserve["period_id"] != current_period:
                raise PaidOperationCorruptionError("unresolved reserve is outside current budget period")
            key = reserve["key"]
            unresolved_by_operation[key] = unresolved_by_operation.get(key, 0) + unresolved
            retain_count_by_operation[key] = retain_count_by_operation.get(key, 0) + retained_by_reserve.get(reserve_key, 0)
    for account_id, limit, reserved, settled in checked_budgets:
        if reserved != account_reserved.get(account_id, 0) or settled != account_settled.get(account_id, 0):
            raise PaidOperationCorruptionError("account budget aggregate drift")
        if reserved + settled > limit:
            raise PaidOperationCorruptionError("account budget exceeds limit")
    if movement_account_ids - budget_account_ids:
        raise PaidOperationCorruptionError("ledger movement is missing account budget")
    for key, cumulative_reserved in cumulative_reserved_by_operation.items():
        snapshot = snapshots[key]
        if cumulative_reserved > snapshot.ceiling_cents:
            raise PaidOperationCorruptionError("operation cumulative reserves exceed ceiling")
    for row in checkpoint_rows:
        key = (_identifier("account_id", row[0]), _identifier("owner_user_id", row[1]), _identifier("operation_id", row[2]))
        step_id = _identifier("step_id", row[3])
        checkpoint_key = (*key, step_id)
        if checkpoint_key in checkpoints:
            raise PaidOperationCorruptionError("duplicate step checkpoint")
        snapshot = snapshots.get(key)
        if snapshot is None or key not in queues:
            raise PaidOperationCorruptionError("checkpoint is missing queue authority")
        intent_hash = _hash("intent_hash", row[4])
        if intent_hash != snapshot.intent_hash:
            raise PaidOperationCorruptionError("checkpoint intent conflicts with authority")
        lease_worker_id = _identifier("lease_worker_id", row[5])
        lease_generation = _required_int("lease_generation", row[6])
        expected_version = _required_int("expected_operation_version", row[7])
        operation_version = _required_int("operation_version", row[8])
        provider_id = _identifier("provider_id", row[9])
        endpoint_id = _identifier("endpoint_id", row[10])
        intent_provider_id, intent_route_id = _intent_provider_route(snapshot)
        if provider_id != intent_provider_id or endpoint_id != intent_route_id:
            raise PaidOperationCorruptionError("checkpoint provider route conflicts with immutable intent")
        idempotency_key = _hash("idempotency_key", row[11])
        response_body_hash = _hash("response_body_hash", row[12])
        response_body_json = _text("response_body_json", row[13])
        if len(response_body_json.encode("utf-8")) > MAX_CANONICAL_INTENT_BYTES:
            raise PaidOperationCorruptionError("response_body_json exceeds durable limit")
        try:
            decoded_response = json.loads(response_body_json)
        except json.JSONDecodeError as exc:
            raise PaidOperationCorruptionError("checkpoint response body is malformed") from exc
        if not isinstance(decoded_response, dict):
            raise PaidOperationCorruptionError("checkpoint response body is not an object")
        try:
            canonical_response = json.dumps(
                decoded_response,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise PaidOperationCorruptionError("checkpoint response body is unstable") from exc
        if canonical_response != response_body_json:
            raise PaidOperationCorruptionError("checkpoint response body is noncanonical")
        if hashlib.sha256(response_body_json.encode("utf-8")).hexdigest() != response_body_hash:
            raise PaidOperationCorruptionError("checkpoint response body hash conflicts")
        provider_receipt = _text("provider_receipt", row[14])
        if len(provider_receipt.encode("utf-8")) > _MAX_TEXT_BYTES:
            raise PaidOperationCorruptionError("provider_receipt exceeds durable limit")
        observed_cost = _required_int("observed_cost_cents", row[15])
        checkpoint_material_hash = _hash("checkpoint_material_hash", row[16])
        _required_int("checkpoint created_at_ms", row[17])
        if idempotency_key != _stable_idempotency_key(*key, step_id, intent_hash):
            raise PaidOperationCorruptionError("checkpoint idempotency material conflicts")
        if lease_generation <= 0 or snapshot.lease_generation is None or lease_generation > snapshot.lease_generation:
            raise PaidOperationCorruptionError("checkpoint lease generation conflicts with authority")
        if lease_generation == snapshot.lease_generation and lease_worker_id != snapshot.lease_worker_id:
            raise PaidOperationCorruptionError("checkpoint lease owner conflicts with authority")
        if operation_version != expected_version + 1 or operation_version > snapshot.version:
            raise PaidOperationCorruptionError("checkpoint operation version is incoherent")
        expected_material_hash = _checkpoint_material_hash(
            key,
            step_id,
            intent_hash,
            lease_worker_id,
            lease_generation,
            expected_version,
            operation_version,
            provider_id,
            endpoint_id,
            idempotency_key,
            response_body_hash,
            provider_receipt,
            observed_cost,
        )
        if checkpoint_material_hash != expected_material_hash:
            raise PaidOperationCorruptionError("checkpoint provider material hash conflicts")
        versions = operation_versions.setdefault(key, set())
        if operation_version in versions:
            raise PaidOperationCorruptionError("duplicate operation mutation version")
        versions.add(operation_version)
        reserve_key = _logical_movement_key(*key, step_id, "reserve")
        reserve = movements.get(reserve_key)
        if reserve is None or reserve["type"] != "reserve":
            raise PaidOperationCorruptionError("checkpoint is missing reserve")
        if (
            reserve["generation"] > lease_generation
            or (
                reserve["generation"] == lease_generation
                and reserve["worker_id"] != lease_worker_id
            )
            or reserve["intent_hash"] != intent_hash
            or expected_version < reserve["operation_version"]
        ):
            raise PaidOperationCorruptionError("checkpoint lease material conflicts with reserve")
        over_reserve = observed_cost > reserve["cents"]
        coherently_quarantined = (
            snapshot.state == "failed_reconcile"
            and snapshot.terminal_reason == "settled_cost_exceeds_reserve"
            and snapshot.result_checkpoint_hash == response_body_hash
        )
        coherently_resolved = (
            snapshot.state == "complete"
            and snapshot.reconciliation_status == "resolved"
            and snapshot.terminal_code in {"reconciled_charged", "reconciled_not_charged"}
            and snapshot.result_checkpoint_hash == response_body_hash
        )
        if (
            over_reserve
            and snapshot.state != "running"
            and not coherently_quarantined
            and not coherently_resolved
        ):
            raise PaidOperationCorruptionError("over-reserve checkpoint is not coherently quarantined")
        checkpoints[checkpoint_key] = {
            "key": key,
            "step_id": step_id,
            "provider_id": provider_id,
            "endpoint_id": endpoint_id,
            "response_body_hash": response_body_hash,
            "observed_cost": observed_cost,
            "reserve": reserve,
            "over_reserve": over_reserve,
        }
    for checkpoint in checkpoints.values():
        checkpoint_identity: tuple[str, str, str] = checkpoint["key"]
        step_id = checkpoint["step_id"]
        reserve = checkpoint["reserve"]
        settle = movements.get(_logical_movement_key(*checkpoint_identity, step_id, "settle"))
        release = movements.get(_logical_movement_key(*checkpoint_identity, step_id, "release"))
        expected_release = reserve["cents"] - checkpoint["observed_cost"]
        if checkpoint["over_reserve"]:
            if settle is not None:
                raise PaidOperationCorruptionError("over-reserve checkpoint cannot settle before reconciliation")
        else:
            if settle is not None and settle["cents"] != checkpoint["observed_cost"]:
                raise PaidOperationCorruptionError("checkpoint settlement conflicts with observed cost")
            if release is not None and release["cents"] != expected_release:
                raise PaidOperationCorruptionError("checkpoint release conflicts with reserve")
            if release is not None and settle is None:
                raise PaidOperationCorruptionError("checkpoint release is missing settlement")
        snapshot = snapshots[checkpoint_identity]
        if snapshot.state == "complete" and snapshot.terminal_code == "complete":
            if settle is None or (expected_release and release is None):
                raise PaidOperationCorruptionError("provider terminal ledger is incomplete")
            if snapshot.result_checkpoint_hash != checkpoint["response_body_hash"]:
                raise PaidOperationCorruptionError("terminal result checkpoint hash conflicts")
            if snapshot.settled_cents != checkpoint["observed_cost"]:
                raise PaidOperationCorruptionError("terminal settled cost conflicts with checkpoint")
    for movement in movements.values():
        movement_identity: tuple[str, str, str] = movement["key"]
        if movement["type"] == "settle" and (*movement_identity, movement["step_id"]) not in checkpoints:
            raise PaidOperationCorruptionError("settlement is missing checkpoint")
        if movement["type"] == "release" and (*movement_identity, movement["step_id"]) not in checkpoints:
            reserve = movements.get(movement["prior"])
            retain_key = _logical_movement_key(*movement_identity, movement["step_id"], "retain")
            if reserve is None or retain_key not in movements:
                raise PaidOperationCorruptionError("release is missing checkpoint or reconciliation hold")
        if movement["type"] == "reconcile":
            retain_key = _logical_movement_key(*movement_identity, movement["step_id"], "retain")
            if retain_key not in movements:
                raise PaidOperationCorruptionError("reconciliation movement is missing retained hold")
        if movement["type"] == "retain":
            retained_checkpoint = checkpoints.get((*movement_identity, movement["step_id"]))
            if retained_checkpoint is not None and not retained_checkpoint["over_reserve"]:
                raise PaidOperationCorruptionError("definite in-reserve result cannot carry unknown-outcome hold")
    _validate_reconciliation_audits(snapshots, movements, checkpoints, audit_rows)
    for key, snapshot in snapshots.items():
        unresolved = unresolved_by_operation.get(key, 0)
        retain_count = retain_count_by_operation.get(key, 0)
        if snapshot.state == "failed_reconcile":
            if unresolved <= 0 or retain_count != 1:
                raise PaidOperationCorruptionError("failed_reconcile requires exactly one retained unresolved reserve")
        elif snapshot.state in {"complete", "failed", "budget_halted", "timed_out"} and unresolved:
            raise PaidOperationCorruptionError("terminal operation has unresolved reserve")
        if snapshot.state == "complete" and snapshot.terminal_code == "complete":
            matching = [checkpoint for checkpoint in checkpoints.values() if checkpoint["key"] == key]
            if len(matching) != 1:
                raise PaidOperationCorruptionError("provider terminal requires exactly one checkpoint")
        elif snapshot.state == "failed_reconcile" and snapshot.result_checkpoint_hash is not None:
            matching = [checkpoint for checkpoint in checkpoints.values() if checkpoint["key"] == key]
            if (
                len(matching) != 1
                or not matching[0]["over_reserve"]
                or matching[0]["response_body_hash"] != snapshot.result_checkpoint_hash
            ):
                raise PaidOperationCorruptionError("quarantined result checkpoint hash conflicts")
        elif (
            snapshot.state == "complete"
            and snapshot.reconciliation_status == "resolved"
            and snapshot.result_checkpoint_hash is not None
        ):
            matching = [checkpoint for checkpoint in checkpoints.values() if checkpoint["key"] == key]
            if (
                len(matching) != 1
                or not matching[0]["over_reserve"]
                or matching[0]["response_body_hash"] != snapshot.result_checkpoint_hash
            ):
                raise PaidOperationCorruptionError("reconciled result checkpoint hash conflicts")
        elif snapshot.result_checkpoint_hash is not None:
            raise PaidOperationCorruptionError("non-provider terminal carries result checkpoint hash")


def _validate_reconciliation_audits(
    snapshots: Mapping[tuple[str, str, str], OperationSnapshot],
    movements: Mapping[str, Mapping[str, Any]],
    checkpoints: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
    audit_rows: Sequence[sqlite3.Row | tuple[Any, ...]],
) -> None:
    seen: set[tuple[str, str, str, str]] = set()
    audit_count_by_operation: dict[tuple[str, str, str], int] = {}
    audit_count_by_movement: dict[str, int] = {}
    for row in audit_rows:
        command_id = _identifier("command_id", row[0])
        key = (
            _identifier("account_id", row[1]),
            _identifier("owner_user_id", row[2]),
            _identifier("operation_id", row[3]),
        )
        audit_key = (*key, command_id)
        if audit_key in seen:
            raise PaidOperationCorruptionError("duplicate reconciliation command")
        seen.add(audit_key)
        audit_count_by_operation[key] = audit_count_by_operation.get(key, 0) + 1
        _identifier("operator_user_id", row[4])
        operation_version = _required_int("operation_version", row[5])
        _hash("evidence_hash", row[6])
        decision = _identifier("decision", row[7])
        reason = _text("reason", row[8])
        charged_cents = _required_int("charged_cents", row[9])
        authorized_settled_cents = _required_int("authorized_settled_cents", row[10])
        step_id = _identifier("step_id", row[11])
        movement_key = _identifier("movement_key", row[12])
        audit_count_by_movement[movement_key] = audit_count_by_movement.get(movement_key, 0) + 1
        _required_int("created_at_ms", row[13])
        snapshot = snapshots.get(key)
        if snapshot is None:
            raise PaidOperationCorruptionError("reconciliation audit is missing authority")
        movement = movements.get(movement_key)
        if movement is None:
            raise PaidOperationCorruptionError("reconciliation audit movement is missing")
        if movement["key"] != key:
            raise PaidOperationCorruptionError("reconciliation audit movement identity conflicts")
        reserve = movements.get(movement["prior"])
        if reserve is None or reserve["type"] != "reserve" or reserve["key"] != key:
            raise PaidOperationCorruptionError("reconciliation audit movement is missing reserve")
        if decision == "confirm_charged":
            if charged_cents <= 0:
                raise PaidOperationCorruptionError("charged reconciliation requires positive cents")
            expected_authorized = min(charged_cents, reserve["cents"])
            if authorized_settled_cents != expected_authorized:
                raise PaidOperationCorruptionError("reconciliation authorized settlement conflicts")
            if movement["type"] != "reconcile" or movement["cents"] != authorized_settled_cents:
                raise PaidOperationCorruptionError("reconciliation audit movement type conflicts")
            checkpoint = checkpoints.get((*key, step_id))
            if checkpoint is not None and charged_cents != checkpoint["observed_cost"]:
                raise PaidOperationCorruptionError("reconciliation external charge conflicts with checkpoint")
            expected_terminal_code = "reconciled_charged"
            release_key = _logical_movement_key(*key, step_id, "release")
            release = movements.get(release_key)
            expected_release = reserve["cents"] - authorized_settled_cents
            if expected_release:
                if release is None or release["cents"] != expected_release:
                    raise PaidOperationCorruptionError("reconciliation release conflicts with retained reserve")
            elif release is not None:
                raise PaidOperationCorruptionError("reconciliation has an unexpected release")
            expected_terminal_version = operation_version + (3 if expected_release else 2)
        elif decision == "confirm_not_charged":
            if charged_cents != 0 or authorized_settled_cents != 0:
                raise PaidOperationCorruptionError("not-charged reconciliation requires zero cents")
            if movement["type"] != "release":
                raise PaidOperationCorruptionError("reconciliation audit movement type conflicts")
            expected_terminal_code = "reconciled_not_charged"
            expected_terminal_version = operation_version + 2
        else:
            raise PaidOperationCorruptionError("reconciliation decision is invalid")
        if movement["step_id"] != step_id or movement["expected_version"] != operation_version:
            raise PaidOperationCorruptionError("reconciliation audit CAS material conflicts")
        if (
            snapshot.state != "complete"
            or snapshot.reconciliation_status != "resolved"
            or snapshot.terminal_code != expected_terminal_code
            or snapshot.terminal_reason != reason
            or snapshot.settled_cents != authorized_settled_cents
            or snapshot.external_charged_cents != charged_cents
            or snapshot.version != expected_terminal_version
        ):
            raise PaidOperationCorruptionError("reconciliation terminal is incoherent")
    for movement_key, movement in movements.items():
        if movement["type"] == "reconcile" and audit_count_by_movement.get(movement_key, 0) != 1:
            raise PaidOperationCorruptionError("reconciliation movement requires exactly one audit")
    for key, snapshot in snapshots.items():
        reconciled_terminal = (
            snapshot.state == "complete"
            and snapshot.reconciliation_status == "resolved"
            and snapshot.terminal_code in {"reconciled_charged", "reconciled_not_charged"}
        )
        audit_count = audit_count_by_operation.get(key, 0)
        if reconciled_terminal and audit_count != 1:
            raise PaidOperationCorruptionError("reconciled terminal requires exactly one audit")
        if not reconciled_terminal and audit_count:
            raise PaidOperationCorruptionError("reconciliation audit lacks reconciled terminal")


def _logical_movement_key(
    account_id: str,
    owner_user_id: str,
    operation_id: str,
    step_id: str,
    movement_type: str,
) -> str:
    material = json.dumps(
        {
            "account_id": account_id,
            "movement_type": movement_type,
            "operation_id": operation_id,
            "owner_user_id": owner_user_id,
            "step_id": step_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "mv:" + hashlib.sha256(_MOVEMENT_KEY_DOMAIN + material).hexdigest()


def _stable_idempotency_key(
    account_id: str,
    owner_user_id: str,
    operation_id: str,
    step_id: str,
    intent_hash: str,
) -> str:
    material = json.dumps(
        {
            "account_id": account_id,
            "intent_hash": intent_hash,
            "operation_id": operation_id,
            "owner_user_id": owner_user_id,
            "step_id": step_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(_IDEMPOTENCY_DOMAIN + material).hexdigest()


def _intent_provider_route(snapshot: OperationSnapshot) -> tuple[str, str]:
    try:
        decoded = json.loads(snapshot.canonical_intent_json)
    except json.JSONDecodeError as exc:
        raise PaidOperationCorruptionError("canonical intent JSON is malformed") from exc
    if not isinstance(decoded, dict):
        raise PaidOperationCorruptionError("canonical intent JSON is not an object")
    return (
        _identifier("intent provider_id", decoded.get("provider_id")),
        _identifier("intent route_id", decoded.get("route_id")),
    )


def _checkpoint_material_hash(
    key: tuple[str, str, str],
    step_id: str,
    intent_hash: str,
    lease_worker_id: str,
    lease_generation: int,
    expected_operation_version: int,
    operation_version: int,
    provider_id: str,
    endpoint_id: str,
    idempotency_key: str,
    response_body_hash: str,
    provider_receipt: str,
    observed_cost_cents: int,
) -> str:
    account_id, owner_user_id, operation_id = key
    material = json.dumps(
        {
            "account_id": account_id,
            "endpoint_id": endpoint_id,
            "expected_operation_version": expected_operation_version,
            "idempotency_key": idempotency_key,
            "intent_hash": intent_hash,
            "lease_generation": lease_generation,
            "lease_worker_id": lease_worker_id,
            "observed_cost_cents": observed_cost_cents,
            "operation_id": operation_id,
            "operation_version": operation_version,
            "owner_user_id": owner_user_id,
            "provider_id": provider_id,
            "provider_receipt": provider_receipt,
            "response_body_hash": response_body_hash,
            "step_id": step_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(_CHECKPOINT_DOMAIN + material).hexdigest()


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
    _optional_int("external_charged_cents", snapshot.external_charged_cents)


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
        snapshot.external_charged_cents,
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
        if key.endswith("_ms") or key in {
            "lease_generation",
            "settled_cents",
            "external_charged_cents",
        }:
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

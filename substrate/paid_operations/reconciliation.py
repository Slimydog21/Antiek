"""Operator-only reconciliation for unknown paid-provider outcomes."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Callable
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from substrate.paid_operations.ledger import (
    LeaseFence,
    Movement,
    PaidOperationLedger,
    logical_movement_key,
)
from substrate.paid_operations.store import (
    OperationConflict,
    PaidOperationCorruptionError,
    PaidOperationStore,
    Subject,
)

Decision = Literal["confirm_charged", "confirm_not_charged"]
_IDENTIFIER_RE = re.compile(r"^[a-z0-9_][a-z0-9._:-]{0,191}$")
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_MAX_SQLITE_INT = 9_223_372_036_854_775_807
_MAX_AUDIT_TEXT_BYTES = 4096


@dataclass(frozen=True)
class OperatorSubject:
    operator_user_id: str
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ReconciliationCommand:
    command_id: str
    subject: Subject
    operation_id: str
    operation_version: int
    evidence_hash: str
    decision: Decision
    reason: str
    charged_cents: int = 0
    step_id: str = "dispatch"


@dataclass(frozen=True)
class ReconciliationReceipt:
    command_id: str
    operation_id: str
    decision: Decision
    movement: Movement
    state: str
    authorized_settled_cents: int
    external_charged_cents: int

    @property
    def external_overage_cents(self) -> int:
        return self.external_charged_cents - self.authorized_settled_cents


class PaidOperationReconciler:
    def __init__(
        self,
        db_path: str | Path,
        *,
        clock_ms: Callable[[], int],
        authorize_operator: Callable[[str], bool] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._clock_ms = clock_ms
        self._authorize_operator = authorize_operator or _deny_operator
        self.ledger = PaidOperationLedger(self._db_path)
        PaidOperationStore(self._db_path)

    def reconcile(self, operator: OperatorSubject, command: ReconciliationCommand) -> ReconciliationReceipt:
        operator_user_id = _identifier("operator_user_id", operator.operator_user_id)
        if self._authorize_operator(operator_user_id) is not True:
            raise OperationConflict("operator is not authorized for reconciliation")
        _validate_command(command)
        now_ms = _exact_int("created_at_ms", self._clock_ms())
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                replay = self._audit_replay_in_tx(con, command)
                if replay is not None:
                    con.execute("COMMIT")
                    return replay
                op = con.execute(
                    "SELECT account_id, owner_user_id, operation_id, intent_hash, version, state, "
                    "lease_worker_id, lease_generation, settled_cents "
                    "FROM paid_operations WHERE account_id = ? AND owner_user_id = ? AND operation_id = ?",
                    (command.subject.account_id, command.subject.owner_user_id, command.operation_id),
                ).fetchone()
                if op is None:
                    raise OperationConflict("paid operation is unavailable")
                if op[4] != command.operation_version or op[5] != "failed_reconcile":
                    raise OperationConflict("reconciliation precondition failed")
                if op[6] is None or op[7] is None:
                    raise PaidOperationCorruptionError("failed reconciliation is missing lease fence")
                reserve_key = logical_movement_key(
                    command.subject.account_id,
                    command.subject.owner_user_id,
                    command.operation_id,
                    command.step_id,
                    "reserve",
                )
                retain = con.execute(
                    "SELECT movement_key FROM paid_operation_ledger WHERE prior_movement_key = ? "
                    "AND movement_type = 'retain' AND account_id = ? AND owner_user_id = ? AND operation_id = ?",
                    (
                        reserve_key,
                        command.subject.account_id,
                        command.subject.owner_user_id,
                        command.operation_id,
                    ),
                ).fetchall()
                if len(retain) != 1:
                    raise PaidOperationCorruptionError("failed reconciliation requires one retained reserve")
                fence = LeaseFence(
                    account_id=op[0],
                    owner_user_id=op[1],
                    operation_id=op[2],
                    intent_hash=op[3],
                    lease_worker_id=op[6],
                    lease_generation=op[7],
                    expected_operation_version=command.operation_version,
                )
                reserve = self._reserve_cents_in_tx(con, reserve_key)
                if command.decision == "confirm_charged":
                    if command.charged_cents <= 0:
                        raise OperationConflict("charged reconciliation requires positive cents")
                    self._validate_checkpoint_charge_in_tx(con, command)
                    authorized_settled = min(command.charged_cents, reserve)
                    movement = self.ledger._movement_in_tx(  # noqa: SLF001
                        con,
                        fence,
                        movement_key=logical_movement_key(
                            fence.account_id,
                            fence.owner_user_id,
                            fence.operation_id,
                            command.step_id,
                            "reconcile",
                        ),
                        step_id=command.step_id,
                        movement_type="reconcile",
                        cents=authorized_settled,
                        prior_movement_key=reserve_key,
                        now_ms=now_ms,
                        allowed_operation_states=frozenset({"failed_reconcile"}),
                        require_active_lease=False,
                    )
                    fence = fence.after(movement)
                    if reserve > authorized_settled:
                        release = self.ledger._movement_in_tx(  # noqa: SLF001
                            con,
                            fence,
                            movement_key=logical_movement_key(
                                fence.account_id,
                                fence.owner_user_id,
                                fence.operation_id,
                                command.step_id,
                                "release",
                            ),
                            step_id=command.step_id,
                            movement_type="release",
                            cents=reserve - authorized_settled,
                            prior_movement_key=reserve_key,
                            now_ms=now_ms,
                            allowed_operation_states=frozenset({"failed_reconcile"}),
                            require_active_lease=False,
                        )
                        fence = fence.after(release)
                    settled = authorized_settled
                    terminal_code = "reconciled_charged"
                else:
                    movement = self.ledger._movement_in_tx(  # noqa: SLF001
                        con,
                        fence,
                        movement_key=logical_movement_key(
                            fence.account_id,
                            fence.owner_user_id,
                            fence.operation_id,
                            command.step_id,
                            "release",
                        ),
                        step_id=command.step_id,
                        movement_type="release",
                        cents=reserve,
                        prior_movement_key=reserve_key,
                        now_ms=now_ms,
                        allowed_operation_states=frozenset({"failed_reconcile"}),
                        require_active_lease=False,
                    )
                    fence = fence.after(movement)
                    settled = 0
                    terminal_code = "reconciled_not_charged"
                self._write_audit_and_terminal_in_tx(
                    con,
                    operator,
                    command,
                    movement,
                    fence,
                    terminal_code,
                    settled,
                    now_ms,
                )
                con.execute("COMMIT")
                return ReconciliationReceipt(
                    command.command_id,
                    command.operation_id,
                    command.decision,
                    movement,
                    "complete",
                    settled,
                    command.charged_cents,
                )
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _write_audit_and_terminal_in_tx(
        self,
        con: sqlite3.Connection,
        operator: OperatorSubject,
        command: ReconciliationCommand,
        movement: Movement,
        fence: LeaseFence,
        terminal_code: str,
        settled_cents: int,
        now_ms: int,
    ) -> None:
        self._audit_replay_in_tx(con, command, movement_key=movement.movement_key)
        con.execute(
            "INSERT INTO paid_operation_reconciliation_audit "
            "(command_id, account_id, owner_user_id, operation_id, operator_user_id, "
            "operation_version, evidence_hash, decision, reason, charged_cents, "
            "authorized_settled_cents, step_id, movement_key, created_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                command.command_id,
                command.subject.account_id,
                command.subject.owner_user_id,
                command.operation_id,
                _identifier("operator_user_id", operator.operator_user_id),
                command.operation_version,
                command.evidence_hash,
                command.decision,
                command.reason,
                command.charged_cents,
                settled_cents,
                command.step_id,
                movement.movement_key,
                now_ms,
            ),
        )
        cur = con.execute(
            "UPDATE paid_operations SET state = 'complete', version = version + 1, updated_at_ms = ?, "
            "terminal_code = ?, terminal_reason = ?, reconciliation_status = 'resolved', "
            "settled_cents = ?, external_charged_cents = ? "
            "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
            "AND state = 'failed_reconcile' AND lease_worker_id = ? AND lease_generation = ? "
            "AND intent_hash = ? AND version = ?",
            (
                now_ms,
                terminal_code,
                command.reason,
                settled_cents,
                command.charged_cents,
                command.subject.account_id,
                command.subject.owner_user_id,
                command.operation_id,
                fence.lease_worker_id,
                fence.lease_generation,
                fence.intent_hash,
                fence.expected_operation_version,
            ),
        )
        if cur.rowcount != 1:
            raise OperationConflict("reconciliation precondition failed")

    def _audit_replay_in_tx(
        self,
        con: sqlite3.Connection,
        command: ReconciliationCommand,
        *,
        movement_key: str | None = None,
    ) -> ReconciliationReceipt | None:
        row = con.execute(
            "SELECT account_id, owner_user_id, operation_id, operation_version, evidence_hash, "
            "decision, reason, charged_cents, authorized_settled_cents, step_id, movement_key, "
            "operator_user_id, created_at_ms "
            "FROM paid_operation_reconciliation_audit WHERE account_id = ? AND owner_user_id = ? "
            "AND operation_id = ? AND command_id = ?",
            (
                command.subject.account_id,
                command.subject.owner_user_id,
                command.operation_id,
                command.command_id,
            ),
        ).fetchone()
        if row is None:
            return None
        _validate_audit_row(row)
        if (
            row[0] != command.subject.account_id
            or row[1] != command.subject.owner_user_id
            or row[2] != command.operation_id
            or row[3] != command.operation_version
            or row[4] != command.evidence_hash
            or row[5] != command.decision
            or row[6] != command.reason
            or row[7] != command.charged_cents
            or row[9] != command.step_id
            or (movement_key is not None and row[10] != movement_key)
        ):
            raise OperationConflict("reconciliation command replay conflicts")
        authorized_settled = _exact_int("authorized_settled_cents", row[8], corruption=True)
        movement = self.ledger._movement_by_key_in_tx(con, row[10])  # noqa: SLF001
        if movement is None:
            raise PaidOperationCorruptionError("reconciliation audit movement is missing")
        expected_movement_type = "reconcile" if command.decision == "confirm_charged" else "release"
        if movement.movement_type != expected_movement_type:
            raise PaidOperationCorruptionError("reconciliation audit movement type conflicts")
        reserve = (
            None
            if movement.prior_movement_key is None
            else self.ledger._movement_by_key_in_tx(con, movement.prior_movement_key)  # noqa: SLF001
        )
        if reserve is None or reserve.movement_type != "reserve":
            raise PaidOperationCorruptionError("reconciliation audit movement is missing reserve")
        if command.decision == "confirm_charged":
            self._validate_checkpoint_charge_in_tx(con, command)
        expected_settled = min(command.charged_cents, reserve.cents)
        if command.decision == "confirm_not_charged":
            expected_settled = 0
        if authorized_settled != expected_settled or (
            command.decision == "confirm_charged" and movement.cents != authorized_settled
        ):
            raise PaidOperationCorruptionError("reconciliation authorized settlement conflicts")
        terminal = con.execute(
            "SELECT state, settled_cents, external_charged_cents FROM paid_operations "
            "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ?",
            (command.subject.account_id, command.subject.owner_user_id, command.operation_id),
        ).fetchone()
        if terminal != ("complete", authorized_settled, command.charged_cents):
            raise PaidOperationCorruptionError("reconciliation terminal is incoherent")
        return ReconciliationReceipt(
            command.command_id,
            command.operation_id,
            command.decision,
            movement,
            "complete",
            authorized_settled,
            command.charged_cents,
        )

    def _validate_checkpoint_charge_in_tx(
        self,
        con: sqlite3.Connection,
        command: ReconciliationCommand,
    ) -> None:
        rows = con.execute(
            "SELECT observed_cost_cents FROM paid_operation_checkpoints "
            "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? AND step_id = ?",
            (
                command.subject.account_id,
                command.subject.owner_user_id,
                command.operation_id,
                command.step_id,
            ),
        ).fetchall()
        if len(rows) > 1:
            raise PaidOperationCorruptionError("reconciliation has duplicate step checkpoints")
        if rows and rows[0][0] != command.charged_cents:
            raise OperationConflict("external charge conflicts with provider checkpoint")

    def _reserve_cents_in_tx(self, con: sqlite3.Connection, reserve_key: str) -> int:
        movement = self.ledger._movement_by_key_in_tx(con, reserve_key)  # noqa: SLF001
        if movement is None:
            raise PaidOperationCorruptionError("retained reserve is missing")
        return movement.cents

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        con = sqlite3.connect(self._db_path, timeout=30.0, isolation_level=None, check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
        return closing(con)


def _validate_command(command: ReconciliationCommand) -> None:
    _identifier("command_id", command.command_id)
    _identifier("account_id", command.subject.account_id)
    _identifier("owner_user_id", command.subject.owner_user_id)
    _identifier("operation_id", command.operation_id)
    _exact_int("operation_version", command.operation_version)
    _hash("evidence_hash", command.evidence_hash)
    if command.decision not in {"confirm_charged", "confirm_not_charged"}:
        raise OperationConflict("reconciliation decision is invalid")
    charged_cents = _exact_int("charged_cents", command.charged_cents)
    _text("reason", command.reason)
    _identifier("step_id", command.step_id)
    if command.decision == "confirm_not_charged" and charged_cents != 0:
        raise OperationConflict("not-charged reconciliation requires zero cents")
    if command.decision == "confirm_charged" and charged_cents <= 0:
        raise OperationConflict("charged reconciliation requires positive cents")


def _validate_audit_row(row: tuple[object, ...]) -> None:
    _identifier("account_id", row[0], corruption=True)
    _identifier("owner_user_id", row[1], corruption=True)
    _identifier("operation_id", row[2], corruption=True)
    _exact_int("operation_version", row[3], corruption=True)
    _hash("evidence_hash", row[4], corruption=True)
    if row[5] not in {"confirm_charged", "confirm_not_charged"}:
        raise PaidOperationCorruptionError("reconciliation audit decision is invalid")
    _text("reason", row[6], corruption=True)
    _exact_int("charged_cents", row[7], corruption=True)
    _exact_int("authorized_settled_cents", row[8], corruption=True)
    _identifier("step_id", row[9], corruption=True)
    _identifier("movement_key", row[10], corruption=True)
    _identifier("operator_user_id", row[11], corruption=True)
    _exact_int("created_at_ms", row[12], corruption=True)


def _deny_operator(operator_user_id: str) -> bool:
    del operator_user_id
    return False


def _identifier(name: str, value: object, *, corruption: bool = False) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        _raise_material_error(f"{name} must be a lowercase canonical identifier", corruption)
    return value


def _hash(name: str, value: object, *, corruption: bool = False) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        _raise_material_error(f"{name} must be a lowercase sha256 digest", corruption)
    return value


def _text(name: str, value: object, *, corruption: bool = False) -> str:
    if (
        not isinstance(value, str)
        or not value
        or unicodedata.normalize("NFC", value) != value
        or len(value.encode("utf-8")) > _MAX_AUDIT_TEXT_BYTES
    ):
        _raise_material_error(f"{name} is invalid", corruption)
    return value


def _exact_int(name: str, value: object, *, corruption: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > _MAX_SQLITE_INT:
        _raise_material_error(f"{name} must be an exact non-negative integer", corruption)
    return value


def _raise_material_error(message: str, corruption: bool) -> NoReturn:
    if corruption:
        raise PaidOperationCorruptionError(message)
    raise OperationConflict(message)


__all__ = [
    "OperatorSubject",
    "PaidOperationReconciler",
    "ReconciliationCommand",
    "ReconciliationReceipt",
]

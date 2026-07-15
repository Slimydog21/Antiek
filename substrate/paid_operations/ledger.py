"""Same-SQLite account budget and idempotent movement ledger."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from substrate.paid_operations.store import OperationConflict, PaidOperationCorruptionError

_MIGRATION = Path(__file__).with_name("migrations") / "001_authority.sql"
_MAX_SQLITE_INT = 9_223_372_036_854_775_807
_IDENTIFIER_RE = re.compile(r"^[a-z0-9_][a-z0-9._:-]{0,191}$")
_MOVEMENT_KEY_DOMAIN = b"antiek.paid-operation.movement.v1\0"

MovementType = Literal["reserve", "settle", "release", "retain", "reconcile"]


class BudgetExceeded(OperationConflict):
    """Account or operation ceiling cannot cover the requested reserve."""


@dataclass(frozen=True)
class AccountBudget:
    account_id: str
    period_id: str
    limit_cents: int
    reserved_cents: int
    settled_cents: int
    version: int

    @property
    def available_cents(self) -> int:
        return self.limit_cents - self.reserved_cents - self.settled_cents


@dataclass(frozen=True)
class Movement:
    movement_key: str
    account_id: str
    owner_user_id: str
    operation_id: str
    period_id: str
    intent_hash: str
    step_id: str
    movement_type: MovementType
    cents: int
    lease_worker_id: str
    lease_generation: int
    expected_operation_version: int
    operation_version: int
    prior_movement_key: str | None
    created_at_ms: int


@dataclass(frozen=True)
class LeaseFence:
    account_id: str
    owner_user_id: str
    operation_id: str
    intent_hash: str
    lease_worker_id: str
    lease_generation: int
    expected_operation_version: int

    def after(self, movement: Movement) -> LeaseFence:
        """Advance this cursor only when it authorized the returned mutation."""
        if (
            movement.account_id == self.account_id
            and movement.owner_user_id == self.owner_user_id
            and movement.operation_id == self.operation_id
            and movement.lease_worker_id == self.lease_worker_id
            and movement.lease_generation == self.lease_generation
            and movement.expected_operation_version == self.expected_operation_version
        ):
            return replace(self, expected_operation_version=movement.operation_version)
        return self


class PaidOperationLedger:
    """Append-only movement ledger with exact replay/conflict semantics."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(_MIGRATION.read_text(encoding="utf-8"))

    def set_account_budget(
        self,
        account_id: str,
        period_id: str,
        limit_cents: int,
        *,
        expected_version: int | None = None,
    ) -> AccountBudget:
        _identifier("account_id", account_id)
        _identifier("period_id", period_id)
        _int("limit_cents", limit_cents)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute(
                    "SELECT account_id, period_id, limit_cents, reserved_cents, settled_cents, version "
                    "FROM paid_account_budgets WHERE account_id = ?",
                    (account_id,),
                ).fetchone()
                if row is None:
                    if expected_version not in (None, 0):
                        raise OperationConflict("budget CAS precondition failed")
                    con.execute(
                        "INSERT INTO paid_account_budgets "
                        "(account_id, period_id, limit_cents, reserved_cents, settled_cents, version) "
                        "VALUES (?, ?, ?, 0, 0, 0)",
                        (account_id, period_id, limit_cents),
                    )
                else:
                    current = _budget(row)
                    if expected_version is not None and current.version != expected_version:
                        raise OperationConflict("budget CAS precondition failed")
                    version_sql = "version + 1" if current.period_id == period_id else "0"
                    if current.period_id != period_id:
                        unresolved = con.execute(
                            "SELECT COALESCE(SUM(unresolved_cents), 0) FROM ("
                            "SELECT r.cents - COALESCE(("
                            "SELECT SUM(x.cents) FROM paid_operation_ledger x "
                            "WHERE x.prior_movement_key = r.movement_key "
                            "AND x.movement_type IN ('settle', 'release', 'reconcile')"
                            "), 0) AS unresolved_cents "
                            "FROM paid_operation_ledger r "
                            "WHERE r.account_id = ? AND r.period_id = ? AND r.movement_type = 'reserve'"
                            ")",
                            (account_id, current.period_id),
                        ).fetchone()[0]
                        if int(unresolved) != 0:
                            raise BudgetExceeded("budget period has unresolved reserves")
                    elif limit_cents < current.reserved_cents + current.settled_cents:
                        raise BudgetExceeded("budget limit cannot be set below committed funds")
                    reserved = current.reserved_cents if current.period_id == period_id else 0
                    settled = current.settled_cents if current.period_id == period_id else 0
                    if limit_cents < reserved + settled:
                        raise BudgetExceeded("budget limit cannot be set below committed funds")
                    con.execute(
                        "UPDATE paid_account_budgets SET period_id = ?, limit_cents = ?, "
                        f"reserved_cents = ?, settled_cents = ?, version = {version_sql} "
                        "WHERE account_id = ?",
                        (period_id, limit_cents, reserved, settled, account_id),
                    )
                budget = self._budget_in_tx(con, account_id)
                con.execute("COMMIT")
                return budget
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def get_budget(self, account_id: str) -> AccountBudget | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT account_id, period_id, limit_cents, reserved_cents, settled_cents, version "
                "FROM paid_account_budgets WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            return None if row is None else _budget(row)

    def reserve(self, fence: LeaseFence, cents: int, *, step_id: str, now_ms: int) -> Movement:
        return self._movement(
            fence,
            step_id=step_id,
            movement_type="reserve",
            cents=cents,
            prior_movement_key=None,
            now_ms=now_ms,
        )

    def settle(
        self,
        fence: LeaseFence,
        cents: int,
        *,
        step_id: str,
        reserve_key: str,
        now_ms: int,
    ) -> Movement:
        return self._movement(
            fence,
            step_id=step_id,
            movement_type="settle",
            cents=cents,
            prior_movement_key=reserve_key,
            now_ms=now_ms,
        )

    def release(
        self,
        fence: LeaseFence,
        cents: int,
        *,
        step_id: str,
        reserve_key: str,
        now_ms: int,
    ) -> Movement:
        return self._movement(
            fence,
            step_id=step_id,
            movement_type="release",
            cents=cents,
            prior_movement_key=reserve_key,
            now_ms=now_ms,
        )

    def retain(
        self,
        fence: LeaseFence,
        *,
        step_id: str,
        reserve_key: str,
        now_ms: int,
    ) -> Movement:
        return self._movement(
            fence,
            step_id=step_id,
            movement_type="retain",
            cents=0,
            prior_movement_key=reserve_key,
            now_ms=now_ms,
        )

    def _movement(
        self,
        fence: LeaseFence,
        *,
        step_id: str,
        movement_type: MovementType,
        cents: int,
        prior_movement_key: str | None,
        now_ms: int,
    ) -> Movement:
        _identifier("step_id", step_id)
        _int("cents", cents)
        _int("now_ms", now_ms)
        movement_key = logical_movement_key(
            fence.account_id,
            fence.owner_user_id,
            fence.operation_id,
            step_id,
            movement_type,
        )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                movement = self._movement_in_tx(
                    con,
                    fence,
                    movement_key=movement_key,
                    step_id=step_id,
                    movement_type=movement_type,
                    cents=cents,
                    prior_movement_key=prior_movement_key,
                    now_ms=now_ms,
                )
                con.execute("COMMIT")
                return movement
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _movement_in_tx(
        self,
        con: sqlite3.Connection,
        fence: LeaseFence,
        *,
        movement_key: str,
        step_id: str,
        movement_type: MovementType,
        cents: int,
        prior_movement_key: str | None,
        now_ms: int,
        allowed_operation_states: frozenset[str] = frozenset({"running"}),
        require_active_lease: bool = True,
    ) -> Movement:
        budget = self._budget_in_tx(con, fence.account_id)
        operation = con.execute(
            "SELECT ceiling_cents, state, lease_worker_id, lease_generation, intent_hash, "
            "version, lease_expires_at_ms "
            "FROM paid_operations WHERE account_id = ? AND owner_user_id = ? AND operation_id = ?",
            (fence.account_id, fence.owner_user_id, fence.operation_id),
        ).fetchone()
        if operation is None:
            raise OperationConflict("paid operation is unavailable")
        if operation[1] not in allowed_operation_states:
            raise OperationConflict("operation state does not authorize movement")
        if (
            operation[2] != fence.lease_worker_id
            or operation[3] != fence.lease_generation
            or operation[4] != fence.intent_hash
        ):
            raise OperationConflict("lease fence rejected")
        existing = self._movement_by_key_in_tx(con, movement_key)
        if existing is not None:
            if (
                existing.account_id != fence.account_id
                or existing.owner_user_id != fence.owner_user_id
                or existing.operation_id != fence.operation_id
                or existing.intent_hash != fence.intent_hash
                or existing.step_id != step_id
                or existing.movement_type != movement_type
                or existing.cents != cents
                or existing.prior_movement_key != prior_movement_key
            ):
                raise OperationConflict("ledger movement replay conflicts")
            if require_active_lease and (operation[6] is None or int(operation[6]) <= now_ms):
                raise OperationConflict("lease has expired")
            if int(operation[5]) < existing.operation_version:
                raise PaidOperationCorruptionError("ledger movement version exceeds authority")
            if (
                int(operation[5]) != fence.expected_operation_version
                and existing.expected_operation_version != fence.expected_operation_version
            ):
                raise OperationConflict("operation CAS precondition failed")
            return existing
        if require_active_lease and (operation[6] is None or int(operation[6]) <= now_ms):
            raise OperationConflict("lease has expired")
        if int(operation[5]) != fence.expected_operation_version:
            raise OperationConflict("operation CAS precondition failed")
        reserve = None if prior_movement_key is None else self._movement_by_key_in_tx(con, prior_movement_key)
        if movement_type == "reserve":
            prior_reserved = con.execute(
                "SELECT COALESCE(SUM(cents), 0) FROM paid_operation_ledger "
                "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
                "AND movement_type = 'reserve'",
                (fence.account_id, fence.owner_user_id, fence.operation_id),
            ).fetchone()[0]
            if int(prior_reserved) + cents > int(operation[0]) or cents > budget.available_cents:
                raise BudgetExceeded("paid operation budget exceeded")
            new_reserved = budget.reserved_cents + cents
            new_settled = budget.settled_cents
        else:
            if (
                reserve is None
                or reserve.movement_type != "reserve"
                or reserve.account_id != fence.account_id
                or reserve.owner_user_id != fence.owner_user_id
                or reserve.operation_id != fence.operation_id
                or reserve.intent_hash != fence.intent_hash
            ):
                raise OperationConflict("movement requires an existing reserve")
            unresolved = self._unresolved_reserve_cents_in_tx(con, reserve.movement_key)
            if movement_type in {"settle", "release", "reconcile"} and cents > unresolved:
                raise BudgetExceeded("movement exceeds unresolved reserve")
            if movement_type in {"settle", "reconcile"}:
                new_reserved = budget.reserved_cents - cents
                new_settled = budget.settled_cents + cents
            elif movement_type == "release":
                new_reserved = budget.reserved_cents - cents
                new_settled = budget.settled_cents
            else:
                new_reserved = budget.reserved_cents
                new_settled = budget.settled_cents
        if new_reserved < 0 or new_settled < 0 or new_reserved + new_settled > budget.limit_cents:
            raise PaidOperationCorruptionError("account budget aggregate drift")
        next_operation_version = fence.expected_operation_version + 1
        con.execute(
            "INSERT INTO paid_operation_ledger "
            "(movement_key, account_id, owner_user_id, operation_id, period_id, intent_hash, step_id, "
            "movement_type, cents, lease_worker_id, lease_generation, expected_operation_version, "
            "operation_version, prior_movement_key, created_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                movement_key,
                fence.account_id,
                fence.owner_user_id,
                fence.operation_id,
                budget.period_id,
                fence.intent_hash,
                step_id,
                movement_type,
                cents,
                fence.lease_worker_id,
                fence.lease_generation,
                fence.expected_operation_version,
                next_operation_version,
                prior_movement_key,
                now_ms,
            ),
        )
        con.execute(
            "UPDATE paid_account_budgets SET reserved_cents = ?, settled_cents = ?, version = version + 1 "
            "WHERE account_id = ?",
            (new_reserved, new_settled, fence.account_id),
        )
        state_placeholders = ", ".join("?" for _ in allowed_operation_states)
        active_lease_sql = " AND lease_expires_at_ms > ?" if require_active_lease else ""
        params: list[object] = [
            now_ms,
            fence.account_id,
            fence.owner_user_id,
            fence.operation_id,
            *sorted(allowed_operation_states),
            fence.lease_worker_id,
            fence.lease_generation,
            fence.intent_hash,
            fence.expected_operation_version,
        ]
        if active_lease_sql:
            params.append(now_ms)
        cur = con.execute(
            "UPDATE paid_operations SET version = version + 1, updated_at_ms = ? "
            "WHERE account_id = ? AND owner_user_id = ? AND operation_id = ? "
            f"AND state IN ({state_placeholders}) AND lease_worker_id = ? AND lease_generation = ? "
            f"AND intent_hash = ? AND version = ?{active_lease_sql}",
            params,
        )
        if cur.rowcount != 1:
            raise OperationConflict("operation CAS precondition failed")
        movement = self._movement_by_key_in_tx(con, movement_key)
        if movement is None:
            raise PaidOperationCorruptionError("ledger movement did not persist")
        return movement

    def _budget_in_tx(self, con: sqlite3.Connection, account_id: str) -> AccountBudget:
        row = con.execute(
            "SELECT account_id, period_id, limit_cents, reserved_cents, settled_cents, version "
            "FROM paid_account_budgets WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise BudgetExceeded("account budget is unavailable")
        budget = _budget(row)
        if budget.reserved_cents + budget.settled_cents > budget.limit_cents:
            raise PaidOperationCorruptionError("account budget aggregate drift")
        return budget

    def _movement_by_key_in_tx(self, con: sqlite3.Connection, movement_key: str) -> Movement | None:
        row = con.execute(
            "SELECT movement_key, account_id, owner_user_id, operation_id, period_id, intent_hash, "
            "step_id, movement_type, cents, lease_worker_id, lease_generation, expected_operation_version, "
            "operation_version, prior_movement_key, created_at_ms "
            "FROM paid_operation_ledger WHERE movement_key = ?",
            (movement_key,),
        ).fetchone()
        return None if row is None else _movement(row)

    def _unresolved_reserve_cents_in_tx(self, con: sqlite3.Connection, reserve_key: str) -> int:
        reserve = self._movement_by_key_in_tx(con, reserve_key)
        if reserve is None or reserve.movement_type != "reserve":
            raise OperationConflict("movement requires an existing reserve")
        resolved = con.execute(
            "SELECT COALESCE(SUM(cents), 0) FROM paid_operation_ledger "
            "WHERE prior_movement_key = ? AND movement_type IN ('settle', 'release', 'reconcile')",
            (reserve_key,),
        ).fetchone()[0]
        return reserve.cents - int(resolved)

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        con = sqlite3.connect(self._db_path, timeout=30.0, isolation_level=None, check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
        return closing(con)


def _budget(row: tuple[Any, ...]) -> AccountBudget:
    return AccountBudget(
        account_id=_identifier("account_id", row[0]),
        period_id=_identifier("period_id", row[1]),
        limit_cents=_int("limit_cents", row[2]),
        reserved_cents=_int("reserved_cents", row[3]),
        settled_cents=_int("settled_cents", row[4]),
        version=_int("version", row[5]),
    )


def _movement(row: tuple[Any, ...]) -> Movement:
    movement_type = row[7]
    if movement_type not in {"reserve", "settle", "release", "retain", "reconcile"}:
        raise PaidOperationCorruptionError("ledger movement type is invalid")
    prior = row[13]
    return Movement(
        movement_key=_identifier("movement_key", row[0]),
        account_id=_identifier("account_id", row[1]),
        owner_user_id=_identifier("owner_user_id", row[2]),
        operation_id=_identifier("operation_id", row[3]),
        period_id=_identifier("period_id", row[4]),
        intent_hash=_hash("intent_hash", row[5]),
        step_id=_identifier("step_id", row[6]),
        movement_type=movement_type,
        cents=_int("cents", row[8]),
        lease_worker_id=_identifier("lease_worker_id", row[9]),
        lease_generation=_int("lease_generation", row[10]),
        expected_operation_version=_int("expected_operation_version", row[11]),
        operation_version=_int("operation_version", row[12]),
        prior_movement_key=None if prior is None else _identifier("prior_movement_key", prior),
        created_at_ms=_int("created_at_ms", row[14]),
    )


def _int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaidOperationCorruptionError(f"{name} must be an exact integer")
    if value < 0 or value > _MAX_SQLITE_INT:
        raise PaidOperationCorruptionError(f"{name} integer out of range")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise PaidOperationCorruptionError(f"{name} must be a non-empty string")
    if unicodedata.normalize("NFC", value) != value:
        raise PaidOperationCorruptionError(f"{name} must be NFC-normalized")
    return value


def _identifier(name: str, value: object) -> str:
    text = _text(name, value)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise PaidOperationCorruptionError(f"{name} must be a lowercase canonical identifier")
    return text


def _hash(name: str, value: object) -> str:
    text = _text(name, value)
    if len(text) != 64 or not all(ch in "0123456789abcdef" for ch in text):
        raise PaidOperationCorruptionError(f"{name} must be a lowercase sha256 hex digest")
    return text


def logical_movement_key(
    account_id: str,
    owner_user_id: str,
    operation_id: str,
    step_id: str,
    movement_type: MovementType,
) -> str:
    material = json.dumps(
        {
            "account_id": _identifier("account_id", account_id),
            "movement_type": movement_type,
            "operation_id": _identifier("operation_id", operation_id),
            "owner_user_id": _identifier("owner_user_id", owner_user_id),
            "step_id": _identifier("step_id", step_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "mv:" + hashlib.sha256(_MOVEMENT_KEY_DOMAIN + material).hexdigest()


__all__ = [
    "AccountBudget",
    "BudgetExceeded",
    "LeaseFence",
    "Movement",
    "PaidOperationLedger",
    "logical_movement_key",
]

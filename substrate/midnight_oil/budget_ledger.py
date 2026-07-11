"""Midnight Oil runtime budget ledger.

Across the Midnight Oil PR swarm, budget was enforced at PLAN time only
(``Σ role_budgets ≤ price_ceiling`` when the plan is built). Nothing decrements
a reserved balance as roles actually spend, and the one runner shape that exists
spends BEFORE it checks. This module is the run-time reserved-balance ledger
that makes the operator's approved price ceiling a LIMIT, not a label — reserve
on PROJECTED cost before a call is made, settle actual after, so a call that
could breach the ceiling is NEVER dispatched.

All monetary values are integer cents (BIGINT). No float ever touches stored
balances or comparisons. Public API takes/returns cents (``*_cents: int``).
Negative or zero amounts raise ``ValueError`` (fail closed).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from runtime.db_lock import FlockWriteCoordinator, connect_read

__all__ = [
    "BudgetCeilingExceeded",
    "BudgetLedger",
    "CallHold",
    "RemainingBalance",
    "ReservationNotFound",
]

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BudgetCeilingExceeded(RuntimeError):
    """Raised when a debit or hold would exceed the run's approved ceiling."""

    def __init__(
        self,
        run_id: str,
        requested_cents: int,
        remaining_cents: int,
    ) -> None:
        self.run_id = run_id
        self.requested_cents = requested_cents
        self.remaining_cents = remaining_cents
        super().__init__(
            f"Run {run_id}: requested {requested_cents}\u00a2 but only "
            f"{remaining_cents}\u00a2 remaining"
        )


class ReservationNotFound(RuntimeError):
    """Raised when a run_id has no active reservation."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"No active reservation for run {run_id}")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RemainingBalance:
    """Snapshot of a run's budget state."""

    run_id: str
    ceiling_cents: int
    spent_cents: int
    held_cents: int
    remaining_cents: int
    status: str


@dataclass(frozen=True)
class CallHold:
    """A projected-cost hold placed by ``reserve_call``, consumed by ``settle``."""

    hold_id: str
    run_id: str
    role: str
    projected_max_cents: int


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL = """\
CREATE TABLE IF NOT EXISTS midnight_oil_reservations (
    run_id        TEXT PRIMARY KEY,
    ceiling_cents BIGINT NOT NULL,
    spent_cents   BIGINT NOT NULL DEFAULT 0,
    held_cents    BIGINT NOT NULL DEFAULT 0,
    freed_cents   BIGINT NOT NULL DEFAULT 0,
    status        TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS midnight_oil_role_budgets (
    run_id       TEXT,
    role         TEXT,
    budget_cents BIGINT NOT NULL,
    spent_cents  BIGINT NOT NULL DEFAULT 0,
    held_cents   BIGINT NOT NULL DEFAULT 0,
    released     BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY(run_id, role)
);
CREATE TABLE IF NOT EXISTS midnight_oil_call_holds (
    hold_id              TEXT PRIMARY KEY,
    run_id               TEXT NOT NULL,
    role                 TEXT NOT NULL,
    projected_max_cents  BIGINT NOT NULL,
    state                TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL,
    updated_at           TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS midnight_oil_spend_ledger (
    entry_id        TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    role            TEXT,
    event           TEXT NOT NULL,
    amount_cents    BIGINT NOT NULL,
    remaining_cents BIGINT NOT NULL,
    "at"            TIMESTAMP NOT NULL
);
"""


def _now_utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# BudgetLedger
# ---------------------------------------------------------------------------


class BudgetLedger:
    """Run-time reserved-balance ledger for Midnight Oil autonomous runs.

    Enforces the operator's approved price ceiling as a hard limit: reserve on
    projected cost before a call is made, settle actual after, so a call that
    could breach the ceiling is NEVER dispatched.

    Usage::

        ledger = BudgetLedger(db_path)
        ledger.ensure_schema()
        ledger.reserve("run-42", approved_ceiling_cents=5000)
        hold = ledger.reserve_call("run-42", "researcher", projected_max_cents=800)
        # ... dispatch call ...
        ledger.settle(hold, actual_cents=650)
    """

    def __init__(self, db_path: str) -> None:
        self._coordinator = FlockWriteCoordinator(db_path)
        self._db_path = db_path

    # --- schema -----------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create the three ledger tables if they don't exist."""
        with self._coordinator.acquire_write_context(
            "midnight_oil.budget_ledger",
        ) as ctx:
            for stmt in _DDL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    ctx.execute(stmt)

    def ensure_schema_in_context(self, ctx: Any) -> None:
        """Create ledger tables inside a caller-owned write transaction."""
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                ctx.execute(stmt)

    def initialize_and_hold_in_context(
        self,
        ctx: Any,
        *,
        run_id: str,
        role: str,
        approved_ceiling_cents: int,
        hold_id: str,
    ) -> CallHold:
        """Create one reservation and full-band hold in the caller's transaction.

        Exact replay returns the existing hold. Any disagreement with persisted
        monetary or ownership fields fails closed. The caller owns commit and
        rollback; all accounting SQL remains inside this ledger authority.
        """
        if approved_ceiling_cents <= 0:
            raise ValueError("approved_ceiling_cents must be positive")
        if not run_id.strip() or not role.strip() or not hold_id.strip():
            raise ValueError("run_id, role, and hold_id are required")
        self.ensure_schema_in_context(ctx)
        existing_hold = ctx.execute(
            "SELECT run_id, role, projected_max_cents, state "
            "FROM midnight_oil_call_holds WHERE hold_id = ?",
            [hold_id],
        ).fetchone()
        if existing_hold is not None:
            expected = (run_id, role, approved_ceiling_cents)
            if tuple(existing_hold[:3]) != expected or existing_hold[3] != "open":
                raise RuntimeError("persisted call hold conflicts with requested hold")
            reservation = ctx.execute(
                "SELECT ceiling_cents, spent_cents, held_cents, status "
                "FROM midnight_oil_reservations WHERE run_id = ?",
                [run_id],
            ).fetchone()
            if reservation != (approved_ceiling_cents, 0, approved_ceiling_cents, "reserved"):
                raise RuntimeError("persisted reservation conflicts with open call hold")
            role_budget = ctx.execute(
                "SELECT budget_cents, spent_cents, held_cents, released "
                "FROM midnight_oil_role_budgets WHERE run_id = ? AND role = ?",
                [run_id, role],
            ).fetchone()
            if role_budget != (approved_ceiling_cents, 0, approved_ceiling_cents, False):
                raise RuntimeError("persisted role budget conflicts with open call hold")
            events = ctx.execute(
                "SELECT event, role, amount_cents, remaining_cents "
                "FROM midnight_oil_spend_ledger WHERE run_id = ? ORDER BY event",
                [run_id],
            ).fetchall()
            if events != [
                ("hold", role, approved_ceiling_cents, 0),
                ("reserved", None, approved_ceiling_cents, 0),
            ]:
                raise RuntimeError("persisted audit ledger conflicts with open call hold")
            return CallHold(hold_id, run_id, role, approved_ceiling_cents)

        existing_reservation = ctx.execute(
            "SELECT ceiling_cents, spent_cents, held_cents, status "
            "FROM midnight_oil_reservations WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if existing_reservation is not None:
            raise RuntimeError("reservation exists without the deterministic call hold")

        now = _now_utc()
        ctx.execute(
            "INSERT INTO midnight_oil_reservations "
            "(run_id, ceiling_cents, spent_cents, held_cents, freed_cents, status, "
            "created_at, updated_at) VALUES (?, ?, 0, ?, 0, 'reserved', ?, ?)",
            [run_id, approved_ceiling_cents, approved_ceiling_cents, now, now],
        )
        ctx.execute(
            "INSERT INTO midnight_oil_role_budgets "
            "(run_id, role, budget_cents, spent_cents, held_cents, released) "
            "VALUES (?, ?, ?, 0, ?, FALSE)",
            [run_id, role, approved_ceiling_cents, approved_ceiling_cents],
        )
        ctx.execute(
            "INSERT INTO midnight_oil_call_holds "
            "(hold_id, run_id, role, projected_max_cents, state, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?)",
            [hold_id, run_id, role, approved_ceiling_cents, now, now],
        )
        self._append_ledger(
            ctx,
            run_id=run_id,
            role=None,
            event="reserved",
            amount_cents=approved_ceiling_cents,
            remaining_cents=0,
        )
        self._append_ledger(
            ctx,
            run_id=run_id,
            role=role,
            event="hold",
            amount_cents=approved_ceiling_cents,
            remaining_cents=0,
        )
        return CallHold(hold_id, run_id, role, approved_ceiling_cents)

    def charge_full_hold_in_context(self, ctx: Any, hold: CallHold) -> RemainingBalance:
        """Charge one open hold at its persisted ceiling in the caller's transaction."""
        hold_row = ctx.execute(
            "SELECT run_id, role, projected_max_cents, state "
            "FROM midnight_oil_call_holds WHERE hold_id = ?",
            [hold.hold_id],
        ).fetchone()
        if hold_row is None:
            raise ReservationNotFound(hold.hold_id)
        run_id, role, projected, state = hold_row
        if (run_id, role, projected) != (
            hold.run_id,
            hold.role,
            hold.projected_max_cents,
        ):
            raise RuntimeError("persisted call hold conflicts with supplied hold")
        if state == "settled":
            balance = self._load_balance(ctx, run_id)
            if balance.spent_cents != projected or balance.held_cents != 0:
                raise RuntimeError("settled full-band hold conflicts with reservation")
            return balance
        if state != "open":
            raise RuntimeError(f"Hold {hold.hold_id} already released")

        updated = ctx.execute(
            "UPDATE midnight_oil_call_holds SET state = 'settled', "
            "updated_at = CURRENT_TIMESTAMP WHERE hold_id = ? AND state = 'open' RETURNING 1",
            [hold.hold_id],
        ).fetchone()
        if updated is None:
            raise RuntimeError(f"Hold {hold.hold_id} already settled or released")
        reservation = ctx.execute(
            "UPDATE midnight_oil_reservations SET held_cents = held_cents - ?, "
            "spent_cents = spent_cents + ?, status = 'exhausted', "
            "updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND held_cents >= ? RETURNING 1",
            [projected, projected, run_id, projected],
        ).fetchone()
        if reservation is None:
            raise ReservationNotFound(run_id)
        role_update = ctx.execute(
            "UPDATE midnight_oil_role_budgets SET spent_cents = spent_cents + ?, "
            "held_cents = held_cents - ? WHERE run_id = ? AND role = ? "
            "AND held_cents >= ? RETURNING 1",
            [projected, projected, run_id, role, projected],
        ).fetchone()
        if role_update is None:
            raise RuntimeError("role budget cannot absorb the full-band charge")
        balance = self._load_balance(ctx, run_id)
        self._append_ledger(
            ctx,
            run_id=run_id,
            role=role,
            event="debit",
            amount_cents=projected,
            remaining_cents=balance.remaining_cents,
        )
        return balance

    # --- transactional wrapper -------------------------------------------

    @contextlib.contextmanager
    def _txn(self, ctx: Any) -> Generator[None]:
        """Wrap a block in BEGIN TRANSACTION / COMMIT / ROLLBACK.

        Every public write operation uses this so multi-statement mutations
        (state change + role update + audit row + sentinel) are atomic.
        """
        ctx.execute("BEGIN TRANSACTION")
        try:
            yield
        except Exception as exc:
            with contextlib.suppress(Exception):
                ctx.execute("ROLLBACK")
            raise exc
        else:
            ctx.execute("COMMIT")

    # --- reserve ----------------------------------------------------------

    def reserve(
        self,
        run_id: str,
        approved_ceiling_cents: int,
        role_budgets: Mapping[str, int] | None = None,
    ) -> RemainingBalance:
        """Reserve budget for a run.  Idempotent on same ceiling.

        The *approved_ceiling_cents* parameter must be the operator-approved
        ``approval_receipt.approved_price_ceiling_usd`` value (in cents), never
        the raw request amount.

        Raises ``ValueError`` if ceiling differs from a prior reservation or
        is non-positive.
        """
        if approved_ceiling_cents <= 0:
            raise ValueError("approved_ceiling_cents must be positive")

        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                existing = ctx.execute(
                    "SELECT ceiling_cents, status FROM midnight_oil_reservations WHERE run_id = ?",
                    [run_id],
                ).fetchone()

                now = _now_utc()

                if existing is not None:
                    if existing[0] != approved_ceiling_cents:
                        raise ValueError(
                            f"Run {run_id} already reserved with ceiling "
                            f"{existing[0]}\u00a2; cannot re-reserve with "
                            f"{approved_ceiling_cents}\u00a2"
                        )
                    return self._load_balance(ctx, run_id)

                # F5: validate ALL role budgets BEFORE the first INSERT.
                if role_budgets:
                    for role_name, budget in role_budgets.items():
                        if budget <= 0:
                            raise ValueError(f"Role budget for {role_name} must be positive")

                ctx.execute(
                    "INSERT INTO midnight_oil_reservations "
                    "(run_id, ceiling_cents, spent_cents, held_cents, "
                    "freed_cents, status, created_at, updated_at) "
                    "VALUES (?, ?, 0, 0, 0, 'reserved', ?, ?)",
                    [run_id, approved_ceiling_cents, now, now],
                )

                if role_budgets:
                    for role_name, budget in role_budgets.items():
                        ctx.execute(
                            "INSERT INTO midnight_oil_role_budgets "
                            "(run_id, role, budget_cents, spent_cents, "
                            "held_cents, released) "
                            "VALUES (?, ?, ?, 0, 0, FALSE)",
                            [run_id, role_name, budget],
                        )

                self._append_ledger(
                    ctx,
                    run_id=run_id,
                    role=None,
                    event="reserved",
                    amount_cents=approved_ceiling_cents,
                    remaining_cents=approved_ceiling_cents,
                )

                return RemainingBalance(
                    run_id=run_id,
                    ceiling_cents=approved_ceiling_cents,
                    spent_cents=0,
                    held_cents=0,
                    remaining_cents=approved_ceiling_cents,
                    status="reserved",
                )

    # --- check (read-only) ------------------------------------------------

    def check(self, run_id: str, amount_cents: int) -> None:
        """Read-only check: raise if *amount_cents* would exceed remaining.

        Raises ``ReservationNotFound`` if no active reservation.
        Raises ``BudgetCeilingExceeded`` if amount exceeds remaining.
        Raises ``ValueError`` if amount is non-positive.
        """
        if amount_cents <= 0:
            raise ValueError("amount_cents must be positive")

        con = connect_read(self._db_path)
        try:
            row = con.execute(
                "SELECT ceiling_cents, spent_cents, held_cents, status "
                "FROM midnight_oil_reservations WHERE run_id = ?",
                [run_id],
            ).fetchone()
            if row is None:
                raise ReservationNotFound(run_id)
            ceiling, spent, held, status = row
            if status not in ("reserved", "exhausted"):
                raise ReservationNotFound(run_id)
            remaining = ceiling - spent - held
            if amount_cents > remaining:
                raise BudgetCeilingExceeded(run_id, amount_cents, remaining)
        finally:
            con.close()

    # --- debit ------------------------------------------------------------

    def debit(
        self,
        run_id: str,
        amount_cents: int,
        role: str | None = None,
    ) -> RemainingBalance:
        """Debit *amount_cents* from the run's budget.

        Raises ``BudgetCeilingExceeded`` if amount exceeds remaining.
        Raises ``ValueError`` if amount is non-positive.
        """
        if amount_cents <= 0:
            raise ValueError("amount_cents must be positive")

        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                if role is not None:
                    self._check_role_budget(ctx, run_id, role, amount_cents)

                # TOCTOU-safe: conditional UPDATE is the arbiter.
                # DuckDB rowcount is always -1; use RETURNING + fetchone instead.
                hit = ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "spent_cents = spent_cents + ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ? "
                    "AND ceiling_cents - spent_cents - held_cents >= ? "
                    "AND status = 'reserved' "
                    "RETURNING 1",
                    [amount_cents, run_id, amount_cents],
                ).fetchone()
                if hit is None:
                    self._raise_ceiling_or_missing(ctx, run_id, amount_cents)

                if role is not None:
                    ctx.execute(
                        "UPDATE midnight_oil_role_budgets SET "
                        "spent_cents = spent_cents + ? "
                        "WHERE run_id = ? AND role = ?",
                        [amount_cents, run_id, role],
                    )

                self._maybe_mark_exhausted(ctx, run_id)

                bal = self._load_balance(ctx, run_id)
                self._append_ledger(
                    ctx,
                    run_id=run_id,
                    role=role,
                    event="debit",
                    amount_cents=amount_cents,
                    remaining_cents=bal.remaining_cents,
                )
                return bal

    def settle_in_context(self, ctx: Any, *, hold_id: str, actual_cents: int) -> RemainingBalance:
        """Settle a persisted hold inside a caller-owned transaction."""
        if actual_cents < 0:
            raise ValueError("actual_cents must be non-negative")
        self.ensure_schema_in_context(ctx)
        row = ctx.execute(
            "SELECT run_id, role, projected_max_cents, state FROM "
            "midnight_oil_call_holds WHERE hold_id = ?",
            [hold_id],
        ).fetchone()
        if row is None:
            raise ReservationNotFound(hold_id)
        run_id, role, projected, state = row
        if state != "open":
            raise RuntimeError(f"Hold {hold_id} already settled or released")
        if actual_cents > projected:
            raise ValueError("actual_cents exceeds the signed hold ceiling")
        if (
            ctx.execute(
                "UPDATE midnight_oil_call_holds SET state='settled', "
                "updated_at=CURRENT_TIMESTAMP WHERE hold_id=? AND state='open' RETURNING 1",
                [hold_id],
            ).fetchone()
            is None
        ):
            raise RuntimeError(f"Hold {hold_id} already settled or released")
        if (
            ctx.execute(
                "UPDATE midnight_oil_reservations SET held_cents=held_cents-?, "
                "spent_cents=spent_cents+?, updated_at=CURRENT_TIMESTAMP "
                "WHERE run_id=? AND held_cents>=? RETURNING 1",
                [projected, actual_cents, run_id, projected],
            ).fetchone()
            is None
        ):
            raise ReservationNotFound(str(run_id))
        role_hit = ctx.execute(
            "UPDATE midnight_oil_role_budgets SET spent_cents=spent_cents+?, "
            "held_cents=held_cents-? WHERE run_id=? AND role=? AND held_cents>=? RETURNING 1",
            [actual_cents, projected, run_id, role, projected],
        ).fetchone()
        if role_hit is None:
            raise ReservationNotFound(str(run_id))
        self._maybe_mark_exhausted(ctx, run_id)
        balance = self._load_balance(ctx, run_id)
        self._append_ledger(
            ctx,
            run_id=run_id,
            role=role,
            event="debit",
            amount_cents=actual_cents,
            remaining_cents=balance.remaining_cents,
        )
        released = projected - actual_cents
        if released:
            self._append_ledger(
                ctx,
                run_id=run_id,
                role=role,
                event="settle_release",
                amount_cents=released,
                remaining_cents=balance.remaining_cents,
            )
        return balance

    # --- reserve_call (zero-overshoot) ------------------------------------

    def reserve_call(
        self,
        run_id: str,
        role: str,
        projected_max_cents: int,
    ) -> CallHold:
        """Atomically hold *projected_max_cents* for an outbound call.

        The hold is placed iff the ceiling **and** role checks pass.  Raises
        ``BudgetCeilingExceeded`` or ``ReservationNotFound`` **before** the
        caller dispatches.

        ``projected_max_cents <= 0`` → ``ValueError`` (pricing-unknown must map
        to a conservative positive cap upstream, never to free).
        """
        if projected_max_cents <= 0:
            raise ValueError(
                "projected_max_cents must be positive "
                "(pricing-unknown must map to a conservative positive cap "
                "upstream, never to free)"
            )

        hold_id = uuid.uuid4().hex

        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                self._check_role_budget(ctx, run_id, role, projected_max_cents)

                hit = ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "held_cents = held_cents + ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ? "
                    "AND ceiling_cents - spent_cents - held_cents >= ? "
                    "AND status = 'reserved' "
                    "RETURNING 1",
                    [projected_max_cents, run_id, projected_max_cents],
                ).fetchone()
                if hit is None:
                    self._raise_ceiling_or_missing(
                        ctx,
                        run_id,
                        projected_max_cents,
                    )

                # F4: track held per role.
                ctx.execute(
                    "UPDATE midnight_oil_role_budgets SET "
                    "held_cents = held_cents + ? "
                    "WHERE run_id = ? AND role = ?",
                    [projected_max_cents, run_id, role],
                )

                ctx.execute(
                    "INSERT INTO midnight_oil_call_holds "
                    "(hold_id, run_id, role, projected_max_cents, "
                    "state, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'open', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)",
                    [hold_id, run_id, role, projected_max_cents],
                )

                bal = self._load_balance(ctx, run_id)
                self._append_ledger(
                    ctx,
                    run_id=run_id,
                    role=role,
                    event="hold",
                    amount_cents=projected_max_cents,
                    remaining_cents=bal.remaining_cents,
                )

        return CallHold(
            hold_id=hold_id,
            run_id=run_id,
            role=role,
            projected_max_cents=projected_max_cents,
        )

    # --- settle -----------------------------------------------------------

    def settle(
        self,
        hold: CallHold,
        actual_cents: int,
    ) -> RemainingBalance:
        """Settle a hold with the actual spend.

        Within one transaction: ``held -= projected_max``, ``spent += actual``,
        ``role.spent += actual``.  If ``actual > projected_max`` (projection was
        wrong — money already gone) still record the TRUE spend, append an
        ``overshoot`` ledger event, and set ``status='exhausted'`` if
        ``remaining <= 0``.  Honest accounting beats pretty accounting.

        A hold may be settled at most once (second settle → ``RuntimeError``).
        The hold row's run_id, role, and projected_max_cents are loaded from
        the persisted hold by hold_id — the caller's CallHold object is NOT
        trusted.
        """
        if actual_cents < 0:
            raise ValueError("actual_cents must be non-negative")

        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                # Load the persisted hold row — do NOT trust caller amounts.
                hold_row = ctx.execute(
                    "SELECT run_id, role, projected_max_cents, state "
                    "FROM midnight_oil_call_holds WHERE hold_id = ?",
                    [hold.hold_id],
                ).fetchone()
                if hold_row is None:
                    raise ReservationNotFound(hold.hold_id)

                _run_id, _role, _projected, _state = hold_row
                if _state != "open":
                    raise RuntimeError(f"Hold {hold.hold_id} already settled or released")

                # Transition hold state: open → settled.
                hit = ctx.execute(
                    "UPDATE midnight_oil_call_holds SET "
                    "state = 'settled', updated_at = CURRENT_TIMESTAMP "
                    "WHERE hold_id = ? AND state = 'open' RETURNING 1",
                    [hold.hold_id],
                ).fetchone()
                if hit is None:
                    raise RuntimeError(f"Hold {hold.hold_id} already settled or released")

                # Release hold + record spend atomically.
                hit = ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "held_cents = held_cents - ?, "
                    "spent_cents = spent_cents + ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ? AND held_cents >= ? "
                    "RETURNING 1",
                    [
                        _projected,
                        actual_cents,
                        _run_id,
                        _projected,
                    ],
                ).fetchone()
                if hit is None:
                    raise ReservationNotFound(_run_id)

                # Decrement role held_cents.
                ctx.execute(
                    "UPDATE midnight_oil_role_budgets SET "
                    "spent_cents = spent_cents + ?, "
                    "held_cents = held_cents - ? "
                    "WHERE run_id = ? AND role = ?",
                    [actual_cents, _projected, _run_id, _role],
                )

                self._maybe_mark_exhausted(ctx, _run_id)
                bal = self._load_balance(ctx, _run_id)

                if actual_cents > _projected:
                    # Overshoot — honest accounting.
                    self._append_ledger(
                        ctx,
                        run_id=_run_id,
                        role=_role,
                        event="overshoot",
                        amount_cents=actual_cents,
                        remaining_cents=bal.remaining_cents,
                    )
                else:
                    self._append_ledger(
                        ctx,
                        run_id=_run_id,
                        role=_role,
                        event="debit",
                        amount_cents=actual_cents,
                        remaining_cents=bal.remaining_cents,
                    )
                    released = _projected - actual_cents
                    if released > 0:
                        self._append_ledger(
                            ctx,
                            run_id=_run_id,
                            role=_role,
                            event="settle_release",
                            amount_cents=released,
                            remaining_cents=bal.remaining_cents,
                        )

                return bal

    # --- release_role -----------------------------------------------------

    def release_role(self, run_id: str, role: str) -> RemainingBalance:
        """Release a role's unspent budget to the freed pool.

        RAISES RuntimeError if the role has any open holds — settle or
        release them first.  Idempotent: releasing an already-released
        role returns current balance.
        """
        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                role_row = ctx.execute(
                    "SELECT budget_cents, spent_cents, held_cents, released "
                    "FROM midnight_oil_role_budgets "
                    "WHERE run_id = ? AND role = ?",
                    [run_id, role],
                ).fetchone()
                if role_row is None:
                    raise ReservationNotFound(run_id)

                budget, spent, role_held, already_released = role_row
                if already_released:
                    return self._load_balance(ctx, run_id)

                # Fail closed: cannot release with open holds.
                open_hold = ctx.execute(
                    "SELECT 1 FROM midnight_oil_call_holds "
                    "WHERE run_id = ? AND role = ? AND state = 'open'",
                    [run_id, role],
                ).fetchone()
                if open_hold is not None:
                    raise RuntimeError(
                        f"Cannot release role {role} of run {run_id}: "
                        f"has open holds. Settle or release them first."
                    )

                # Unspent excludes held (those funds are still committed).
                unspent = budget - spent - role_held
                if unspent > 0:
                    ctx.execute(
                        "UPDATE midnight_oil_reservations SET "
                        "freed_cents = freed_cents + ?, "
                        "updated_at = CURRENT_TIMESTAMP "
                        "WHERE run_id = ?",
                        [unspent, run_id],
                    )

                ctx.execute(
                    "UPDATE midnight_oil_role_budgets SET released = TRUE "
                    "WHERE run_id = ? AND role = ?",
                    [run_id, role],
                )

                bal = self._load_balance(ctx, run_id)
                self._append_ledger(
                    ctx,
                    run_id=run_id,
                    role=role,
                    event="role_released",
                    amount_cents=unspent,
                    remaining_cents=bal.remaining_cents,
                )
                return bal

    # --- release (end-of-run) ---------------------------------------------

    def release(self, run_id: str) -> RemainingBalance:
        """End-of-run release: set ``status='released'``.

        Raises if there are outstanding holds (``held_cents > 0``).
        """
        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                row = ctx.execute(
                    "SELECT held_cents, status FROM midnight_oil_reservations WHERE run_id = ?",
                    [run_id],
                ).fetchone()
                if row is None:
                    raise ReservationNotFound(run_id)

                held, status = row
                if status == "released":
                    return self._load_balance(ctx, run_id)
                if held > 0:
                    raise RuntimeError(f"Cannot release run {run_id}: {held}\u00a2 still held")

                ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "status = 'released', updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ?",
                    [run_id],
                )

                bal = self._load_balance(ctx, run_id)
                self._append_ledger(
                    ctx,
                    run_id=run_id,
                    role=None,
                    event="released",
                    amount_cents=0,
                    remaining_cents=bal.remaining_cents,
                )
                return bal

    # --- balance (read-only) ----------------------------------------------

    def balance(self, run_id: str) -> RemainingBalance:
        """Read-only balance query."""
        con = connect_read(self._db_path)
        try:
            row = con.execute(
                "SELECT run_id, ceiling_cents, spent_cents, held_cents, "
                "freed_cents, status "
                "FROM midnight_oil_reservations WHERE run_id = ?",
                [run_id],
            ).fetchone()
            if row is None:
                raise ReservationNotFound(run_id)
            return self._balance_row(row)
        finally:
            con.close()

    # --- guarded_call -----------------------------------------------------

    def guarded_call(
        self,
        run_id: str,
        role: str,
        projected_max_cents: int,
        call: Callable[[], tuple[T, int]],
    ) -> tuple[T, RemainingBalance]:
        """Execute *call* with budget guard.

        ``reserve_call`` → invoke ``call()`` → ``settle(hold, actual)``.

        * If ``reserve_call`` raises, ``call`` is **never** invoked.
        * If ``call`` raises, provider outcome is unknown. The projected maximum
          is charged conservatively before the exception is re-raised. A caller
          that can prove dispatch never occurred may use a separate explicit
          pre-dispatch path; a generic exception is never proof of zero spend.
        """
        hold = self.reserve_call(run_id, role, projected_max_cents)
        try:
            result, actual_cents = call()
        except Exception:
            self.settle(hold, projected_max_cents)
            raise
        balance = self.settle(hold, actual_cents)
        return result, balance

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _check_role_budget(
        self,
        ctx: Any,
        run_id: str,
        role: str,
        amount_cents: int,
    ) -> None:
        """Gate: can *role* draw *amount_cents* within its soft cap + freed?

        The run ceiling is checked separately via conditional UPDATE.

        If the role's own budget is insufficient, the excess is drawn from
        the ``freed_cents`` pool atomically (conditional UPDATE + rowcount).
        The run ceiling is the hard limit enforced by the caller's UPDATE.
        """
        role_row = ctx.execute(
            "SELECT budget_cents, spent_cents, held_cents, released "
            "FROM midnight_oil_role_budgets WHERE run_id = ? AND role = ?",
            [run_id, role],
        ).fetchone()
        if role_row is None:
            raise ReservationNotFound(run_id)

        budget, spent, role_held, released = role_row
        available = 0 if released else max(0, budget - spent - role_held)

        if amount_cents > available:
            excess = amount_cents - available
            # Atomically consume freed headroom; miss = pool exhausted.
            hit = ctx.execute(
                "UPDATE midnight_oil_reservations SET "
                "freed_cents = freed_cents - ? "
                "WHERE run_id = ? AND freed_cents >= ? "
                "RETURNING 1",
                [excess, run_id, excess],
            ).fetchone()
            if hit is None:
                res_row = ctx.execute(
                    "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = ?",
                    [run_id],
                ).fetchone()
                if res_row is None:
                    raise ReservationNotFound(run_id)
                freed = res_row[0]
                raise BudgetCeilingExceeded(
                    run_id,
                    amount_cents,
                    available + freed,
                )

    def _raise_ceiling_or_missing(
        self,
        ctx: Any,
        run_id: str,
        amount_cents: int,
    ) -> None:
        """After a failed conditional UPDATE, distinguish missing from exceeded."""
        row = ctx.execute(
            "SELECT ceiling_cents, spent_cents, held_cents, status "
            "FROM midnight_oil_reservations WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if row is None:
            raise ReservationNotFound(run_id)
        ceiling, spent, held, status = row
        if status not in ("reserved", "exhausted"):
            raise ReservationNotFound(run_id)
        remaining = ceiling - spent - held
        raise BudgetCeilingExceeded(run_id, amount_cents, remaining)

    def _maybe_mark_exhausted(self, ctx: Any, run_id: str) -> None:
        """Transition status to 'exhausted' when remaining hits zero."""
        row = ctx.execute(
            "SELECT ceiling_cents - spent_cents - held_cents, status "
            "FROM midnight_oil_reservations WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if row is not None and row[0] <= 0 and row[1] == "reserved":
            ctx.execute(
                "UPDATE midnight_oil_reservations SET "
                "status = 'exhausted', updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ? AND status = 'reserved'",
                [run_id],
            )

    def _release_hold(self, hold: CallHold) -> None:
        """Release a hold without settling (call failed).

        ``held -= projected_max``; ``spent`` unchanged.
        The hold's run_id, role, and projected_max_cents are loaded from
        the persisted hold by hold_id — the caller's CallHold object is NOT
        trusted.
        """
        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                # Load the persisted hold row.
                hold_row = ctx.execute(
                    "SELECT run_id, role, projected_max_cents, state "
                    "FROM midnight_oil_call_holds WHERE hold_id = ?",
                    [hold.hold_id],
                ).fetchone()
                if hold_row is None:
                    raise ReservationNotFound(hold.hold_id)

                _run_id, _role, _projected, _state = hold_row
                if _state != "open":
                    raise RuntimeError(f"Hold {hold.hold_id} already settled or released")

                # Transition hold state: open → released.
                hit = ctx.execute(
                    "UPDATE midnight_oil_call_holds SET "
                    "state = 'released', updated_at = CURRENT_TIMESTAMP "
                    "WHERE hold_id = ? AND state = 'open' RETURNING 1",
                    [hold.hold_id],
                ).fetchone()
                if hit is None:
                    raise RuntimeError(f"Hold {hold.hold_id} already settled or released")

                hit = ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "held_cents = held_cents - ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ? AND held_cents >= ? "
                    "RETURNING 1",
                    [_projected, _run_id, _projected],
                ).fetchone()
                if hit is None:
                    raise ReservationNotFound(_run_id)

                # Decrement role held_cents.
                ctx.execute(
                    "UPDATE midnight_oil_role_budgets SET "
                    "held_cents = held_cents - ? "
                    "WHERE run_id = ? AND role = ?",
                    [_projected, _run_id, _role],
                )

                # If status was exhausted but remaining is now positive, recover.
                bal = self._load_balance(ctx, _run_id)
                if bal.remaining_cents > 0 and bal.status == "exhausted":
                    ctx.execute(
                        "UPDATE midnight_oil_reservations SET "
                        "status = 'reserved', updated_at = CURRENT_TIMESTAMP "
                        "WHERE run_id = ?",
                        [_run_id],
                    )

                self._append_ledger(
                    ctx,
                    run_id=_run_id,
                    role=_role,
                    event="halted",
                    amount_cents=_projected,
                    remaining_cents=bal.remaining_cents,
                )

    def _load_balance(
        self,
        ctx: Any,
        run_id: str,
    ) -> RemainingBalance:
        """Load balance from a write context."""
        row = ctx.execute(
            "SELECT run_id, ceiling_cents, spent_cents, held_cents, "
            "freed_cents, status "
            "FROM midnight_oil_reservations WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if row is None:
            raise ReservationNotFound(run_id)
        return self._balance_row(row)

    @staticmethod
    def _balance_row(row: tuple[Any, ...]) -> RemainingBalance:
        run_id, ceiling, spent, held, _freed, status = row
        return RemainingBalance(
            run_id=str(run_id),
            ceiling_cents=int(ceiling),
            spent_cents=int(spent),
            held_cents=int(held),
            remaining_cents=int(ceiling) - int(spent) - int(held),
            status=str(status),
        )

    def _append_ledger(
        self,
        ctx: Any,
        *,
        run_id: str,
        role: str | None,
        event: str,
        amount_cents: int,
        remaining_cents: int,
    ) -> None:
        """Append exactly one row to the audit trail."""
        ctx.execute(
            "INSERT INTO midnight_oil_spend_ledger "
            "(entry_id, run_id, role, event, amount_cents, "
            'remaining_cents, "at") '
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                uuid.uuid4().hex,
                run_id,
                role,
                event,
                amount_cents,
                remaining_cents,
            ],
        )

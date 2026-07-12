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
import re
import uuid
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn, TypeVar

from runtime.db_lock import FlockWriteCoordinator, connect_read

__all__ = [
    "BudgetCeilingExceeded",
    "BudgetExposure",
    "BudgetLedger",
    "CallHold",
    "CallKeyReplay",
    "CallNotDispatched",
    "RemainingBalance",
    "ReservationNotFound",
    "StageBudgetExposure",
    "UnknownCallOutcome",
    "UnknownOutcomePersistenceError",
]

T = TypeVar("T")
_CALL_KEY_RE = re.compile(r"[0-9a-f]{64}")


def _call_key(value: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _CALL_KEY_RE.fullmatch(value) is None:
        raise ValueError("call_key must be a canonical lowercase SHA-256 hex digest")
    return value


def _hold_from_exposure(exposure: StageBudgetExposure) -> CallHold:
    return CallHold(
        hold_id=exposure.hold_id,
        run_id=exposure.run_id,
        role=exposure.role,
        projected_max_cents=exposure.projected_cents,
        freed_drawn_cents=0,
        call_key=exposure.call_key,
    )


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


class CallNotDispatched(Exception):
    """Raised when a call provably never reached the provider.

    This is the **only** exception that releases the hold.  Callers
    raise or wrap it when the failure is provably pre-dispatch (e.g.
    connection refused before the request was sent, local validation
    error).  The burden of proof sits with the caller — a timeout,
    lost response, or parse failure after the provider accepted the
    request is **not** proof of zero spend.
    """


class CallKeyReplay(RuntimeError):
    """A deterministic stage call key already has durable exposure.

    Exact replay never allocates another hold and never dispatches again. The
    caller must recover from ``exposure`` (or reconcile an open/unknown hold).
    """

    def __init__(self, exposure: StageBudgetExposure) -> None:
        self.exposure = exposure
        super().__init__(f"Call key {exposure.call_key} already has durable state {exposure.state}")


class UnknownCallOutcome(RuntimeError):
    """Raised when a guarded call's provider outcome is unknown.

    The hold transitions to 'unknown' (fail closed — band stays held).
    Callers use ``exc.hold.hold_id`` for durable reconciliation via
    ``resolve_unknown``.

    Attributes:
        hold: The durable ``CallHold`` whose hold_id survives concurrency
              and process boundaries.
        provider_error: The original exception raised by the provider call.
    """

    def __init__(self, hold: CallHold, provider_error: Exception) -> None:
        self.hold = hold
        self.provider_error = provider_error
        super().__init__(f"Unknown provider outcome retained for hold {hold.hold_id}")


class UnknownOutcomePersistenceError(RuntimeError):
    """Raised when transitioning a hold to 'unknown' also fails.

    Contains BOTH the original provider exception and the bookkeeping
    exception, plus the exact ``CallHold``.  The caller retains enough
    information to reconcile the durable open hold.

    Attributes:
        hold: The ``CallHold`` that was being transitioned.
        provider_error: The original exception from the provider call.
        bookkeeping_error: The exception raised during persistence.
    """

    def __init__(
        self,
        hold: CallHold,
        provider_error: Exception,
        bookkeeping_error: Exception,
    ) -> None:
        self.hold = hold
        self.provider_error = provider_error
        self.bookkeeping_error = bookkeeping_error
        super().__init__(f"Unknown-outcome persistence failed for hold {hold.hold_id}")


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
class BudgetExposure:
    """Read-only paid-call exposure split by confirmed/open/unknown state."""

    run_id: str
    ceiling_cents: int
    confirmed_spent_cents: int
    open_held_cents: int
    unknown_held_cents: int
    remaining_cents: int
    status: str


@dataclass(frozen=True)
class StageBudgetExposure:
    """Exact cent exposure for one deterministic stage call."""

    run_id: str
    call_key: str
    hold_id: str
    role: str
    projected_cents: int
    confirmed_cents: int
    open_cents: int
    unknown_cents: int
    state: str


@dataclass(frozen=True)
class CallHold:
    """A projected-cost hold placed by ``reserve_call``, consumed by ``settle``."""

    hold_id: str
    run_id: str
    role: str
    projected_max_cents: int
    freed_drawn_cents: int = 0
    call_key: str | None = None


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
    freed_drawn_cents    BIGINT NOT NULL DEFAULT 0,
    call_key             TEXT,
    actual_cents         BIGINT,
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
        """Create the three ledger tables if they don't exist.

        Also performs idempotent schema migration for columns added after
        the initial schema (e.g. ``freed_drawn_cents`` on
        ``midnight_oil_call_holds``).
        """
        with self._coordinator.acquire_write_context(
            "midnight_oil.budget_ledger",
        ) as ctx:
            for stmt in _DDL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    ctx.execute(stmt)

            # H1: idempotent migration — add freed_drawn_cents to existing
            # databases that predate Round 3.
            # DuckDB does not support NOT NULL in ALTER TABLE ADD COLUMN,
            # so we add with DEFAULT 0 (nullable for old rows, code always
            # sets it explicitly for new rows).
            ctx.execute(
                "ALTER TABLE midnight_oil_call_holds "
                "ADD COLUMN IF NOT EXISTS freed_drawn_cents "
                "BIGINT DEFAULT 0"
            )
            ctx.execute(
                "UPDATE midnight_oil_call_holds SET freed_drawn_cents = 0 "
                "WHERE freed_drawn_cents IS NULL"
            )
            ctx.execute(
                "ALTER TABLE midnight_oil_call_holds ADD COLUMN IF NOT EXISTS call_key TEXT"
            )
            ctx.execute(
                "ALTER TABLE midnight_oil_call_holds ADD COLUMN IF NOT EXISTS actual_cents BIGINT"
            )
            ctx.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS midnight_oil_call_key_unique "
                "ON midnight_oil_call_holds(run_id, call_key)"
            )

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

    # --- reserve_call (zero-overshoot) ------------------------------------

    def reserve_call(
        self,
        run_id: str,
        role: str,
        projected_max_cents: int,
        *,
        call_key: str | None = None,
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

        checked_call_key = _call_key(call_key)
        hold_id = uuid.uuid4().hex

        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                if checked_call_key is not None:
                    existing = ctx.execute(
                        "SELECT hold_id, role, projected_max_cents, state, "
                        "actual_cents FROM midnight_oil_call_holds "
                        "WHERE run_id = ? AND call_key = ?",
                        [run_id, checked_call_key],
                    ).fetchone()
                    if existing is not None:
                        existing_hold, existing_role, existing_projected, state, actual = existing
                        if (
                            str(existing_role) != role
                            or int(existing_projected) != projected_max_cents
                        ):
                            raise ValueError(
                                "call_key replay conflicts with its durable role or projection"
                            )
                        raise CallKeyReplay(
                            self._stage_exposure_row(
                                run_id=run_id,
                                call_key=checked_call_key,
                                hold_id=str(existing_hold),
                                role=str(existing_role),
                                projected_cents=int(existing_projected),
                                state=str(state),
                                actual_cents=(None if actual is None else int(actual)),
                            )
                        )
                freed_drawn = self._check_role_budget(
                    ctx,
                    run_id,
                    role,
                    projected_max_cents,
                )

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
                    "freed_drawn_cents, call_key, actual_cents, state, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, NULL, 'open', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)",
                    [
                        hold_id,
                        run_id,
                        role,
                        projected_max_cents,
                        freed_drawn,
                        checked_call_key,
                    ],
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
            freed_drawn_cents=freed_drawn,
            call_key=checked_call_key,
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
                    "SELECT run_id, role, projected_max_cents, "
                    "freed_drawn_cents, state, call_key "
                    "FROM midnight_oil_call_holds WHERE hold_id = ?",
                    [hold.hold_id],
                ).fetchone()
                if hold_row is None:
                    raise ReservationNotFound(hold.hold_id)

                _run_id, _role, _projected, _freed_drawn, _state, _call = hold_row
                if _state != "open":
                    raise RuntimeError(f"Hold {hold.hold_id} already settled or released")

                # Transition hold state: open → settled.
                hit = ctx.execute(
                    "UPDATE midnight_oil_call_holds SET "
                    "state = 'settled', actual_cents = ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE hold_id = ? AND state = 'open' RETURNING 1",
                    [actual_cents, hold.hold_id],
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

                # H2: freed-pool conservation.
                self._reconcile_freed(
                    ctx,
                    _run_id,
                    _projected,
                    _freed_drawn,
                    actual_cents,
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

                # Fail closed: cannot release with open or unknown holds.
                open_hold = ctx.execute(
                    "SELECT 1 FROM midnight_oil_call_holds "
                    "WHERE run_id = ? AND role = ? "
                    "AND state IN ('open', 'unknown')",
                    [run_id, role],
                ).fetchone()
                if open_hold is not None:
                    raise RuntimeError(
                        f"Cannot release role {role} of run {run_id}: "
                        f"has open or unknown holds. "
                        f"Settle or resolve them first."
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

    # --- resolve_unknown --------------------------------------------------

    def resolve_unknown(
        self,
        hold_id: str,
        actual_cents: int,
    ) -> RemainingBalance:
        """Reconcile a hold whose outcome was unknown.

        The hold must be in state 'unknown'.  Loads the hold row, transitions
        to 'settled', then applies the settle math: ``held -= projected_max``,
        ``spent += actual``, ``role.spent += actual``, freed reconciliation
        (H2), overshoot honesty.

        ``actual_cents=0`` is the "proven never billed" case.
        Second resolve → ``RuntimeError``.
        Resolving an 'open' hold → ``RuntimeError`` (use ``settle`` instead).
        """
        if actual_cents < 0:
            raise ValueError("actual_cents must be non-negative")

        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                hold_row = ctx.execute(
                    "SELECT run_id, role, projected_max_cents, "
                    "freed_drawn_cents, state, call_key "
                    "FROM midnight_oil_call_holds WHERE hold_id = ?",
                    [hold_id],
                ).fetchone()
                if hold_row is None:
                    raise ReservationNotFound(hold_id)

                _run_id, _role, _projected, _freed_drawn, _state, _call = hold_row
                if _state == "open":
                    raise RuntimeError(f"Hold {hold_id} is still open — use settle()")
                if _state != "unknown":
                    raise RuntimeError(f"Hold {hold_id} already {_state}")

                # Transition: unknown → settled.
                hit = ctx.execute(
                    "UPDATE midnight_oil_call_holds SET "
                    "state = 'settled', actual_cents = ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE hold_id = ? AND state = 'unknown' RETURNING 1",
                    [actual_cents, hold_id],
                ).fetchone()
                if hit is None:
                    raise RuntimeError(f"Hold {hold_id} already resolved")

                # Release hold + record spend atomically.
                hit = ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "held_cents = held_cents - ?, "
                    "spent_cents = spent_cents + ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ? AND held_cents >= ? "
                    "RETURNING 1",
                    [_projected, actual_cents, _run_id, _projected],
                ).fetchone()
                if hit is None:
                    raise ReservationNotFound(_run_id)

                # Decrement role held_cents + increment role spent.
                ctx.execute(
                    "UPDATE midnight_oil_role_budgets SET "
                    "spent_cents = spent_cents + ?, "
                    "held_cents = held_cents - ? "
                    "WHERE run_id = ? AND role = ?",
                    [actual_cents, _projected, _run_id, _role],
                )

                # H2: freed-pool conservation.
                self._reconcile_freed(
                    ctx,
                    _run_id,
                    _projected,
                    _freed_drawn,
                    actual_cents,
                )

                self._maybe_mark_exhausted(ctx, _run_id)
                bal = self._load_balance(ctx, _run_id)

                if actual_cents > _projected:
                    # M1: overshoot on unknown reconciliation — honest
                    # accounting.  Append both 'reconciled' and 'overshoot'.
                    self._append_ledger(
                        ctx,
                        run_id=_run_id,
                        role=_role,
                        event="reconciled",
                        amount_cents=actual_cents,
                        remaining_cents=bal.remaining_cents,
                    )
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
                        event="reconciled",
                        amount_cents=actual_cents,
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

    def exposure(self, run_id: str) -> BudgetExposure:
        """Return exact confirmed and unsettled call exposure without mutation."""

        con = connect_read(self._db_path)
        try:
            row = con.execute(
                "SELECT run_id, ceiling_cents, spent_cents, held_cents, "
                "freed_cents, status FROM midnight_oil_reservations "
                "WHERE run_id = ?",
                [run_id],
            ).fetchone()
            if row is None:
                raise ReservationNotFound(run_id)
            balance = self._balance_row(row)
            holds = con.execute(
                "SELECT state, COALESCE(sum(projected_max_cents), 0) "
                "FROM midnight_oil_call_holds WHERE run_id = ? "
                "AND state IN ('open', 'unknown') GROUP BY state",
                [run_id],
            ).fetchall()
            by_state = {str(state): int(cents) for state, cents in holds}
            open_cents = by_state.get("open", 0)
            unknown_cents = by_state.get("unknown", 0)
            if open_cents + unknown_cents != balance.held_cents:
                raise RuntimeError("held balance conflicts with call holds")
            return BudgetExposure(
                run_id=run_id,
                ceiling_cents=balance.ceiling_cents,
                confirmed_spent_cents=balance.spent_cents,
                open_held_cents=open_cents,
                unknown_held_cents=unknown_cents,
                remaining_cents=balance.remaining_cents,
                status=balance.status,
            )
        finally:
            con.close()

    @staticmethod
    def _stage_exposure_row(
        *,
        run_id: str,
        call_key: str,
        hold_id: str,
        role: str,
        projected_cents: int,
        state: str,
        actual_cents: int | None,
    ) -> StageBudgetExposure:
        if state not in {"open", "unknown", "settled", "released"}:
            raise RuntimeError("stage hold has an unknown durable state")
        if projected_cents <= 0 or (actual_cents is not None and actual_cents < 0):
            raise RuntimeError("stage hold contains invalid cent exposure")
        if state == "settled":
            if actual_cents is None:
                raise RuntimeError("settled stage hold lacks confirmed actual cents")
            confirmed = actual_cents
        else:
            if actual_cents is not None:
                raise RuntimeError("unsettled stage hold carries confirmed actual cents")
            confirmed = 0
        return StageBudgetExposure(
            run_id=run_id,
            call_key=call_key,
            hold_id=hold_id,
            role=role,
            projected_cents=projected_cents,
            confirmed_cents=confirmed,
            open_cents=projected_cents if state == "open" else 0,
            unknown_cents=projected_cents if state == "unknown" else 0,
            state=state,
        )

    def stage_exposure(self, run_id: str, call_key: str) -> StageBudgetExposure:
        """Return authoritative exposure for one deterministic stage key."""
        checked = _call_key(call_key)
        assert checked is not None
        con = connect_read(self._db_path)
        try:
            row = con.execute(
                "SELECT hold_id, role, projected_max_cents, state, actual_cents "
                "FROM midnight_oil_call_holds WHERE run_id = ? AND call_key = ?",
                [run_id, checked],
            ).fetchone()
            if row is None:
                raise ReservationNotFound(checked)
            hold_id, role, projected, state, actual = row
            return self._stage_exposure_row(
                run_id=run_id,
                call_key=checked,
                hold_id=str(hold_id),
                role=str(role),
                projected_cents=int(projected),
                state=str(state),
                actual_cents=None if actual is None else int(actual),
            )
        finally:
            con.close()

    def mark_stage_call_unknown(self, run_id: str, call_key: str) -> StageBudgetExposure:
        """Fail closed an open keyed stage hold after an ambiguous dispatch window."""
        checked = _call_key(call_key)
        assert checked is not None
        with (
            self._coordinator.acquire_write_context(
                "midnight_oil.budget_ledger.stage_unknown"
            ) as ctx,
            self._txn(ctx),
        ):
            row = ctx.execute(
                "SELECT hold_id, role, projected_max_cents, state, actual_cents "
                "FROM midnight_oil_call_holds WHERE run_id = ? AND call_key = ?",
                [run_id, checked],
            ).fetchone()
            if row is None:
                raise ReservationNotFound(checked)
            hold_id, role, projected, state, actual = row
            if state == "open":
                hit = ctx.execute(
                    "UPDATE midnight_oil_call_holds SET state = 'unknown', "
                    "updated_at = CURRENT_TIMESTAMP WHERE hold_id = ? AND state = 'open' "
                    "RETURNING 1",
                    [hold_id],
                ).fetchone()
                if hit is None:
                    raise RuntimeError("stage hold changed during unknown transition")
                balance = self._load_balance(ctx, run_id)
                self._append_ledger(
                    ctx,
                    run_id=run_id,
                    role=str(role),
                    event="unknown_outcome",
                    amount_cents=int(projected),
                    remaining_cents=balance.remaining_cents,
                )
                state = "unknown"
            elif state != "unknown":
                raise ValueError("only an open stage call may become unknown")
            return self._stage_exposure_row(
                run_id=run_id,
                call_key=checked,
                hold_id=str(hold_id),
                role=str(role),
                projected_cents=int(projected),
                state=str(state),
                actual_cents=None if actual is None else int(actual),
            )

    def release_stage_call(self, run_id: str, call_key: str) -> StageBudgetExposure:
        """Release an open keyed hold after proof that no network dispatch occurred."""
        exposure = self.stage_exposure(run_id, call_key)
        if exposure.state == "released":
            return exposure
        if exposure.state != "open":
            raise ValueError("only an open stage call may be released")
        try:
            self._release_hold(_hold_from_exposure(exposure))
        except RuntimeError:
            durable = self.stage_exposure(run_id, call_key)
            if durable.state != "released":
                raise
            return durable
        return self.stage_exposure(run_id, call_key)

    def run_stage_fenced(
        self,
        run_id: str,
        call_key: str,
        *,
        expected_states: frozenset[str],
        action: Callable[[StageBudgetExposure], T],
    ) -> T:
        """Run a stage CAS while keyed cent exposure cannot change.

        Lock order for stage mutations is fixed and load-bearing:
        ``OperationQueue.run_fenced`` operation flock → this budget
        coordinator/transaction → stage SQLite ``BEGIN IMMEDIATE``. Callers
        must never acquire these in reverse order.
        """
        checked = _call_key(call_key)
        assert checked is not None
        if not expected_states or not expected_states.issubset(
            {"open", "unknown", "settled", "released"}
        ):
            raise ValueError("expected stage exposure states are invalid")
        with (
            self._coordinator.acquire_write_context(
                "midnight_oil.budget_ledger.stage_fence"
            ) as ctx,
            self._txn(ctx),
        ):
            row = ctx.execute(
                "SELECT hold_id, role, projected_max_cents, state, actual_cents "
                "FROM midnight_oil_call_holds WHERE run_id = ? AND call_key = ?",
                [run_id, checked],
            ).fetchone()
            if row is None:
                raise ReservationNotFound(checked)
            hold_id, role, projected, state, actual = row
            exposure = self._stage_exposure_row(
                run_id=run_id,
                call_key=checked,
                hold_id=str(hold_id),
                role=str(role),
                projected_cents=int(projected),
                state=str(state),
                actual_cents=None if actual is None else int(actual),
            )
            if exposure.state not in expected_states:
                raise ValueError("stage transition conflicts with authoritative budget exposure")
            return action(exposure)

    # --- guarded_call -----------------------------------------------------

    def guarded_call(
        self,
        run_id: str,
        role: str,
        projected_max_cents: int,
        call: Callable[[], tuple[T, int]],
        *,
        call_key: str | None = None,
        after_reserve: Callable[[CallHold], None] | None = None,
        before_settle: Callable[[T, int], None] | None = None,
    ) -> tuple[T, RemainingBalance]:
        """Execute *call* with budget guard.

        ``reserve_call`` → invoke ``call()`` → ``settle(hold, actual)``.

        * If ``reserve_call`` raises, ``call`` is **never** invoked.
        * If ``call`` raises ``CallNotDispatched``, the hold is released
          (provably pre-dispatch).
        * If ``call`` raises any other exception, the outcome is unknown —
          the hold transitions to 'unknown' and the projected maximum stays
          held (fail closed).  An ``UnknownCallOutcome`` is raised with the
          durable ``hold`` and ``provider_error`` so callers can reconcile
          via ``exc.hold.hold_id``.
        * If transitioning to 'unknown' also fails (bookkeeping error),
          ``UnknownOutcomePersistenceError`` is raised containing BOTH the
          original provider exception and the bookkeeping exception, with
          the exact ``CallHold``.  The hold remains open (fail closed).
        """
        hold = self.reserve_call(
            run_id,
            role,
            projected_max_cents,
            call_key=call_key,
        )
        if after_reserve is not None:
            after_reserve(hold)

        def raise_unknown(error: Exception) -> NoReturn:
            try:
                durable_hold = self._mark_hold_unknown(hold)
            except Exception as bookkeeping_error:
                raise UnknownOutcomePersistenceError(
                    hold,
                    error,
                    bookkeeping_error,
                ) from None
            raise UnknownCallOutcome(durable_hold, error) from None

        try:
            result, actual_cents = call()
        except CallNotDispatched:
            # Provably pre-dispatch: safe to release.
            self._release_hold(hold)
            raise
        except Exception as provider_error:
            raise_unknown(provider_error)

        # The provider has returned. From this point onward no exception can
        # prove non-dispatch, even if it uses the CallNotDispatched type.
        if before_settle is not None:
            try:
                before_settle(result, actual_cents)
            except Exception as checkpoint_error:
                raise_unknown(checkpoint_error)
        balance = self.settle(hold, actual_cents)
        return result, balance

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _mark_hold_unknown(self, hold: CallHold) -> CallHold:
        """Transition a hold from 'open' to 'unknown' (fail closed).

        The hold's projected_max stays held — the band is unavailable until
        ``resolve_unknown`` is called.  Appends an ``unknown_outcome`` event.

        Returns a ``CallHold`` with the durable hold_id (loaded from DB).
        Raises ``RuntimeError`` if the hold is not in 'open' state.
        """
        with self._coordinator.acquire_write_context(  # noqa: SIM117
            "midnight_oil.budget_ledger",
        ) as ctx:
            with self._txn(ctx):
                hold_row = ctx.execute(
                    "SELECT run_id, role, projected_max_cents, "
                    "freed_drawn_cents, state, call_key "
                    "FROM midnight_oil_call_holds WHERE hold_id = ?",
                    [hold.hold_id],
                ).fetchone()
                if hold_row is None:
                    raise ReservationNotFound(hold.hold_id)

                _run_id, _role, _projected, _freed_drawn, _state, _call = hold_row
                if _state != "open":
                    raise RuntimeError(f"Hold {hold.hold_id} already {_state}")

                hit = ctx.execute(
                    "UPDATE midnight_oil_call_holds SET "
                    "state = 'unknown', updated_at = CURRENT_TIMESTAMP "
                    "WHERE hold_id = ? AND state = 'open' RETURNING 1",
                    [hold.hold_id],
                ).fetchone()
                if hit is None:
                    raise RuntimeError(f"Hold {hold.hold_id} already {_state}")

                bal = self._load_balance(ctx, _run_id)
                self._append_ledger(
                    ctx,
                    run_id=_run_id,
                    role=_role,
                    event="unknown_outcome",
                    amount_cents=_projected,
                    remaining_cents=bal.remaining_cents,
                )

                return CallHold(
                    hold_id=hold.hold_id,
                    run_id=_run_id,
                    role=_role,
                    projected_max_cents=_projected,
                    freed_drawn_cents=_freed_drawn,
                    call_key=None if _call is None else str(_call),
                )

    def _reconcile_freed(
        self,
        ctx: Any,
        run_id: str,
        projected: int,
        freed_drawn: int,
        actual: int,
    ) -> None:
        """H2: freed-pool conservation at settle / resolve_unknown time.

        ``role_part = projected - freed_drawn`` is the portion covered by
        the role's own allocation.  ``actual_excess = max(0, actual - role_part)``
        is the true excess.  ``delta = actual_excess - freed_drawn``:
          - delta < 0: refund ``-delta`` to freed_cents.
          - delta > 0: best-effort consume ``min(delta, freed_available)``.
        """
        role_part = projected - freed_drawn
        actual_excess = max(0, actual - role_part)
        delta = actual_excess - freed_drawn

        if delta < 0:
            refund = -delta
            ctx.execute(
                "UPDATE midnight_oil_reservations SET "
                "freed_cents = freed_cents + ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ?",
                [refund, run_id],
            )
            self._append_ledger(
                ctx,
                run_id=run_id,
                role=None,
                event="freed_refund",
                amount_cents=refund,
                remaining_cents=self._load_balance(
                    ctx,
                    run_id,
                ).remaining_cents,
            )
        elif delta > 0:
            # Best-effort: consume what's available, never raise.
            res_row = ctx.execute(
                "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = ?",
                [run_id],
            ).fetchone()
            freed_available = int(res_row[0]) if res_row else 0
            consume = min(delta, freed_available)
            if consume > 0:
                ctx.execute(
                    "UPDATE midnight_oil_reservations SET "
                    "freed_cents = freed_cents - ?, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE run_id = ? AND freed_cents >= ?",
                    [consume, run_id, consume],
                )
            # The unconsumed shortfall (delta - consume) is role-budget
            # overshoot — already captured in the overshoot event's honesty.

    def _check_role_budget(
        self,
        ctx: Any,
        run_id: str,
        role: str,
        amount_cents: int,
    ) -> int:
        """Gate: can *role* draw *amount_cents* within its soft cap + freed?

        The run ceiling is checked separately via conditional UPDATE.

        If the role's own budget is insufficient, the excess is drawn from
        the ``freed_cents`` pool atomically (conditional UPDATE + rowcount).
        The run ceiling is the hard limit enforced by the caller's UPDATE.

        Returns the amount drawn from the freed pool (0 if none needed).
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
            return excess
        return 0

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
        """Release a hold without settling (call provably never dispatched).

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
                    "SELECT run_id, role, projected_max_cents, "
                    "freed_drawn_cents, state "
                    "FROM midnight_oil_call_holds WHERE hold_id = ?",
                    [hold.hold_id],
                ).fetchone()
                if hold_row is None:
                    raise ReservationNotFound(hold.hold_id)

                _run_id, _role, _projected, _freed_drawn, _state = hold_row
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

                # Refund any freed drawn back to the pool.
                if _freed_drawn > 0:
                    ctx.execute(
                        "UPDATE midnight_oil_reservations SET "
                        "freed_cents = freed_cents + ?, "
                        "updated_at = CURRENT_TIMESTAMP "
                        "WHERE run_id = ?",
                        [_freed_drawn, _run_id],
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

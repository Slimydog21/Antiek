"""Red-proof test suite for Midnight Oil budget ledger.

Every test asserts OUTCOMES (balances, statuses, ledger rows), not
mocks-were-called.  Uses tmp_path DuckDB files — no shared state.
"""

from __future__ import annotations

import pathlib
import threading
from unittest.mock import patch

import pytest

from substrate.midnight_oil.budget_ledger import (
    BudgetCeilingExceeded,
    BudgetLedger,
    CallHold,
    CallNotDispatched,
    ReservationNotFound,
    UnknownCallOutcome,
    UnknownOutcomePersistenceError,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ledger(tmp_path: object) -> BudgetLedger:
    """Create a fresh ledger with schema in *tmp_path*."""
    db = pathlib.Path(str(tmp_path)) / "test.duckdb"
    ledger = BudgetLedger(str(db))
    ledger.ensure_schema()
    return ledger


# ---------------------------------------------------------------------------
# 1. Hard ceiling under over-spend
# ---------------------------------------------------------------------------

def test_hard_ceiling_under_overspend(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300)

    ledger.debit("r1", 120)
    ledger.debit("r1", 120)

    with pytest.raises(BudgetCeilingExceeded) as exc_info:
        ledger.debit("r1", 120)

    assert exc_info.value.remaining_cents == 60

    bal = ledger.balance("r1")
    assert bal.spent_cents == 240
    assert bal.remaining_cents == 60
    assert bal.status == "reserved"


# ---------------------------------------------------------------------------
# 2. Exact fit then exhaust
# ---------------------------------------------------------------------------

def test_exact_fit_then_exhaust(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300)

    ledger.debit("r1", 150)
    ledger.debit("r1", 150)

    bal = ledger.balance("r1")
    assert bal.status == "exhausted"
    assert bal.spent_cents == 300
    assert bal.remaining_cents == 0

    with pytest.raises(BudgetCeilingExceeded):
        ledger.debit("r1", 1)


# ---------------------------------------------------------------------------
# 3. No float leak at $10.03
# ---------------------------------------------------------------------------

def test_no_float_leak_at_ten_oh_three(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 1003)

    for _ in range(59):
        ledger.debit("r1", 17)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 1003
    assert bal.remaining_cents == 0
    assert bal.status == "exhausted"


# ---------------------------------------------------------------------------
# 4. Concurrent debit atomicity
# ---------------------------------------------------------------------------

def test_concurrent_debit_atomicity(tmp_path: object) -> None:
    import pathlib

    db = pathlib.Path(str(tmp_path)) / "test.duckdb"
    ledger = BudgetLedger(str(db))
    ledger.ensure_schema()
    ledger.reserve("r1", 1000)

    successes: list[int] = []
    errors: list[int] = []
    lock = threading.Lock()

    def worker(amount: int) -> None:
        try:
            ledger.debit("r1", amount)
            with lock:
                successes.append(amount)
        except BudgetCeilingExceeded:
            with lock:
                errors.append(amount)

    threads = [threading.Thread(target=worker, args=(100,)) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    bal = ledger.balance("r1")
    assert bal.spent_cents <= 1000
    assert bal.spent_cents == sum(successes)
    # Ledger debit rows count matches successes.
    from runtime.db_lock import connect_read

    rd = connect_read(str(db))
    try:
        rows = rd.execute(
            "SELECT COUNT(*) FROM midnight_oil_spend_ledger WHERE event = 'debit'"
        ).fetchone()
    finally:
        rd.close()
    assert rows[0] == len(successes)


# ---------------------------------------------------------------------------
# 5. ZERO-OVERSHOOT spy (the headline)
# ---------------------------------------------------------------------------

def test_zero_overshoot_spy(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"researcher": 300})

    call_count = 0

    def fake_call() -> tuple[str, int]:
        nonlocal call_count
        call_count += 1
        return ("result", 50)

    # Three calls: projected 100, actual 50 each.
    # After each: spent += 50, remaining decreases by 50.
    ledger.guarded_call("r1", "researcher", 100, fake_call)
    assert call_count == 1

    ledger.guarded_call("r1", "researcher", 100, fake_call)
    assert call_count == 2

    ledger.guarded_call("r1", "researcher", 100, fake_call)
    assert call_count == 3

    # Now remaining = 300 - 150 = 150.  Projected 200 > 150 → raises.
    with pytest.raises(BudgetCeilingExceeded):
        ledger.guarded_call("r1", "researcher", 200, fake_call)

    # The spy recorded ZERO invocations for that step.
    assert call_count == 3

    bal = ledger.balance("r1")
    assert bal.spent_cents == 150  # unchanged by the halted step


# ---------------------------------------------------------------------------
# 6. Settle releases the unused band
# ---------------------------------------------------------------------------

def test_settle_releases_unused_band(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 200, role_budgets={"dev": 200})

    def cheap_call() -> tuple[str, int]:
        return ("ok", 40)

    ledger.guarded_call("r1", "dev", 100, cheap_call)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 40
    assert bal.remaining_cents == 160

    # Ledger: reserved, hold(100), debit(40), settle_release(60)
    con = ledger._db_path  # noqa: SLF001
    from runtime.db_lock import connect_read

    rd = connect_read(con)
    try:
        events = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "ORDER BY \"at\", entry_id"
        ).fetchall()
    finally:
        rd.close()

    event_list = [(e[0], int(e[1])) for e in events]
    assert ("reserved", 200) in event_list
    assert ("hold", 100) in event_list
    assert ("debit", 40) in event_list
    assert ("settle_release", 60) in event_list

    # No sentinel rows — hold state is in midnight_oil_call_holds.
    sentinel_events = [e for e in event_list if "hold_state" in e[0]]
    assert sentinel_events == []


# ---------------------------------------------------------------------------
# 7. Overshoot honesty
# ---------------------------------------------------------------------------

def test_overshoot_honesty(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 100, role_budgets={"r": 100})

    # Pre-spend 60 so remaining = 40.
    ledger.debit("r1", 60, role="r")

    def overshoot_call() -> tuple[str, int]:
        return ("oops", 50)  # projected 30, actual 50

    ledger.guarded_call("r1", "r", 30, overshoot_call)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 110  # 60 + 50
    assert bal.status == "exhausted"

    # Ledger contains an overshoot event.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "WHERE event = 'overshoot'"
        ).fetchall()
    finally:
        rd.close()

    assert len(rows) == 1
    assert int(rows[0][1]) == 50


# ---------------------------------------------------------------------------
# 8. Role headroom
# ---------------------------------------------------------------------------

def test_role_headroom(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve(
        "r1", 300,
        role_budgets={"a": 100, "b": 100, "c": 100},
    )

    # Role a spends 40 and is released → frees 60.
    ledger.debit("r1", 40, role="a")
    ledger.release_role("r1", "a")

    # Role b may spend up to 160 (100 own + 60 freed).
    ledger.debit("r1", 160, role="b")

    # 161 would exceed role b's headroom (100 + 60 = 160).
    with pytest.raises(BudgetCeilingExceeded):
        ledger.debit("r1", 161, role="b")

    # Nothing may cross the 300 ceiling: remaining = 300 - 40 - 160 = 100.
    bal = ledger.balance("r1")
    assert bal.remaining_cents == 100
    assert bal.spent_cents == 200


# ---------------------------------------------------------------------------
# 9. Reserve idempotency
# ---------------------------------------------------------------------------

def test_reserve_idempotency(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)

    b1 = ledger.reserve("r1", 500)
    b2 = ledger.reserve("r1", 500)
    assert b1.ceiling_cents == b2.ceiling_cents
    assert b1.run_id == b2.run_id

    # Different ceiling → ValueError.
    with pytest.raises(ValueError, match="already reserved"):
        ledger.reserve("r1", 999)


# ---------------------------------------------------------------------------
# 10. CallNotDispatched releases hold; plain RuntimeError does NOT
# ---------------------------------------------------------------------------

def test_failed_call_charges_projected_maximum(tmp_path: object) -> None:
    """CallNotDispatched releases the hold (provably pre-dispatch).
    A plain RuntimeError does NOT release — fail closed (unknown outcome).
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    # --- CallNotDispatched path: hold released, spent 0. ---
    def not_dispatched_call() -> tuple[str, int]:
        raise CallNotDispatched("connection refused before send")

    with pytest.raises(CallNotDispatched):
        ledger.guarded_call("r1", "r", 100, not_dispatched_call)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 0
    assert bal.held_cents == 0
    assert bal.remaining_cents == 300

    # 'halted' event present (from _release_hold).
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "WHERE event = 'halted'"
        ).fetchall()
    finally:
        rd.close()
    assert len(rows) == 1

    # --- Plain RuntimeError path: hold transitions to 'unknown', NOT released. ---
    def exploding_call() -> tuple[str, int]:
        raise RuntimeError("boom")

    with pytest.raises(UnknownCallOutcome) as exc_info:
        ledger.guarded_call("r1", "r", 100, exploding_call)

    # H2: durable hold ID survives in the exception.
    assert exc_info.value.hold.hold_id  # non-empty
    assert str(exc_info.value.provider_error) == "boom"

    bal = ledger.balance("r1")
    # held_cents == 100 (fail closed), spent == 0 (not settled yet).
    assert bal.held_cents == 100
    assert bal.spent_cents == 0
    assert bal.remaining_cents == 200

    # Hold state is 'unknown'.
    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        hold_states = rd.execute(
            "SELECT state FROM midnight_oil_call_holds "
            "ORDER BY created_at, hold_id"
        ).fetchall()
    finally:
        rd.close()
    states = [s[0] for s in hold_states]
    assert "released" in states
    assert "unknown" in states


def test_billed_timeout_cannot_restore_reusable_budget(tmp_path: object) -> None:
    """TimeoutError (not CallNotDispatched) → hold transitions to 'unknown',
    band stays held.  Second call raises BudgetCeilingExceeded before dispatch.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 100, role_budgets={"researcher": 100})
    external_spent_cents = 0

    def billed_then_timed_out() -> tuple[str, int]:
        nonlocal external_spent_cents
        external_spent_cents += 100
        raise TimeoutError("provider accepted request but response timed out")

    with pytest.raises(UnknownCallOutcome) as exc_info:
        ledger.guarded_call("r1", "researcher", 100, billed_then_timed_out)

    # H2: durable hold ID and provider error available.
    assert exc_info.value.hold.hold_id
    assert isinstance(exc_info.value.provider_error, TimeoutError)

    bal = ledger.balance("r1")
    # Only 1 external bill (second call never dispatched).
    assert external_spent_cents == 100
    # Fail closed: held, not spent.  Unknown hold keeps band unavailable.
    assert bal.held_cents == 100
    assert bal.spent_cents == 0
    assert bal.remaining_cents == 0

    # Second call: BudgetCeilingExceeded BEFORE dispatch.
    call_count = 0

    def should_not_fire() -> tuple[str, int]:
        nonlocal call_count
        call_count += 1
        return ("result", 100)

    with pytest.raises(BudgetCeilingExceeded):
        ledger.guarded_call("r1", "researcher", 100, should_not_fire)

    assert call_count == 0  # spy: zero invocations


# ---------------------------------------------------------------------------
# 22. CallNotDispatched releases; plain RuntimeError does NOT (H1)
# ---------------------------------------------------------------------------

def test_call_not_dispatched_releases(tmp_path: object) -> None:
    """CallNotDispatched → hold released, spent 0, halted event.
    Plain RuntimeError → hold 'unknown', held stays, no release.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    # --- CallNotDispatched: releases the hold. ---
    def not_dispatched() -> tuple[str, int]:
        raise CallNotDispatched("connection refused")

    with pytest.raises(CallNotDispatched):
        ledger.guarded_call("r1", "r", 100, not_dispatched)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 0
    assert bal.held_cents == 0
    assert bal.remaining_cents == 300

    # 'halted' event present.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event FROM midnight_oil_spend_ledger "
            "WHERE event = 'halted'"
        ).fetchall()
    finally:
        rd.close()
    assert len(rows) >= 1

    # --- Plain RuntimeError: does NOT release. ---
    def boom() -> tuple[str, int]:
        raise RuntimeError("boom")

    with pytest.raises(UnknownCallOutcome) as exc_info:
        ledger.guarded_call("r1", "r", 100, boom)

    # H2: durable hold ID and provider error available.
    assert exc_info.value.hold.hold_id
    assert str(exc_info.value.provider_error) == "boom"

    bal = ledger.balance("r1")
    assert bal.held_cents == 100  # still held (fail closed)
    assert bal.spent_cents == 0
    assert bal.remaining_cents == 200

    # Hold state is 'unknown', not 'released'.
    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        states = rd.execute(
            "SELECT state FROM midnight_oil_call_holds "
            "ORDER BY created_at, hold_id"
        ).fetchall()
    finally:
        rd.close()
    state_list = [s[0] for s in states]
    assert "released" in state_list
    assert "unknown" in state_list


# ---------------------------------------------------------------------------
# 23. resolve_unknown (H1)
# ---------------------------------------------------------------------------

def test_resolve_unknown(tmp_path: object) -> None:
    """After test-21 state (unknown hold), resolve_unknown(hold, 60)
    → held 0, spent 60, remaining 40, 'reconciled' event.
    Second resolve → RuntimeError.
    resolve_unknown on an 'open' hold → RuntimeError.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 100, role_budgets={"researcher": 100})

    def billed_then_timeout() -> tuple[str, int]:
        raise TimeoutError("lost response")

    with pytest.raises(UnknownCallOutcome) as exc_info:
        ledger.guarded_call("r1", "researcher", 100, billed_then_timeout)

    # H2: use exc.hold.hold_id for durable reconciliation.
    hold_id = exc_info.value.hold.hold_id

    # Resolve with actual 60.
    bal = ledger.resolve_unknown(hold_id, 60)
    assert bal.held_cents == 0
    assert bal.spent_cents == 60
    assert bal.remaining_cents == 40

    # 'reconciled' event present.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event FROM midnight_oil_spend_ledger "
            "WHERE event = 'reconciled'"
        ).fetchall()
    finally:
        rd.close()
    assert len(rows) >= 1

    # Second resolve → RuntimeError.
    with pytest.raises(RuntimeError, match="already settled"):
        ledger.resolve_unknown(hold_id, 30)

    # resolve_unknown on an 'open' hold → RuntimeError.
    # Use the same ledger with a new run for this sub-scenario.
    ledger.reserve("r2", 200, role_budgets={"r": 200})
    open_hold = ledger.reserve_call("r2", "r", 50)
    with pytest.raises(RuntimeError, match="still open"):
        ledger.resolve_unknown(open_hold.hold_id, 10)


# ---------------------------------------------------------------------------
# 24. release blocked by unknown hold; succeeds after resolve (H1)
# ---------------------------------------------------------------------------

def test_release_blocked_by_unknown_hold(tmp_path: object) -> None:
    """release(run) with an unknown hold → raises.
    After resolve_unknown → succeeds.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 200, role_budgets={"r": 200})

    def timeout_call() -> tuple[str, int]:
        raise TimeoutError("lost")

    with pytest.raises(UnknownCallOutcome):
        ledger.guarded_call("r1", "r", 100, timeout_call)

    # release(run) blocked by held_cents > 0.
    with pytest.raises(RuntimeError, match="still held"):
        ledger.release("r1")

    # Resolve the unknown.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        hold_row = rd.execute(
            "SELECT hold_id FROM midnight_oil_call_holds "
            "WHERE state = 'unknown'"
        ).fetchone()
    finally:
        rd.close()
    ledger.resolve_unknown(hold_row[0], 0)  # proven never billed

    # Now release succeeds.
    bal = ledger.release("r1")
    assert bal.status == "released"


# ---------------------------------------------------------------------------
# 25. Freed-pool conservation: full refund (H2)
# ---------------------------------------------------------------------------

def test_freed_pool_conservation_full_refund(tmp_path: object) -> None:
    """Role budget 100¢, freed 60¢ (from released sibling).
    Hold projected 160 (draws 60 freed), settle actual 100
    → freed back to 60 (full refund), freed_refund event.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve(
        "r1", 300,
        role_budgets={"a": 100, "b": 100, "c": 100},
    )

    # Release role a → freed = 60 (a had no spend, unspent = 100).
    ledger.release_role("r1", "a")

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 100  # full role a budget freed

    # Place hold on role b: projected 160 (100 own + 60 freed draw).
    hold = ledger.reserve_call("r1", "b", 160)

    # freed should now be 40 (100 - 60 consumed).
    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 40

    # Settle actual 100 (within role budget, no excess).
    # role_part = 160 - 60 = 100.  actual_excess = max(0, 100 - 100) = 0.
    # delta = 0 - 60 = -60.  refund 60 to freed.
    ledger.settle(hold, 100)

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
        refund_events = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "WHERE event = 'freed_refund'"
        ).fetchall()
    finally:
        rd.close()
    assert int(row[0]) == 100  # freed back to 100
    assert len(refund_events) >= 1
    assert any(int(e[1]) == 60 for e in refund_events)


# ---------------------------------------------------------------------------
# 26. Freed-pool conservation: partial refund (H2)
# ---------------------------------------------------------------------------

def test_freed_pool_conservation_partial_refund(tmp_path: object) -> None:
    """Same setup, settle actual 130 → actual excess 30, refund 30, freed==70.
    role_part = 160 - 60 = 100.  actual_excess = max(0, 130 - 100) = 30.
    delta = 30 - 60 = -30.  refund 30.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve(
        "r1", 300,
        role_budgets={"a": 100, "b": 100, "c": 100},
    )

    ledger.release_role("r1", "a")  # freed = 100

    hold = ledger.reserve_call("r1", "b", 160)  # draws 60 freed, freed = 40

    ledger.settle(hold, 130)

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    # freed: 40 (after draw) + 30 (refund) = 70
    assert int(row[0]) == 70


# ---------------------------------------------------------------------------
# 27. Freed-pool overshoot draw (H2)
# ---------------------------------------------------------------------------

def test_freed_pool_overshoot_draw(tmp_path: object) -> None:
    """Hold projected 100 (role_part 100, no freed drawn), settle actual 140
    with freed 20 available → freed consumed 20 (best-effort), overshoot
    event present, freed==0, run spent==140.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve(
        "r1", 300,
        role_budgets={"a": 100, "b": 100, "c": 100},
    )

    # Debit role a 80, then release → freed = 20.
    ledger.debit("r1", 80, role="a")
    ledger.release_role("r1", "a")

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 20

    # Hold on role b: projected 100 (no freed drawn, within role budget).
    hold = ledger.reserve_call("r1", "b", 100)

    # Settle actual 140 (overshoot by 40).
    # role_part = 100 - 0 = 100.  actual_excess = max(0, 140 - 100) = 40.
    # delta = 40 - 0 = 40.  consume min(40, 20) = 20 from freed.
    ledger.settle(hold, 140)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 220  # 80 (debit a) + 140 (settle b)

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
        overshoot = rd.execute(
            "SELECT event FROM midnight_oil_spend_ledger "
            "WHERE run_id = 'r1' AND event = 'overshoot'"
        ).fetchall()
    finally:
        rd.close()
    assert int(row[0]) == 0  # freed consumed
    assert len(overshoot) >= 1


# ---------------------------------------------------------------------------
# 28. H1 — migrate existing databases (freed_drawn_cents column)
# ---------------------------------------------------------------------------

def test_schema_migration_adds_freed_drawn_cents(tmp_path: object) -> None:
    """Round-2 databases lack freed_drawn_cents on midnight_oil_call_holds.
    ensure_schema() must add it idempotently; reserve+settle must succeed
    and the default must be 0.
    """
    import duckdb as _duckdb

    db = pathlib.Path(str(tmp_path)) / "test.duckdb"
    con = _duckdb.connect(str(db))
    # Create the exact old table (Round 2 — no freed_drawn_cents).
    con.execute(
        "CREATE TABLE midnight_oil_call_holds ("
        "    hold_id              TEXT PRIMARY KEY,"
        "    run_id               TEXT NOT NULL,"
        "    role                 TEXT NOT NULL,"
        "    projected_max_cents  BIGINT NOT NULL,"
        "    state                TEXT NOT NULL,"
        "    created_at           TIMESTAMP NOT NULL,"
        "    updated_at           TIMESTAMP NOT NULL"
        ")"
    )
    con.close()

    ledger = BudgetLedger(str(db))
    # ensure_schema() must add the missing column + create other tables.
    ledger.ensure_schema()

    ledger.reserve("r1", 300, role_budgets={"r": 300})
    hold = ledger.reserve_call("r1", "r", 100)

    # freed_drawn_cents must be 0 (the column default).
    from runtime.db_lock import connect_read

    rd = connect_read(str(db))
    try:
        row = rd.execute(
            "SELECT freed_drawn_cents FROM midnight_oil_call_holds "
            "WHERE hold_id = ?",
            [hold.hold_id],
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 0

    # Settle must succeed.
    bal = ledger.settle(hold, 80)
    assert bal.spent_cents == 80
    assert bal.held_cents == 0

    # Idempotent: calling ensure_schema() again must not raise.
    ledger.ensure_schema()


# ---------------------------------------------------------------------------
# 29. H2 — concurrent unknowns correlate to their own durable rows
# ---------------------------------------------------------------------------

def test_concurrent_unknowns_correlate_to_own_rows(tmp_path: object) -> None:
    """Two concurrent guarded calls that both fail produce two
    UnknownCallOutcome exceptions, each with a distinct hold_id.
    Resolving one cannot affect the other.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 500, role_budgets={"r": 500})

    exceptions: list[UnknownCallOutcome] = []
    lock = threading.Lock()

    def failing_call(msg: str) -> tuple[str, int]:
        raise RuntimeError(msg)

    def worker(msg: str, projected: int) -> None:
        try:
            ledger.guarded_call(
                "r1", "r", projected,
                lambda: failing_call(msg),
            )
        except UnknownCallOutcome as exc:
            with lock:
                exceptions.append(exc)

    t1 = threading.Thread(target=worker, args=("err-A", 100))
    t2 = threading.Thread(target=worker, args=("err-B", 150))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(exceptions) == 2
    hold_ids = {e.hold.hold_id for e in exceptions}
    assert len(hold_ids) == 2, "hold IDs must be distinct"

    # Each exception's provider_error carries its own message.
    msgs = {str(e.provider_error) for e in exceptions}
    assert msgs == {"err-A", "err-B"}

    # Resolve one — the other must remain 'unknown'.
    exc_a = exceptions[0]
    ledger.resolve_unknown(exc_a.hold.hold_id, 50)

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        states = rd.execute(
            "SELECT hold_id, state FROM midnight_oil_call_holds "
            "WHERE hold_id IN (?, ?)",
            [exc_a.hold.hold_id, exceptions[1].hold.hold_id],
        ).fetchall()
    finally:
        rd.close()
    state_map = {s[0]: s[1] for s in states}
    assert state_map[exc_a.hold.hold_id] == "settled"
    assert state_map[exceptions[1].hold.hold_id] == "unknown"


# ---------------------------------------------------------------------------
# 30. M1 — honest overshoot during unknown reconciliation (covered excess)
# ---------------------------------------------------------------------------

def test_resolve_unknown_overshoot_covered_freed(tmp_path: object) -> None:
    """resolve_unknown(actual > projected) with freed pool covering the
    excess: must append 'reconciled' AND 'overshoot' events, correct
    amounts, freed pool reflects the reconciliation.
    """
    ledger = _ledger(tmp_path)
    def timeout_call() -> tuple[str, int]:
        raise TimeoutError("provider timeout")

    ledger.reserve("r2", 300, role_budgets={"a": 100, "b": 100, "c": 100})
    ledger.release_role("r2", "a")  # freed = 100

    with pytest.raises(UnknownCallOutcome) as exc_info:
        ledger.guarded_call("r2", "b", 50, timeout_call)

    hold_id = exc_info.value.hold.hold_id

    # Resolve with actual 90 > projected 50.
    # role_part = 50 - 0 = 50.  actual_excess = max(0, 90-50) = 40.
    # delta = 40 - 0 = 40.  consume min(40, 100) = 40 from freed → freed = 60.
    # M1: overshoot event must be appended.
    bal = ledger.resolve_unknown(hold_id, 90)
    assert bal.spent_cents == 90
    assert bal.held_cents == 0

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        events = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "WHERE run_id = 'r2' ORDER BY \"at\", entry_id"
        ).fetchall()
        freed_row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations "
            "WHERE run_id = 'r2'"
        ).fetchone()
    finally:
        rd.close()

    event_list = [(e[0], int(e[1])) for e in events]
    # Must have both 'reconciled' and 'overshoot' for the resolve.
    reconciled_events = [e for e in event_list if e[0] == "reconciled"]
    overshoot_events = [e for e in event_list if e[0] == "overshoot"]
    assert len(reconciled_events) >= 1
    assert len(overshoot_events) >= 1
    # Overshoot amount must be the actual (90).
    assert any(e[1] == 90 for e in overshoot_events)

    # freed: 100 (released a) - 40 (consumed) = 60.
    assert int(freed_row[0]) == 60


# ---------------------------------------------------------------------------
# 31. M1 — honest overshoot during unknown reconciliation (uncovered excess)
# ---------------------------------------------------------------------------

def test_resolve_unknown_overshoot_uncovered_freed(tmp_path: object) -> None:
    """resolve_unknown(actual > projected) where freed pool cannot cover
    the full excess: best-effort consume, overshoot event still present,
    freed pool drained to 0.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve(
        "r1", 500,
        role_budgets={"a": 100, "b": 100},
    )

    # Release role a → freed = 100.
    ledger.release_role("r1", "a")

    # Mark a hold on role b unknown.
    def timeout_call() -> tuple[str, int]:
        raise TimeoutError("provider timeout")

    with pytest.raises(UnknownCallOutcome) as exc_info:
        ledger.guarded_call("r1", "b", 50, timeout_call)

    hold_id = exc_info.value.hold.hold_id

    # Resolve with actual 150 > projected 50.
    # role_part = 50 - 0 = 50.  actual_excess = max(0, 150-50) = 100.
    # delta = 100 - 0 = 100.  consume min(100, 100) = 100 → freed = 0.
    bal = ledger.resolve_unknown(hold_id, 150)
    assert bal.spent_cents == 150

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        events = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "WHERE run_id = 'r1' ORDER BY \"at\", entry_id"
        ).fetchall()
        freed_row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations "
            "WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()

    event_list = [(e[0], int(e[1])) for e in events]
    overshoot_events = [e for e in event_list if e[0] == "overshoot"]
    reconciled_events = [e for e in event_list if e[0] == "reconciled"]
    assert len(overshoot_events) >= 1
    assert len(reconciled_events) >= 1
    assert any(e[1] == 150 for e in overshoot_events)

    # freed = 0 (fully consumed).
    assert int(freed_row[0]) == 0


# ---------------------------------------------------------------------------
# 32. M2 — persistence failure during unknown transition: both errors, hold open
# ---------------------------------------------------------------------------

def test_unknown_persistence_failure_preserves_both_errors(
    tmp_path: object,
) -> None:
    """If _mark_hold_unknown's _append_ledger fails, the hold remains open
    (fail closed, transaction rolled back), held balances intact.
    UnknownOutcomePersistenceError contains BOTH the provider error and the
    bookkeeping error, plus the exact CallHold with hold_id.
    """
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    def exploding_call() -> tuple[str, int]:
        raise RuntimeError("boom")

    original_append = ledger._append_ledger  # noqa: SLF001

    def failing_append(*args: object, **kwargs: object) -> None:
        # Permit reservation/hold persistence, then fail precisely while
        # persisting the post-dispatch unknown transition.
        if kwargs.get("event") == "unknown_outcome":
            raise RuntimeError("ledger-fail")
        original_append(*args, **kwargs)

    with (
        patch.object(ledger, "_append_ledger", side_effect=failing_append),
        pytest.raises(UnknownOutcomePersistenceError) as exc_info,
    ):
        ledger.guarded_call("r1", "r", 100, exploding_call)

    exc = exc_info.value

    # Both errors present.
    assert str(exc.provider_error) == "boom"
    assert str(exc.bookkeeping_error) == "ledger-fail"

    # Durable hold ID.
    assert exc.hold.hold_id

    # Hold remains open (transaction rolled back).
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        hold_state = rd.execute(
            "SELECT state FROM midnight_oil_call_holds "
            "WHERE hold_id = ?",
            [exc.hold.hold_id],
        ).fetchone()
    finally:
        rd.close()
    assert hold_state is not None
    assert hold_state[0] == "open"

    # Held balances intact: 100 still held, 0 spent.
    bal = ledger.balance("r1")
    assert bal.held_cents == 100
    assert bal.spent_cents == 0
    assert bal.remaining_cents == 200

    # Hold is still usable: settle succeeds on retry (clean path).
    hold_obj = CallHold(
        hold_id=exc.hold.hold_id,
        run_id="r1",
        role="r",
        projected_max_cents=100,
    )
    bal = ledger.settle(hold_obj, 60)
    assert bal.spent_cents == 60
    assert bal.held_cents == 0


# ---------------------------------------------------------------------------
# Recovered committed regression coverage (tests 11-20)
# ---------------------------------------------------------------------------

def test_audit_trail_complete(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"a": 150, "b": 150})
    ledger.debit("r1", 50, role="a")
    ledger.release_role("r1", "a")

    def call_b() -> tuple[str, int]:
        return ("done", 60)

    ledger.guarded_call("r1", "b", 80, call_b)
    ledger.release("r1")
    bal = ledger.balance("r1")
    assert bal.status == "released"
    assert bal.spent_cents == 110

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "ORDER BY \"at\", entry_id"
        ).fetchall()
    finally:
        rd.close()
    events = [(row[0], int(row[1])) for row in rows]
    event_types = [event for event, _ in events]
    assert event_types[0] == "reserved"
    assert "released" in event_types
    assert event_types[-1] == "released"
    assert sum(amount for event, amount in events if event == "debit") == 110
    allowed_events = {
        "reserved", "hold", "debit", "settle_release", "overshoot",
        "role_released", "exhausted", "released", "halted",
        "freed_refund", "reconciled", "unknown",
    }
    assert set(event_types) <= allowed_events


def test_settle_atomicity(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})
    hold = ledger.reserve_call("r1", "r", 100)

    def failing_append(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected failure mid-settle")

    with (
        patch.object(ledger, "_append_ledger", side_effect=failing_append),
        pytest.raises(RuntimeError, match="injected failure"),
    ):
        ledger.settle(hold, 50)
    bal = ledger.balance("r1")
    assert (bal.spent_cents, bal.held_cents, bal.remaining_cents) == (0, 100, 200)

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        state = rd.execute(
            "SELECT state FROM midnight_oil_call_holds WHERE hold_id = ?",
            [hold.hold_id],
        ).fetchone()
    finally:
        rd.close()
    assert state == ("open",)
    settled = ledger.settle(hold, 50)
    assert (settled.spent_cents, settled.held_cents) == (50, 0)


def test_double_settle_with_second_hold(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})
    first = ledger.reserve_call("r1", "r", 100)
    ledger.reserve_call("r1", "r", 100)
    assert ledger.balance("r1").held_cents == 200
    ledger.settle(first, 80)
    with pytest.raises(RuntimeError, match="already settled or released"):
        ledger.settle(first, 50)
    bal = ledger.balance("r1")
    assert (bal.held_cents, bal.spent_cents) == (100, 80)


def test_freed_headroom_consumed_once(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"a": 100, "b": 100, "c": 100})
    ledger.debit("r1", 40, role="a")
    ledger.release_role("r1", "a")
    ledger.debit("r1", 160, role="b")
    with pytest.raises(BudgetCeilingExceeded):
        ledger.debit("r1", 101, role="c")

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 0


def test_two_holds_vs_role_cap(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 500, role_budgets={"r": 100})
    ledger.reserve_call("r1", "r", 100)
    with pytest.raises(BudgetCeilingExceeded):
        ledger.reserve_call("r1", "r", 100)


def test_reserve_invalid_role_budget_leaves_nothing(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    with pytest.raises(ValueError, match="must be positive"):
        ledger.reserve("r1", 300, role_budgets={"a": 100, "b": 0})
    with pytest.raises(ReservationNotFound):
        ledger.balance("r1")

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        counts = tuple(
            int(rd.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "midnight_oil_reservations",
                "midnight_oil_role_budgets",
                "midnight_oil_spend_ledger",
            )
        )
    finally:
        rd.close()
    assert counts == (0, 0, 0)
    assert ledger.reserve(
        "r1", 300, role_budgets={"a": 100, "b": 100}
    ).status == "reserved"


def test_overshoot_event_atomic_with_spend(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})
    hold = ledger.reserve_call("r1", "r", 50)

    def failing_append(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected failure during overshoot")

    with (
        patch.object(ledger, "_append_ledger", side_effect=failing_append),
        pytest.raises(RuntimeError, match="injected failure"),
    ):
        ledger.settle(hold, 80)
    bal = ledger.balance("r1")
    assert (bal.spent_cents, bal.held_cents, bal.remaining_cents) == (0, 50, 250)
    assert ledger.settle(hold, 80).spent_cents == 80


def test_release_then_settle_impossible(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})
    first = ledger.reserve_call("r1", "r", 100)
    second = ledger.reserve_call("r1", "r", 100)
    ledger._release_hold(first)  # noqa: SLF001
    assert ledger.balance("r1").held_cents == 100
    with pytest.raises(RuntimeError, match="already settled or released"):
        ledger.settle(first, 50)
    ledger.settle(second, 60)
    with pytest.raises(RuntimeError, match="already settled or released"):
        ledger._release_hold(first)  # noqa: SLF001
    bal = ledger.balance("r1")
    assert (bal.held_cents, bal.spent_cents) == (0, 60)


def test_freed_excess_no_double_charge(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"a": 100, "b": 100})
    ledger.release_role("r1", "a")
    ledger.debit("r1", 160, role="b")
    ledger.debit("r1", 10, role="b")
    assert ledger.balance("r1").spent_cents == 170

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 30


def test_release_role_with_open_holds_raises(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 200})
    hold = ledger.reserve_call("r1", "r", 150)
    with pytest.raises(RuntimeError, match=r"open(?: or unknown)? holds"):
        ledger.release_role("r1", "r")
    ledger.settle(hold, 100)
    ledger.release_role("r1", "r")

    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 100

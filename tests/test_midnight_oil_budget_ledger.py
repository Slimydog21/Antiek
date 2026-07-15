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
    ReservationNotFound,
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
# 10. Failed call conservatively charges the projection
# ---------------------------------------------------------------------------

def test_failed_call_charges_projected_maximum(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    def exploding_call() -> tuple[str, int]:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        ledger.guarded_call("r1", "r", 100, exploding_call)

    bal = ledger.balance("r1")
    assert bal.spent_cents == 100
    assert bal.held_cents == 0
    assert bal.remaining_cents == 200

    # Unknown provider outcome is accounted as projected spend, not a release.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "WHERE event = 'debit'"
        ).fetchall()
    finally:
        rd.close()

    assert rows == [("debit", 100)]


def test_billed_timeout_cannot_restore_reusable_budget(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 100, role_budgets={"researcher": 100})
    external_spent_cents = 0

    def billed_then_timed_out() -> tuple[str, int]:
        nonlocal external_spent_cents
        external_spent_cents += 100
        raise TimeoutError("provider accepted request but response timed out")

    with pytest.raises(TimeoutError):
        ledger.guarded_call("r1", "researcher", 100, billed_then_timed_out)

    with pytest.raises(BudgetCeilingExceeded):
        ledger.guarded_call("r1", "researcher", 100, billed_then_timed_out)

    balance = ledger.balance("r1")
    assert external_spent_cents == 100
    assert balance.spent_cents == 100
    assert balance.held_cents == 0
    assert balance.remaining_cents == 0
    assert balance.status == "exhausted"


# ---------------------------------------------------------------------------
# 11. Audit trail complete
# ---------------------------------------------------------------------------

def test_audit_trail_complete(tmp_path: object) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"a": 150, "b": 150})

    # Role a: debit 50, release (frees 100).
    ledger.debit("r1", 50, role="a")
    ledger.release_role("r1", "a")

    # Role b: guarded call (projected 80, actual 60).
    def call_b() -> tuple[str, int]:
        return ("done", 60)

    ledger.guarded_call("r1", "b", 80, call_b)

    # End-of-run release.
    ledger.release("r1")

    bal = ledger.balance("r1")
    assert bal.status == "released"
    assert bal.spent_cents == 110  # 50 + 60

    # Audit trail: every debit amount sums to spent_cents.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        rows = rd.execute(
            "SELECT event, amount_cents FROM midnight_oil_spend_ledger "
            "ORDER BY \"at\", entry_id"
        ).fetchall()
    finally:
        rd.close()

    events = [(r[0], int(r[1])) for r in rows]
    event_types = [e[0] for e in events]

    assert event_types[0] == "reserved"
    assert "released" in event_types
    assert event_types[-1] == "released"

    # Sum of debit amounts == spent_cents.
    debit_sum = sum(amt for evt, amt in events if evt == "debit")
    assert debit_sum == bal.spent_cents
    assert debit_sum <= bal.ceiling_cents

    # G5: closed event-set — only real audit events allowed.
    allowed_events = {
        "reserved", "hold", "debit", "settle_release", "overshoot",
        "role_released", "exhausted", "released", "halted",
    }
    for evt in event_types:
        assert evt in allowed_events, f"unexpected event type: {evt}"


# ---------------------------------------------------------------------------
# 12. Settle atomicity (F1 + F2)
# ---------------------------------------------------------------------------

def test_settle_atomicity(tmp_path: object) -> None:
    """Mid-settle failure rolls back EVERYTHING: balance, held, no sentinel."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    hold = ledger.reserve_call("r1", "r", 100)
    bal_before = ledger.balance("r1")
    assert bal_before.held_cents == 100
    assert bal_before.spent_cents == 0

    # Monkeypatch _append_ledger to fail mid-settle (after UPDATEs).
    def failing_append(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected failure mid-settle")

    with (
        patch.object(ledger, "_append_ledger", side_effect=failing_append),
        pytest.raises(RuntimeError, match="injected failure"),
    ):
        ledger.settle(hold, 50)

    # NOTHING persisted: balance, held, spent all unchanged.
    bal_after = ledger.balance("r1")
    assert bal_after.spent_cents == 0
    assert bal_after.held_cents == 100
    assert bal_after.remaining_cents == 200

    # Hold row in midnight_oil_call_holds is still 'open' (rolled back).
    from runtime.db_lock import connect_read

    db = ledger._db_path  # noqa: SLF001
    rd = connect_read(db)
    try:
        hold_state = rd.execute(
            "SELECT state FROM midnight_oil_call_holds "
            "WHERE hold_id = ?",
            [hold.hold_id],
        ).fetchone()
    finally:
        rd.close()
    assert hold_state is not None
    assert hold_state[0] == "open"

    # Clean retry succeeds.
    bal_settled = ledger.settle(hold, 50)
    assert bal_settled.spent_cents == 50
    assert bal_settled.held_cents == 0


# ---------------------------------------------------------------------------
# 13. Double-settle with second hold (F7)
# ---------------------------------------------------------------------------

def test_double_settle_with_second_hold(tmp_path: object) -> None:
    """Settling the same hold twice raises; co-outstanding hold untouched."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    h1 = ledger.reserve_call("r1", "r", 100)
    ledger.reserve_call("r1", "r", 100)  # co-outstanding hold

    bal = ledger.balance("r1")
    assert bal.held_cents == 200

    # Settle h1 normally.
    ledger.settle(h1, 80)

    # Settle h1 again → RuntimeError.
    with pytest.raises(RuntimeError, match="already settled or released"):
        ledger.settle(h1, 50)

    # H2's hold is untouched: held_cents reflects h2's 100 still held.
    bal = ledger.balance("r1")
    assert bal.held_cents == 100
    assert bal.spent_cents == 80


# ---------------------------------------------------------------------------
# 14. Freed headroom consumed once (F3)
# ---------------------------------------------------------------------------

def test_freed_headroom_consumed_once(tmp_path: object) -> None:
    """Freed pool is atomically consumed; cannot be double-spent."""
    ledger = _ledger(tmp_path)
    ledger.reserve(
        "r1", 300,
        role_budgets={"a": 100, "b": 100, "c": 100},
    )

    # A releases 60¢ → freed = 60.
    ledger.debit("r1", 40, role="a")
    ledger.release_role("r1", "a")

    # B draws 60¢ excess from freed → freed = 0.
    ledger.debit("r1", 160, role="b")

    bal = ledger.balance("r1")
    assert bal.spent_cents == 200

    # C trying 1¢ excess → freed pool empty → raises.
    with pytest.raises(BudgetCeilingExceeded):
        ledger.debit("r1", 101, role="c")

    # freed_cents == 0.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 0


# ---------------------------------------------------------------------------
# 15. Two holds vs one role cap (F4)
# ---------------------------------------------------------------------------

def test_two_holds_vs_role_cap(tmp_path: object) -> None:
    """Role sub-cap enforced via held_cents: two holds for same role capped."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 500, role_budgets={"r": 100})

    # First hold of 100¢ uses the full role budget.
    ledger.reserve_call("r1", "r", 100)

    # Second hold of 100¢ exceeds role budget (no freed available).
    with pytest.raises(BudgetCeilingExceeded):
        ledger.reserve_call("r1", "r", 100)


# ---------------------------------------------------------------------------
# 16. Reserve with invalid role budget leaves nothing (F5)
# ---------------------------------------------------------------------------

def test_reserve_invalid_role_budget_leaves_nothing(tmp_path: object) -> None:
    """Invalid role budget raises ValueError; DB has no partial state."""
    ledger = _ledger(tmp_path)

    with pytest.raises(ValueError, match="must be positive"):
        ledger.reserve("r1", 300, role_budgets={"a": 100, "b": 0})

    # No reservation row.
    with pytest.raises(ReservationNotFound):
        ledger.balance("r1")

    # No role rows, no ledger rows.
    from runtime.db_lock import connect_read

    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        res_count = rd.execute(
            "SELECT COUNT(*) FROM midnight_oil_reservations"
        ).fetchone()
        role_count = rd.execute(
            "SELECT COUNT(*) FROM midnight_oil_role_budgets"
        ).fetchone()
        ledger_count = rd.execute(
            "SELECT COUNT(*) FROM midnight_oil_spend_ledger"
        ).fetchone()
    finally:
        rd.close()
    assert int(res_count[0]) == 0
    assert int(role_count[0]) == 0
    assert int(ledger_count[0]) == 0

    # Corrected retry succeeds.
    ledger.reserve("r1", 300, role_budgets={"a": 100, "b": 100})
    bal = ledger.balance("r1")
    assert bal.ceiling_cents == 300
    assert bal.status == "reserved"


# ---------------------------------------------------------------------------
# 17. Overshoot event atomic with spend (F1)
# ---------------------------------------------------------------------------

def test_overshoot_event_atomic_with_spend(tmp_path: object) -> None:
    """Injected failure during overshoot settle → nothing persisted."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    hold = ledger.reserve_call("r1", "r", 50)
    bal_before = ledger.balance("r1")
    assert bal_before.held_cents == 50

    # Inject failure after the UPDATE would run (in _append_ledger).
    def failing_append(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected failure during overshoot")

    with (
        patch.object(ledger, "_append_ledger", side_effect=failing_append),
        pytest.raises(RuntimeError, match="injected failure"),
    ):
        ledger.settle(hold, 80)  # actual > projected

    # Nothing persisted: spend not recorded without its ledger row.
    bal_after = ledger.balance("r1")
    assert bal_after.spent_cents == 0
    assert bal_after.held_cents == 50
    assert bal_after.remaining_cents == 250

    # Clean retry succeeds.
    bal_settled = ledger.settle(hold, 80)
    assert bal_settled.spent_cents == 80
    assert bal_settled.status == "exhausted" or bal_settled.remaining_cents >= 0


# ---------------------------------------------------------------------------
# 18. Release-then-settle impossible (F7)
# ---------------------------------------------------------------------------

def test_release_then_settle_impossible(tmp_path: object) -> None:
    """Released hold cannot be settled; co-outstanding hold band intact."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 300})

    # A call whose call() raises → hold released.
    h1 = ledger.reserve_call("r1", "r", 100)
    h2 = ledger.reserve_call("r1", "r", 100)

    # Release h1 (simulate failed call).
    ledger._release_hold(h1)  # noqa: SLF001

    bal = ledger.balance("r1")
    assert bal.held_cents == 100  # only h2 still held
    assert bal.spent_cents == 0

    # Attempting to settle the released h1 → RuntimeError.
    with pytest.raises(RuntimeError, match="already settled or released"):
        ledger.settle(h1, 50)

    # Balances untouched.
    bal = ledger.balance("r1")
    assert bal.held_cents == 100
    assert bal.spent_cents == 0

    # H2's band is intact.
    ledger.settle(h2, 60)
    bal = ledger.balance("r1")
    assert bal.held_cents == 0
    assert bal.spent_cents == 60

    # Double-release of h1 → RuntimeError (idempotent check).
    with pytest.raises(RuntimeError, match="already settled or released"):
        ledger._release_hold(h1)  # noqa: SLF001

    bal_after = ledger.balance("r1")
    assert bal_after.held_cents == 0  # not double-decremented


# ---------------------------------------------------------------------------
# 19. Freed-pool excess: no double-charge on overdrawn role (G2)
# ---------------------------------------------------------------------------

def test_freed_excess_no_double_charge(tmp_path: object) -> None:
    """Role that previously overdrawn has role_remaining < 0.  max(0, ...)
    prevents re-charging the deficit from the freed pool."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"a": 100, "b": 100})

    # A releases 100 → freed = 100.
    ledger.release_role("r1", "a")

    # B draws 160 (100 own + 60 freed).  freed = 40.
    ledger.debit("r1", 160, role="b")
    # Verify intermediate state.
    from runtime.db_lock import connect_read
    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 40

    # B draws 10 more.  With the bug, role_remaining = 100-160-0 = -60,
    # so excess = 10 - (-60) = 70, draining freed to -30 (or raising).
    # With the fix, available = max(0, 100-160-0) = 0, excess = 10.
    ledger.debit("r1", 10, role="b")

    bal = ledger.balance("r1")
    assert bal.spent_cents == 170  # 160 + 10

    # freed_cents == 30 (40 - 10), not overdrawn.
    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 30


# ---------------------------------------------------------------------------
# 20. release_role with open holds raises; settle-then-release succeeds (G3)
# ---------------------------------------------------------------------------

def test_release_role_with_open_holds_raises(tmp_path: object) -> None:
    """release_role raises RuntimeError if the role has any open holds."""
    ledger = _ledger(tmp_path)
    ledger.reserve("r1", 300, role_budgets={"r": 200})

    # Place a hold that won't be settled yet.
    hold = ledger.reserve_call("r1", "r", 150)

    # release_role while hold is open → raises.
    with pytest.raises(RuntimeError, match="open holds"):
        ledger.release_role("r1", "r")

    # Settle the hold.
    ledger.settle(hold, 100)

    # Now release_role succeeds.
    bal = ledger.release_role("r1", "r")
    # Unspent = 200 - 100 - 0 = 100, freed.
    assert bal.remaining_cents >= 0

    # Verify freed_cents is correct.
    from runtime.db_lock import connect_read
    rd = connect_read(ledger._db_path)  # noqa: SLF001
    try:
        row = rd.execute(
            "SELECT freed_cents FROM midnight_oil_reservations WHERE run_id = 'r1'"
        ).fetchone()
    finally:
        rd.close()
    assert int(row[0]) == 100

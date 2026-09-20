# RED-PROOF-LOG — Midnight Oil Budget Ledger

**Date:** 2026-07-10  
**Branch:** mo/budget-ledger-spr05  
**Commit:** working tree (not committed)

## Purpose

Prove that the ceiling guard in `budget_ledger.py` is load-bearing — a test
that has never seen red is theater.  We temporarily neutered the guard, ran
tests 1 and 5, confirmed they FAIL (the run overspends / the spy sees the
call fire), restored the guard, and confirmed green.

---

## Guard neutered

Two changes in `substrate/midnight_oil/budget_ledger.py`:

### 1. `debit()` — ceiling check removed from conditional UPDATE

**Before (lines ~303–314):**
```python
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
```

**Neutered:**
```python
# [RED-PROOF NEUTERED] ceiling check removed for red-proof test.
hit = ctx.execute(
    "UPDATE midnight_oil_reservations SET "
    "spent_cents = spent_cents + ?, "
    "updated_at = CURRENT_TIMESTAMP "
    "WHERE run_id = ? "
    "AND status = 'reserved' "
    "RETURNING 1",
    [amount_cents, run_id],
).fetchone()
```

### 2. `reserve_call()` — ceiling check removed from conditional UPDATE

**Before (lines ~370–379):**
```python
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
```

**Neutered:**
```python
# [RED-PROOF NEUTERED] ceiling check removed for red-proof test.
hit = ctx.execute(
    "UPDATE midnight_oil_reservations SET "
    "held_cents = held_cents + ?, "
    "updated_at = CURRENT_TIMESTAMP "
    "WHERE run_id = ? "
    "AND status = 'reserved' "
    "RETURNING 1",
    [projected_max_cents, run_id],
).fetchone()
```

### 3. `_check_role_budget()` — entire body short-circuited

**Before:** full role budget + freed_cents check.  
**Neutered:** early `return` after the docstring.

---

## Test run with guard neutered

**Command:**
```
/Users/slimydog/Antiek/platform/.venv/bin/python -m pytest \
    tests/test_midnight_oil_budget_ledger.py::test_hard_ceiling_under_overspend \
    tests/test_midnight_oil_budget_ledger.py::test_zero_overshoot_spy \
    -v
```

**Observed failures (verbatim tail):**

```
=================================== FAILURES ===================================
______________________ test_hard_ceiling_under_overspend _______________________

tmp_path = PosixPath('.../test_hard_ceiling_under_oversp0')

    def test_hard_ceiling_under_overspend(tmp_path: object) -> None:
        ledger = _ledger(tmp_path)
        ledger.reserve("r1", 300)
    
        ledger.debit("r1", 120)
        ledger.debit("r1", 120)
    
>       with pytest.raises(BudgetCeilingExceeded) as exc_info:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE BudgetCeilingExceeded

tests/test_midnight_oil_budget_ledger.py:43: Failed

___________________________ test_zero_overshoot_spy ____________________________

tmp_path = PosixPath('.../test_zero_overshoot_spy0')

    def test_zero_overshoot_spy(tmp_path: object) -> None:
        ledger = _ledger(tmp_path)
        ledger.reserve("r1", 300, role_budgets={"researcher": 300})
        ...
        # Now remaining = 300 - 150 = 150.  Projected 200 > 150 → raises.
>       with pytest.raises(BudgetCeilingExceeded):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE BudgetCeilingExceeded

tests/test_midnight_oil_budget_ledger.py:165: Failed

=========================== short test summary info ============================
FAILED tests/test_midnight_oil_budget_ledger.py::test_hard_ceiling_under_overspend
FAILED tests/test_midnight_oil_budget_ledger.py::test_zero_overshoot_spy
============================== 2 failed in 0.52s ==============================
```

### What the failures prove

| Test | Expected | Observed (neutered) | Meaning |
|------|----------|---------------------|---------|
| test_hard_ceiling_under_overspend | 3rd debit of 120¢ raises BudgetCeilingExceeded (remaining=60¢) | 3rd debit SUCCEEDS; spent goes to 360¢, 60¢ over the 300¢ ceiling | Without the conditional WHERE `ceiling - spent - held >= amount`, the ceiling is a suggestion, not a limit |
| test_zero_overshoot_spy | 4th guarded_call with projected 200¢ raises BEFORE the spy fires | 4th call SUCCEEDS; spy fires (call_count=4); spend exceeds ceiling | Without the ceiling gate on `reserve_call`, the zero-overshoot mechanism is bypassed and the provider is dispatched when the budget cannot cover it |

---

## Guard restored + green confirmation

All three neutered code sites restored to original form.  Full suite re-run:

**Command:**
```
/Users/slimydog/Antiek/platform/.venv/bin/python -m pytest \
    tests/test_midnight_oil_budget_ledger.py -q
```

**Output:**
```
11 passed in 5.04s
```

---

## Conclusion

The ceiling guard (`ceiling_cents - spent_cents - held_cents >= ?` in the
conditional WHERE clause) is **load-bearing**.  Removing it allows:

1. Direct debits to exceed the operator's approved ceiling.
2. `reserve_call` to place holds that the budget cannot cover, dispatching
   provider calls that will overspend.

Both tests that passed with the guard in place fail without it.  The guard
is not theater.

---

## F1 red-proof: explicit BEGIN/COMMIT transaction wrapper

**Date:** 2026-07-10 (fix-round-1)  
**What:** prove the `_txn(ctx)` transaction wrapper is load-bearing for settle
atomicity (F1+F2).

### Neutered

Commented out the `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK` in `_txn()`
so every write operation runs in DuckDB autocommit (each statement is an
independent commit):

```python
@contextlib.contextmanager
def _txn(self, ctx: Any) -> Generator[None]:
    # [RED-PROOF NEUTERED] transaction wrapper removed.
    # ctx.execute("BEGIN TRANSACTION")
    try:
        yield
    except Exception:
        # ctx.execute("ROLLBACK")
        raise
    # else:
    #     ctx.execute("COMMIT")
```

### Test run with wrapper neutered

**Command:**
```
/Users/slimydog/Antiek/platform/.venv/bin/python -m pytest \
    tests/test_midnight_oil_budget_ledger.py::test_settle_atomicity \
    -v
```

**Observed failure (verbatim tail):**

```
FAILED tests/test_midnight_oil_budget_ledger.py::test_settle_atomicity
  - assert bal_after.spent_cents == 0  (was 50 — partial commit!)
  - assert bal_after.held_cents == 100  (was 0 — partial commit!)
```

Without the transaction wrapper, the `UPDATE` that decrements `held_cents`
and increments `spent_cents` commits autocommit-style even though the
subsequent `_append_ledger` call fails.  The result: a settle that crashed
mid-way left the balance in an inconsistent state (spent incremented, held
decremented, no ledger row, no sentinel).

### Wrapper restored + green confirmation

Transaction wrapper restored.  Full suite re-run:

**Command:**
```
/Users/slimydog/Antiek/platform/.venv/bin/python -m pytest \
    tests/test_midnight_oil_budget_ledger.py -q
```

**Output:**
```
18 passed in 5.78s
```

### What this proves

The `_txn(ctx)` wrapper (BEGIN/COMMIT/ROLLBACK) is **load-bearing**.
Without it, a mid-settle failure leaves `spent_cents` and `held_cents` in
an inconsistent state — the UPDATE committed but the sentinel did not,
enabling double-settle and phantom spend.  The wrapper is not theater.

---

## Round-2 addendum — hold-state machine (persisted holds) proven load-bearing

**Date:** 2026-07-10 (orchestrator-run demonstration)

FIX-ROUND-2 replaced the ledger-row sentinels with a persisted
`midnight_oil_call_holds` state machine (open → settled|released), arbitered by a
conditional `UPDATE ... WHERE hold_id = ? AND state = 'open' RETURNING 1` plus an
in-transaction pre-check.

**Neutered:** both state pre-checks (`if _state != "open"` → `if False`) and settle's
arbiter condition (`AND state = 'open'` removed from the UPDATE).

**Observed red (verbatim tail):**
```
FAILED tests/test_midnight_oil_budget_ledger.py::test_double_settle_with_second_hold - Failed: DID NOT RAISE RuntimeError
FAILED tests/test_midnight_oil_budget_ledger.py::test_release_then_settle_impossible - Failed: DID NOT RAISE RuntimeError
2 failed in 0.43s
```

**Restored + green:** full suite `20 passed in 5.94s`.

Without the state machine, a hold can be settled twice and a released hold can still be
settled — phantom spend consuming a co-outstanding hold's band. The guard is not theater.

# FIX ROUND 2 — durable hold identity is mandatory

Round 1 improved transactions, role-held accounting, released-headroom consumption, and
terminal sentinels. Its 18 tests pass. The implementation is still REJECTED because a
`CallHold` is caller-supplied data with no durable record binding its identity to the
reservation it claims to represent.

## Confirmed critical exploit

After reserving a real 100-cent hold, construct:

```python
CallHold("attacker", "run", "r", 100)
```

`settle(forged, 1)` succeeds, drops aggregate held cents to zero, and records spend. The
legitimate hold subsequently raises because its aggregate band was stolen. This was
observed against the Round 1 implementation, not inferred.

## Required design

Add a durable hold table:

```sql
midnight_oil_call_holds(
  hold_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  role TEXT NOT NULL,
  projected_max_cents BIGINT NOT NULL,
  state TEXT NOT NULL,              -- active|settled|released
  actual_cents BIGINT,
  created_at TIMESTAMP NOT NULL,
  terminal_at TIMESTAMP
)
```

- `reserve_call` inserts the exact hold row in the same explicit transaction as aggregate
  and role `held_cents` increments and the audit event.
- `settle` must load/transition by `hold_id` and require the durable row's `run_id`, `role`,
  and `projected_max_cents` to exactly match the supplied dataclass. A missing or mismatched
  hold fails closed without changing any state.
- The arbiter is a conditional transition `active -> settled` for that exact hold inside the
  transaction. Duplicate or released holds fail before aggregate mutation.
- `_release_hold` uses the same exact identity checks and conditional `active -> released`
  transition. A repeated release is idempotent only when the durable identity also matches;
  a forged mismatch is never treated as an innocent retry.
- Terminal state belongs in this table. Spend-ledger rows remain append-only audit events,
  not identity/authentication records. Remove or stop relying on synthetic entry-id
  sentinels for correctness.
- Add `reconcile_active_holds(run_id, *, older_than: datetime | None = None)` (or an equally
  explicit API) that enumerates durable active holds and conservatively releases them in
  one serialized transaction, returning the resulting balance. This is operator/recovery
  machinery; it must never guess that money was spent. The worker integration may instead
  choose an absorb-as-spent policy at its boundary, but the ledger must expose active hold
  identity so that decision is possible.
- `release(run_id)` must fail closed while active holds exist; it may not erase or strand
  them.

## Required outcome tests

19. Forged hold ID with otherwise correct fields cannot settle or release; real hold remains.
20. Real hold ID with forged run, role, or projected amount cannot settle/release; test each.
21. Durable hold survives a fresh `BudgetLedger` instance and settles exactly once.
22. Released hold cannot settle after process restart.
23. `release(run_id)` refuses while any durable hold is active.
24. Reconciliation releases only selected active holds, preserves other runs, and is
    idempotent; aggregate and role held cents equal the sum of durable active holds.
25. Inject a failure between hold-row transition and aggregate/audit updates; rollback leaves
    the durable hold active and every aggregate unchanged, then retry succeeds once.

Add an invariant helper used by tests (SQL is fine): for every run,
`reservations.held_cents == SUM(active projected_max_cents)` and for every role,
`role_budgets.held_cents == SUM(active projected_max_cents for that role)`.

Run the existing 18 tests plus 19–25, strict mypy, Ruff, declared-bar gates, and a red-proof
that temporarily removes the durable identity match and observes test 19 fail. Do not commit.

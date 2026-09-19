# FIX ROUND 4 — Round 3 adversarial rejection

The current 28-test Round 3 diff is REJECTED by an independent Codex review. Preserve its
typed unknown-outcome and freed-pool work, then fix all four findings below.

## H1 — migrate existing databases

`CREATE TABLE IF NOT EXISTS` does not add `freed_drawn_cents` to a Round-2 hold table.
`ensure_schema()` must perform an idempotent, serialized schema migration using
`ALTER TABLE midnight_oil_call_holds ADD COLUMN IF NOT EXISTS freed_drawn_cents BIGINT
NOT NULL DEFAULT 0`. Add a test that first creates the exact old table, calls
`ensure_schema()`, then reserves/settles a hold successfully and verifies the column/default.

## H2 — unknown exceptions must carry exact durable correlation

Do not make callers query an arbitrary `state='unknown'` row. Add an exported typed wrapper,
for example `UnknownCallOutcome(RuntimeError)`, with public `hold: CallHold` and
`provider_error: Exception` attributes and exception chaining. On an ordinary exception:

1. transition the exact hold to unknown;
2. raise `UnknownCallOutcome(hold, provider_error) from provider_error`.

The durable hold ID must therefore survive concurrency and process boundaries. Update tests
and APIs so reconciliation always uses `exc.hold.hold_id`. Add a concurrent/two-unknown test
proving each exception correlates to its own durable row and resolving one cannot affect the
other.

## M1 — honest overshoot during unknown reconciliation

`resolve_unknown(actual > projected)` must append the same `overshoot` truth event as normal
settlement in addition to `reconciled`, after applying freed-pool reconciliation. Test both
covered and uncovered freed-pool excess, balance truth, and event amounts.

## M2 — never mask the provider failure with bookkeeping failure

If transition-to-unknown persistence fails, the hold remains open/fail-closed. Raise a typed
`UnknownOutcomePersistenceError` (or enrich `UnknownCallOutcome`) containing BOTH the
original provider exception and bookkeeping exception, with the exact `CallHold`; do not
silently substitute one unrelated exception for the other. The caller must retain enough
information to reconcile the durable open hold. Add an injected `_append_ledger` failure
test proving rollback leaves state `open`, held balances intact, and the raised diagnostic
contains both errors and the hold ID.

## Gates

Keep all 28 tests green and add the required outcome tests. Run focused pytest, strict mypy,
Ruff, declared-bar mypy/Ruff, and update the red-proof decision doc if a new mutation proof
is needed. Do not commit. Report exact outputs and deviations.

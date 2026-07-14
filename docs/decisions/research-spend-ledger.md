# SPR-02: Durable research spend ledger

**Date:** 2026-07-13
**Status:** implemented
**Owner:** research execution

## Decision

Research execution owns a standard-library `sqlite3` authority and evidence
ledger. It is deliberately separate from Midnight Oil's DuckDB role-allocation
ledger. The shared contract is behavioral: both fail closed before a provider
call when the approved ceiling has no headroom.

Midnight Oil couples its ledger to role budgets, a freed pool, and its guarded
call lifecycle. Extracting those concepts would broaden this sprint and weaken
both ownership boundaries. A future shared protocol may sit above the ledgers;
their storage cores remain independent.

## Authority model

All authority values are bounded integer USD cents. Cumulative observed provider
spend is canonical nonnegative decimal text and is added as a Python integer, so
provider evidence remains exact beyond SQLite's signed 64-bit range.

Every mutation opens a new connection and executes under `BEGIN IMMEDIATE` with
foreign keys enabled, a 30-second busy timeout, WAL, and `synchronous=FULL`.
Reservation authority is one conditional statement:

```sql
UPDATE research_spend_runs
SET held_cents = held_cents + :projected
WHERE run_id = :run_id
  AND status = 'active'
  AND ceiling_breached = 0
  AND :projected <= ceiling_cents - authorized_spent_cents - held_cents
RETURNING held_cents;
```

The run is bound to owner, session, plan digest, approval revision, and USD.
Reservation intent additionally binds the seam, provider, model, operation and
projection digests, rate snapshot, projected maximum, and provider idempotency
key. Immutable command rows bind every command key to its kind, scope, canonical
intent, intent hash, and original result. An exact replay returns that result;
changed intent fails.

## State machines

Paid work:

```text
reserved -> dispatch_possible -> unknown -> settled
reserved -> dispatch_possible -> settled
reserved -> released
dispatch_possible|unknown -> released only with authoritative provider evidence
```

The dispatch marker is durable before any provider send. A reserved hold is
provably unsent and may be released. Dispatch-possible and unknown holds retain
their full projection until authoritative settlement or no-charge evidence.
Terminal holds cannot be mutated through the API.

Zero-cost local work:

```text
prepared -> completed|failed
```

Zero-cost attempts are replay-bound but never change monetary balances.

Run lifecycle:

```text
active -> ceiling_breached
active|ceiling_breached -> closed_unresolved|closed_reconciled
closed_unresolved -> closed_reconciled
```

Settlement authorizes `min(actual, projected)`, records the full actual amount as
observed provider evidence, and releases the full hold. An above-hold actual sets
a permanent breach flag and freezes new work. Closing atomically releases only
reserved holds, fails prepared local attempts, retains ambiguous paid holds, and
advances to reconciled only after every ambiguous hold is resolved.

## Persistence

Schema version 2 uses five STRICT tables: runs, paid holds, zero-cost attempts,
immutable commands, and append-only events. Database CHECK constraints enforce
USD, explicit `hard_ceiling` mode, canonical observed values, bounded balances,
run/hold terminal consistency, and `authorized + held <= ceiling`. Triggers
reject command/event update or deletion. Reads verify persisted intent JSON
against its hash and material columns.

`application_id=0x52535044` and `user_version=2` identify the database. Initial
schema creation is one transaction. Version 1 migrates atomically by adding the
explicit mode binding with the only historically valid value, `hard_ceiling`.
Failure after any individual DDL statement rolls back to version zero with no
research tables.

## Verification contract

The focused suite proves:

- exactly one winner when 100 independent connections race for the final cent;
- exact replay and changed-intent rejection for paid and zero-cost work;
- stale binding, illegal transition, malformed storage, and terminal rejection;
- retained ambiguity across restart and conservative close behavior;
- above-hold breach, permanent freeze, and exact cumulative observed overflow;
- process death at each reservation and settlement transaction boundary;
- post-commit replay without duplicate authorization or evidence;
- migration rollback at every DDL boundary and immutable audit records.

## Follow-on

SPR-03 must place a dispatch gateway in front of every research provider seam.
Its required order is project, reserve, persist dispatch-possible, send with the
persisted provider idempotency key, then settle or mark unknown. This ledger does
not by itself prevent a caller from bypassing that gateway.

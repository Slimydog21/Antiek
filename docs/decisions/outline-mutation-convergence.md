# Outline mutation convergence

Status: executable decision for Write outline composition

## Problem

`move_block` and `remove_block` mutate DuckDB before appending their typed
trajectory event. A process or filesystem failure after the commit leaves the
composition state ahead of its audit trail. Retrying a move then observes the
destination as its origin, while retrying a removal returns a false 404 because
the row is already gone.

An event-only receipt cannot close this gap: the same failure can lose both the
audit event and its receipt, after which the original move endpoints no longer
exist in the live row.

## Decision

Every move and removal is identified by a caller-supplied `Idempotency-Key`.
The command and its exact typed event envelope are committed atomically with
the outline mutation in `outline_block_commands`.

The event envelope has a stable event id derived from the command id and is
appended strictly after commit. A replay with the same command id and canonical
request fingerprint never mutates state again; it republishes the stored event
only when that stable event id is absent. Reusing a command id for different
material is a conflict.

Different command ids always represent different user intentions, including a
later intentional move to a location used by an earlier command. Target-state
hashing without an explicit command id is forbidden because it would collapse
those distinct edits.

## Ordering

```text
validate command id and request fingerprint
  → begin DuckDB transaction
  → resolve current endpoints
  → construct exact typed event envelope
  → mutate outline row + insert immutable command receipt
  → commit
  → append stored event envelope once
  → return success
```

On replay:

```text
load command by id
  → reject fingerprint drift
  → append stored envelope only if its event id is absent
  → return the original success without reapplying the mutation
```

## Crash behavior

- Before commit: neither mutation nor command exists.
- After commit and before append: the mutation and exact event envelope are
  durable; the same request repairs the event.
- After append and before the response: the same request finds the stable event
  id and does not append a second logical event.
- A new removal command for an absent block remains 404. A replay of the
  command that removed it remains successful.
- Historical gaps created before this contract are not reconstructed from
  current state because doing so would fabricate prior endpoints.

## Storage and compatibility

`outline_block_commands` stores the immutable command id, request fingerprint,
operation, block id, investigation id, event id, full validated event JSON, and
creation time. It is created both by the graph schema and idempotently at the
write boundary so an existing database that takes the schema sentinel fast path
still receives the table before its first mutation.

The existing moved/removed payload shapes and action types do not change. The
stable event id supplies command identity without forcing a typed-event or
TypeScript code-generation migration.

The HTTP response bodies and success status codes remain unchanged. Move and
delete requests without a valid `Idempotency-Key` are rejected before opening a
write transaction.

## Required red proofs

- A transaction failure leaves both the outline row and command table
  unchanged.
- An append failure after a move commit is repaired by replay with the original
  `from_*` and `to_*` fields and one logical event.
- An append failure after a removal commit replays as success rather than 404
  and emits the original section id once.
- Reusing a command id with a different target, operation, block,
  investigation, or parent event conflicts without mutation.
- Different command ids for sequential moves remain distinct, even when a
  later move reuses an earlier destination.
- A replay after subsequent moves or deletion never rewinds current state.
- Existing databases create the command table without data loss.
- Raw DuckDB connections remain rejected.

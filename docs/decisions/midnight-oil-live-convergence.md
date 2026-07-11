# Midnight Oil live convergence

Status: executable decision for parent SPR-06

## Decision

There is one live execution chain:

```text
authenticated owner
  → signed, owner/job/operation/config/ceiling-bound spend consent
  → atomic consent claim
  → durable enqueue-once operation
  → generation-fenced worker lease
  → idempotent paid step
  → BudgetLedger projected hold
  → provider call
  → returned-result checkpoint
  → actual-cost settlement
  → terminal authority transition
  → idempotent HTML + twin deposit
```

`/research/midnight-oil/execute` remains the permanent synthetic oracle. It
must never switch to live mode: that endpoint has no owner-bound consent,
durable operation, lease generation, paid-step idempotency, restart
checkpoint, or unknown-outcome reconciliation.

The parent SPR-06 instruction to branch inside `execute_midnight_oil` is
therefore superseded. Live provider and retrieval behavior is an
`IdempotentStepFn` constructed only after `lease_authorized_operation` and run
only by `run_leased_worker_iteration` under `OperationQueue.run_fenced`.

## Budget ordering

The accepted ordering is:

```text
reserve projected maximum → dispatch → persist returned checkpoint
→ settle actual cost
```

It replaces the parent's unsafe `check → dispatch → debit` sequence. A
post-dispatch debit cannot prevent overshoot and loses the difference between
provably-not-dispatched and unknown outcomes. `BudgetLedger.guarded_call`
retains the hold on ambiguity and the durable authority moves to
`FAILED_RECONCILE`; it never silently retries a possibly billed request.

The worker owns this ledger interaction. Live adapters must return observed
`DispatchResult.cost_usd`; they must not maintain a second balance or debit
again.

## Provider idempotency prerequisite

Every paid step already has a stable
`provider_idempotency_key(operation_id, step_index)`. Before production live
dispatch, that key must cross the router boundary. Providers that cannot accept
an idempotency key must fail before network I/O. OpenAI-compatible transports
carry it as `Idempotency-Key`; unsupported transports remain unavailable to
Midnight Oil live work.

An OpenAI-compatible wire shape is not evidence of deduplication. The generic
adapter defaults `idempotency_guaranteed=False`; a server-owned plan resolver
may include an endpoint only after the operator verifies that exact provider
contract. As of this decision, the checked-in default providers do not assert
that guarantee, so production live-plan creation remains unavailable rather
than guessing.

The plan resolver also signs the exact route chain, pricing, output cap,
conservative input-byte cap, projected maximum, and source policy into the
consent configuration. The router refuses config drift before network I/O.
Input is byte-capped before dispatch; using bytes as the token upper bound is
conservative because a tokenizer cannot consume more tokens than the encoded
byte count.

## Retrieval scope

The existing `RetrievalSubstrate` searches the Antiek corpus. It does not
perform arXiv, Substack, or web network retrieval and its result rows do not
contain canonical external URLs. SPR-06 therefore supports
`operator_corpus` only, producing content-hashed internal source receipts from
document/chunk provenance. External source policies remain explicitly blocked
until their connector contracts produce canonical source receipts.

Retrieval executes inside the fenced paid step. Untrusted source text is data,
not instructions, and must be delimited in prompts and escaped in HTML.

## Persistence

`deposit_job_results` is the canonical HTML/twin materialization path. Paid
outputs and their route/source evidence must be durable before ledger
settlement so a crash after provider return cannot force redispatch. Deposit
must consume those exact checkpoints idempotently; it must not fabricate a
generic replacement.

The durable job carries `deposit_state=pending|complete` and the completed
document id. Provider settlement/terminalization precedes deposit, so a crash
in that window is recovered by the deposit-only `resume_terminal_deposit`
path from exact step evidence; it can never make the paid step dispatchable
again.

Graph projection is downstream of durable evidence. A deliverable row alone
is not a stored HTML asset and must not justify `graph_mutated=True` or
`persisted=True`.

This change is live-substrate readiness, not a production enablement claim.
Deployment still needs a verified provider capability and a worker launcher
that supplies the server plan resolver, durable queue consumer, retrieval
substrate, and persistent engagement store. DuckDB knowledge-graph projection
and its effect receipts remain a later parent SPR-06 closure item.

## Required red proofs

- Consent without a queue lease makes zero retrieval/provider calls.
- Foreign owner, drifted job/operation/config/ceiling, stale generation, and
  expired lease all make zero calls.
- Two workers yield one provider idempotency key and one paid call.
- A provider lacking idempotency support fails before network I/O.
- A projected hold larger than remaining budget prevents the call.
- Timeout/lost response retains an unknown hold and cannot replay.
- Provider return followed by crash is recovered from the checkpoint without
  provider replay.
- Unsupported external retrieval policy is blocked honestly.
- Source/route evidence survives restart and appears in the HTML/twin deposit.
- Synthetic execution never constructs a live adapter or writes a graph row.
- No consent token, API key, prompt secret, or raw provider error reaches logs,
  durable state, errors, or HTML.

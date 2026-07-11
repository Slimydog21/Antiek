# Midnight Oil live-execution seams

This is the contract of record for the seven closed Midnight Oil adapter
boundaries. `seams.py` makes the boundaries callable and honestly inert; it
does not authorize spend, retrieval, persistence, or mutation. Every default
adapter performs no I/O and either raises an authorization error or returns an
empty result carrying a blocked reason.

The catalog is closed by `contracts.ADAPTER_KEYS` and an executable
completeness assertion. Adding a seam requires changing that contract and its
tests; a new receipt noun is not a seam.

## Adapter catalog

| Adapter key | Protocol | Real substrate anchor | No-spend / ordering precondition | Live owner |
| --- | --- | --- | --- | --- |
| `budget_reservation_provider` | `BudgetReservationProvider.reserve`, `.debit` using integer cents → `RemainingBalance` | `substrate/midnight_oil/budget_ledger.py:BudgetLedger.reserve`, `substrate/midnight_oil/budget_ledger.py:BudgetLedger.debit`, `substrate/midnight_oil/budget_ledger.py:BudgetLedger.reserve_call` | A verified, owner-bound consent grant must exist before reserve; debit cannot exceed the durable reservation. | SPR-05 |
| `model_provider_route_executor` | `ModelProviderRouteExecutor.execute` → `DispatchResult` | `substrate/dispatch/router.py:dispatch`, `substrate/dispatch/router.py:DispatchResult`, `substrate/dispatch/base.py:Provider` | Operator grant is live, reservation exists, and the requested debit fits before any provider call. | SPR-06 |
| `retrieval_executor_source_receipts` | `RetrievalExecutorSourceReceipts.retrieve` → `RetrievalResult` | `substrate/graph/retrieval_substrate.py:RetrievalSubstrate`, `substrate/graph/retrieval_substrate.py:make_substrate` | **Retrieval must not run before budget reservation.** Every returned source requires a source receipt. | SPR-06 |
| `graph_mutation_writer` | `GraphMutationWriter.commit_asset` | `substrate/graph/ops.py:insert_deliverable`, `runtime/db_lock.py:LockedConnection` | Requires a write-locked connection, completed synthesis, provenance, and operator-authorized run. | SPR-06 |
| `final_html_artifact_writer` | `FinalHtmlArtifactWriter.write(MidnightOilExecutionReceipt)` → `DepositResult` (`ArtifactHandle`) | `substrate/midnight_oil/deposit.py:deposit_job_results`, `substrate/engagement_spine/store.py:EngagementStore.put_document`, `substrate/engagement_spine/project.py:project_to_html` | Deposit the document and twin notes before projecting the HTML transport; never claim persistence before the store writes finish. | SPR-06 |
| `operator_live_dispatch_enablement` | `OperatorLiveDispatchEnablement.is_authorized`, `.authorization` | `substrate/midnight_oil/spend_consent.py:decode_and_verify`, `interfaces/research/api/midnight_oil_routes.py:post_run` | No verified, owner-bound, unexpired consent receipt means inert. Header consent is never persisted. | SPR-06 |
| `control_ledger_audit_rollback` | `ControlLedgerAuditRollback.append`, `.rollback_receipt` | `substrate/event_log/events.py:log_event`, `substrate/event_log/events.py:emit_typed`, `substrate/midnight_oil/operation_queue.py:DurableOperationQueue` | Append-only transitions must be idempotent and monotonic; an unknown provider outcome cannot be replayed without reconciliation. | SPR-04 and SPR-06 |

The three directly spend-capable boundaries are budget reservation, provider
execution, and retrieval. Their live implementations must all derive authority
from the same consent receipt and durable operation generation. A successful
check at one boundary does not authorize a later boundary after expiry.

## Ordering owned by `MidnightOilSeams`

The injected bundle owns cross-adapter preconditions. Today it records budget
reservation before allowing retrieval. SPR-06 extends this single state machine
for provider execution, synthesis, graph commit, twin write, and ledger closeout;
callers must not invoke adapters out of band. The synthetic runner constructs
the all-Null bundle but invokes none of it, preserving the permanent free test
oracle.

## Durable worker-claim appendix (SPR-04)

The historical #584 proposal used visibility `900s`, lease TTL `300s`,
heartbeat `60s`, maximum attempts `3`, and exponential backoff with jitter.
Those values are design inputs, not claims about the current implementation.
The accepted durable queue is the source of truth and additionally requires:

- one durable operation per job;
- compare-and-swap claim generations and explicit lease expiration;
- per-operation process locking with crash release;
- checkpoints distinguishing a provider return from completed settlement;
- a stable provider idempotency key;
- unknown outcomes held for reconciliation, never automatically replayed; and
- terminal `FAILED_RECONCILE` when safe recovery cannot prove the outcome.

SPR-04 owns claim/lease durability, SPR-05 owns atomic reservation and debit,
and SPR-06 owns the only reachable live adapter wiring. The reference runner's
synthetic mode remains networkless and free after all three land.

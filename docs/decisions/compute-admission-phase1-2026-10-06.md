# Provider-neutral compute admission, phase 1

Status: proposed implementation, default off. Root/Nudge owns merge and deployment.

The Oct 6 backend handoff assigns the admission contract to Undertaker v3.
The module at `runtime/compute_admission/` adds typed job identity, policy-based
placement, local lane leases, memory/disk admission and `compute_ledger.v1`.
It runs only trusted in-process callables. Modal, Prime Sandboxes and Mini-node
entries are fail-closed stubs. No product caller is connected.

Use `owner_user_id`, `tenant_id` and `project_id` in both the job and each ledger
row. These are the exact names for the other backend lane's additive event
migration and eventual result funnel. An API must derive them from authorized
server state. This decision adds neither an identity migration nor a graph
write path.

Antiek-user jobs require a backend declared EU. Unknown regions refuse.
No-retention jobs refuse until the hand-off and retention policy can be proved.
Provider prices remain null. Missing ledger/capacity bindings cannot produce
an admitted state. The shipped policy has no tenant allocations.

The ledger is a private single-writer journal. It records a start before
execution and validates state/identity continuity when opened. Historical
unfinished jobs or reused historical keys require explicit reconciliation.
This is not a distributed scheduler or a replay engine. Separate ledger paths
cannot arbitrate the same lane across hosts. Bead IDs name lanes, but Beads
claim leases do not authorize execution or replace compute leases.

Real provider adapters remain held for Faisal's s16 amendment and ADR 0017
scope decision. The single-writer graph funnel, backups, EU R2 buckets and event
migration remain with Undertaker p2C. Per-user DuckDB, derived ClickHouse and
host migration decisions are not implemented here. Null prices and passing
unit controls do not authorize runtime activation or provider spend.

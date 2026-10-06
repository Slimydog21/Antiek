# Compute admission, phase 1

This internal module runs trusted callables in one Python process. No production
API, CLI or research caller uses it. `ANTIEK_COMPUTE_LAYER_ENABLED` defaults off.
Disabled submissions refuse execution without opening a ledger or sampling the
host. Existing product callers and their behavior are unchanged.

The shipped policy allocates no tenants, declares no local region, and leaves
capacity thresholds and the disk path null. The flag alone cannot admit work.
An enabled controller also needs an explicit absolute private ledger path,
owner/project allocations and a capacity policy. Missing bindings return an
honest refusal. This module is not a sandbox or an authentication system.
An eventual caller must derive owner, tenant and project from authorized server
state. Caller assertions do not grant access to a graph or provider.

## Jobs and outcomes

`JobRequest` requires `owner_user_id`, `tenant_id`, `project_id`,
`idempotency_key`, `lane_key`, `workload_class`, `inputs_digest` and `who_pays`.
The input digest is SHA-256 and the workload is a closed `WorkloadClass` enum.
`who_pays` is `antiek_hosted` or `byot`; it records attribution without authorizing
billing. The request rejects caller-selected job IDs and routes. `submit()`
mints a UUID and binds the policy version and selected backend alias.

Identical requests reuse their current job within a scheduler. Idempotency is
scoped to owner/tenant/project/key. Changed inputs with the same key get a
separate refusal job and cannot change the original. Running and terminal jobs
cannot start again. There is no automatic retry or fallback.

| Code | Meaning | Controller action |
| --- | --- | --- |
| `admitted` | Pool slots and ACU allowance reserved | Run this job once |
| `queued` | Host headroom is unknown/low, or the pool is full | Hold the same job; explicitly call `advance()` when capacity changes |
| `refused_policy` | Disabled, unbound, unallocated, conflicting or disallowed placement | Report refusal |
| `lease_held` | Another job owns this tenant/project/lane | Inspect its holder |
| `route_blocked` | Unimplemented adapter or credential/billing failure | Repair under operator control; do not retry or fall back |
| `budget_blocked` | The tenant's session ACU allowance is exhausted | Report refusal |

Every decision has `retryable=false` and a typed `ReasonCode`. `advance()`
reconsiders an existing queued job without creating an attempt. `run()` executes
an admitted callable on the calling thread, with its envelope and heartbeat
function. It checks the route and host headroom again before recording a start.
If headroom has fallen, it returns the job to the queue and releases its
reservation while retaining its lane. Only a recorded start consumes ACU.

`CredentialFailure` and `BillingFailure` make the job terminal and block that
tenant/backend alias, including work already queued or admitted. Ordinary task
exceptions fail only that job. Interruptions fail the job and are re-raised.
Exception messages are not copied into the ledger. There is no live provider
error translator or credential test in this phase.

## Policy and placement

`ComputePolicy` validates `antiek.compute_policy.v1` with a `1.x.y` policy
version. Its JSON schema is available through `model_json_schema()`. Unknown
fields, duplicate YAML keys, unsafe tags, invalid references and impossible
slot costs are rejected. All provider prices remain null.

Each tenant has explicit owner IDs, projects, a session ACU budget and
`data_locality`. Each backend has a kind and declared `region` of `eu`, `us` or
`unknown`. `antiek_user` work refuses any route whose declared region is not
`eu`, before capacity or execution. The declaration is policy input, not proof
of a host's location. `mini-only` permits only local/in-process or reserved
Mini-node kinds. `cloud-ok-no-retention` refuses because this phase cannot
establish the artifact retention contract.

The registry contains `in_process`, `modal`, `prime_sandboxes` and `mini_node`.
Only `in_process` can execute. Every other adapter refuses even a direct call;
none imports a provider SDK, reads credentials or makes a network request.
Real Modal/Prime adapters need Faisal's s16 amendment and ADR 0017 decision.

Capacity admission uses configured memory percentage, disk bytes and memory
pressure limits. Linux samples `MemAvailable` from `/proc/meminfo`. macOS uses
a bounded native `sysctl` query. Unsupported, expired or invalid samples queue
work; they never imply readiness. Disk capacity is measured on the configured
path. Samples do not reserve physical resources or predict a callable's peak
use. The caller must choose real thresholds before connecting workloads.

Pool slots and ACU are admission weights, not measured CPU/RAM or currency.
Admission reserves ACU, start consumes it, and pre-start cancellation refunds
only that job's reservation. Budgets are per tenant and scheduler session.
They do not replace monthly billing or the existing capacity slider.

## Ledger and leases

`compute_ledger.v1` is an append-only JSONL journal with an exclusive advisory
file lock, private regular-file checks, bounded records and `fsync` after each
row. Each row carries owner, tenant, project, job, idempotency and lane identity,
input digest, workload, payer, policy, state transition, attempt, route, region
and ACU weight. Cost fields are null with `cost_source: unknown`. Terminal rows
include `trace_ref` and `artifact_refs`. A callable can return `JobOutput` to
supply real references. Absent references remain null/empty; no artifact is
invented, uploaded or treated as durable by this module.

A start must be journaled before calling the task. A write failure holds further
execution. A failed terminal write still releases the completed task's lease
and prevents re-execution in memory; the journal remains unfinished and needs
operator reconciliation. Partial records are retained, never truncated.
Opening a journal with an unfinished historical job or reusing a historical
idempotency key also holds execution. A clean journal can append new intentional
work without rewriting its prefix. There is no automatic crash recovery.

Lane ownership uses the exact tenant/project/lane tuple. Queued and admitted
jobs own their lanes. `inspect_lease()` reports node, PID, scheduler instance,
thread identity, UTC acquisition/heartbeat and monotonic staleness. Staleness
never evicts a holder or starts a replacement. Tasks and controllers must
heartbeat work they continue to hold. `cancel()` applies only before execution.
A retired job cannot heartbeat a successor. Forked controllers refuse use.

For bead-driven jobs, supply `bead_id` and use that exact ID as `lane_key`.
This binds the name only. Beads claim leases are advisory and are not replicated
execution authority. This scheduler does not invoke `bd`, synchronize Dolt or
bridge Beads leases. Its own lease governs execution within this process.

## Limits and verification

Job values, idempotency responses, budgets, route blocks and leases remain
process-local. They are not replicated or restored from the ledger. An instance
ID is not an OS process-birth proof. Two independent ledger paths do not provide
shared lane exclusion. This phase has no remote worker, TTL teardown, reaper,
provider fallback, weighted tenant fairness or artifact hand-off bucket.

Workers must not write the research graph. This module imports no graph/DB code.
The event-envelope migration and graph-writer funnel are owned by the other
backend lane. DuckDB identity/encryption, backups, ClickHouse, R2 provisioning
and the AWS move remain separate work. Production heavy workloads are not
admitted by this PR.

Run only the targeted controls locally on the overloaded Mini:

```sh
python -m unittest discover -s tests -p test_compute_admission.py -v
```

Normal CI collects the same module through pytest. The controls use actual
private temporary journals and local callables, bounded threads, explicit unit
policy namespaces and injected capacity samples. They exercise refusal and
execution; they do not establish live provider, production placement or billing
behavior. No network or paid backend is needed.

# Compute admission, phase 1

This module admits and runs trusted callables inside one Python process. It is
an internal scheduler contract, with no production API, CLI or investigation
caller wired to it. `ANTIEK_COMPUTE_LAYER_ENABLED` defaults off. Disabled
submissions return `refused_policy` and cannot execute a callable.

The shipped `policy.v1.yaml` has no tenant allocations. Setting the flag alone
still refuses work. A controller must load a validated policy with its actual
tenant/project allocation and explicitly use one shared `AdmissionScheduler`.
Tenant/project identifiers here are routing namespaces, not authentication or
data-access authorization. An eventual API must derive them from authorized
server state.

## Submission and execution

`JobRequest` requires `tenant_id`, `project_id`, `lane_key`, `workload_class`,
`idempotency_key` and a SHA-256 `inputs_digest`. It rejects caller-supplied job
IDs and backend choices. `submit()` mints the full UUID job ID. The scheduler
selects the backend alias and records the policy version in each decision.

Idempotency is scoped to tenant/project/key. Identical requests return the
same job and current state. Changed lane, class or input digest with that key
returns `refused_policy` without changing the original job. Keep the digest
bound to the actual inputs when a caller is connected to this module.

Admission is separate from execution. `run(job_id, task)` runs an admitted
callable once on the calling thread, with its envelope and heartbeat function
in `JobContext`. Repeated or concurrent calls cannot start it again. Success,
task failure and interruption all release its lane and pool slots. An
interruption is recorded as failed and re-raised to the controller.

| Code | Meaning | Controller action |
| --- | --- | --- |
| `admitted` | Pool slots and ACU allowance reserved | Run that job once |
| `queued` | Pool is full; the job owns its lane | Keep its identity; call `advance(job_id)` when capacity changes |
| `refused_policy` | Disabled, unallocated, unknown class or conflicting key | Report refusal; do not retry |
| `lease_held` | Another job owns this tenant/project/lane | Inspect that holder; do not retry |
| `route_blocked` | Credential or billing failure blocked this tenant/route | Repair the route under operator control; do not retry or fall back |
| `budget_blocked` | The configured session ACU allowance is exhausted | Report refusal; do not retry |

Every decision has `retryable=false`. `advance()` is a scheduler action on an
existing queued job, not a repeated submission or execution attempt. Refused
keys remain refused for the lifetime of this scheduler. A new intentional
unit of work needs its own key. Running and terminal jobs cannot be restarted.
The `state` and `attempts` fields distinguish an admission decision from the
subsequent execution result.

`CredentialFailure` and `BillingFailure` are the execution boundary's typed
signals. Either makes the job terminal and blocks subsequent work on that
tenant/backend alias, including already admitted and queued jobs. No other
route is selected automatically. Ordinary task exceptions fail just that job.
Exception messages are not copied into decisions. There is no provider error
translator yet, and these controls do not establish live credential handling.

## Policy and leases

`ComputePolicy` is the strict versioned YAML schema. Its JSON schema is
available through `ComputePolicy.model_json_schema()`. Version 1 accepts
`schema_version: antiek.compute_policy.v1` and a `1.x.y` policy version, with
explicit backend aliases, slot pools, workload classes, tenant/project
allocations, session ACU allowances and heartbeat thresholds. Unknown fields,
duplicate YAML keys, unsafe tags, invalid versions, unknown references and
impossible slot costs are rejected. Only `kind: in_process` is supported. The
required `price_usd_per_unit` field must be null, including for local execution.

Slot costs and ACU units are configured admission weights. Admitted work
reserves its weight; starting it consumes that session allowance even if it
fails. Cancelling queued or admitted work releases only its own reservation.
These counters are process-local. They are not monthly billing, measured
resource usage, currency prices or a connection to the existing capacity slider.

Leases use the exact tuple `tenant_id/project_id/lane_key`, avoiding filename
normalization collisions. Both queued and admitted work own their lanes.
`inspect_lease()` reports the job, node name, PID, scheduler instance, running
thread identity, UTC acquisition/heartbeat times, heartbeat staleness and
local thread liveness. Elapsed time uses a monotonic clock. A task must call
its heartbeat function within the configured interval; the controller must
heartbeat queued or admitted work it continues to hold.

A stale heartbeat is diagnostic. It never evicts a holder, frees capacity or
restarts a job. `cancel()` applies only before execution. This phase has no
force-release operation. Completed jobs cannot heartbeat a later lane owner.
The scheduler refuses use from a forked process.

## Limits and verification

All jobs, idempotency entries, budgets and route blocks are held in memory.
They do not survive a process restart and are not shared across scheduler
instances or hosts. The scheduler instance ID is a local ownership token,
not an OS process-birth proof. Callables are trusted application code; the
in-process backend is not a sandbox or a thread-kill facility.

This phase does not activate host memory/disk gates, weighted tenant fairness,
provider execution, a durable ledger, orphan reconciliation, a reaper or
resource TTLs. It does not change the existing retry behavior, ACU metering,
DuckDB ownership or data placement. Modal/Prime selection, ClickHouse and the
planned host migration remain separate decisions. Do not connect production
heavy workloads until those operational controls and ownership are resolved.

The targeted local command is:

```sh
python -m unittest discover -s tests -p test_compute_admission.py -v
```

The same tests live under `tests/` and are collected by the normal GitHub
pytest gate. They exercise actual in-process tasks and bounded thread controls,
with synthetic unit-test namespaces. No DB engine, provider SDK, credentials,
network requests or remote compute are required.

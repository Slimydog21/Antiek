# Daytona Integration Spec

Status: **DRAFT** — 2026-05-17. Not yet ratified.
Author: Faisal (with Claude review).
Scope: How Daytona (ephemeral remote sandboxes) integrates into Antiek
without violating substrate invariants.

## 0. Purpose

Daytona is a sandbox-as-a-service: each task runs in a remote, ephemeral
Linux environment that is created, used once, and destroyed. This spec
defines **exactly where that pattern earns its place in Antiek** and —
just as importantly — **where it does not**.

The default posture of this document is **rejection**: Daytona is an
extra moving part with a paid quota, network dependency, and its own
failure modes. It is admitted only where it solves a problem the host
process cannot solve cleanly on its own.

## 1. Goals

In priority order:

1. **Eliminate the WP-A3 failure class.** Phase A surfaced loky
   semaphore / external-kill failures at `roles/parameter_extractor`
   when a local process pool was used for parallel fan-out. Per-task
   *remote* sandboxes dissolve the worker-pool model entirely: a dead
   worker is a dead sandbox, not a poisoned pool.

2. **Isolate untrusted external content** during acquisition. URLs,
   PDFs, scraped HTML, and library mirrors deliver byte streams that
   can wedge parsers, exhaust memory, or trip anti-bot countermeasures.
   These workloads belong in disposable environments.

3. **Provide a safe tool-execution target** when `roles/` agents need
   to run Python (compute, parse, fetch). LLMs must never execute code
   against the host filesystem.

4. **Restore deterministic substrate hygiene** for compounding skill
   verification and backtest replay.

## 2. Non-Goals (explicit rejections)

This spec **does not** introduce Daytona into any of the following.
Each rejection is grounded in a specific Antiek invariant.

| Surface | Reason for rejection |
|---|---|
| `runtime/db_lock.py` and the DuckDB single-writer invariant | The lock is local-file `flock` over a sidecar lock file; it is the Quack-swap point. A remote sandbox cannot hold a `flock` on a host file. Writes must remain on the host. |
| `substrate/event_log/` | The event log is the system of record. Ephemeral sandboxes do not own state. Events about sandbox work are emitted *from the host* after results return. |
| `substrate/graph/`, `substrate/attribution/`, `substrate/context_pack/` | Read-heavy, stateful, and accessed by every role. Pinning these into per-call sandboxes adds latency without solving any active problem. |
| `substrate/dispatch/` (the LLM router) | LLM dispatch is provider-side HTTP. It is already remote. Wrapping it in another remote layer is pure overhead. |
| `runtime/docker/` (the planned long-lived service containers) | Daytona is short-lived per-task sandboxes. The planned compose services (`antiek-event-writer`, `antiek-duckdb-warden`, `antiek-research-api`) are long-lived owners of state and need a real container host (Fly / Modal / Render / k8s). Daytona does not replace this layer; it sits *behind* it. |
| The Sprint 10 REST surface | A REST API is a long-lived process. It is deployed via runtime/docker, not Daytona. |
| `substrate/schemas/`, `middleware/temporal/`, `middleware/source_tier/`, `middleware/archive/`, `middleware/constraint_check/` (deterministic path) | Pure compute on already-trusted in-process data. No isolation benefit. |
| `processing/embedding/` index storage | Stateful, latency-sensitive, persistent. |

If a future contributor proposes Daytona for any of the above, the
burden of proof is on them to overturn the rejection with a concrete
failure mode this spec did not foresee.

## 3. Architecture: where Daytona sits

```
┌─────────────────────────────────────────────────────────────┐
│ HOST (developer mac / production server)                    │
│                                                             │
│  substrate/        ← stays on host                          │
│  middleware/       ← stays on host                          │
│  orchestration/    ← stays on host                          │
│  roles/            ← orchestration logic on host;           │
│                       LLM calls go to providers;            │
│                       tool execution → Daytona              │
│  runtime/db_lock   ← stays on host (flock-based)            │
│  runtime/docker/   ← long-lived service containers          │
│                                                             │
│  Daytona-aware seam:                                        │
│  ─────────────────                                          │
│  runtime/remote_exec/   ← NEW MODULE                        │
│    - create_sandbox(snapshot, purpose)                      │
│    - run_in_sandbox(sandbox, code|exec, payload)            │
│    - destroy_sandbox(sandbox)                               │
│    - emit_typed_events_at_each_step()                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS, API key from env
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ DAYTONA (api.daytona.io managed)                            │
│                                                             │
│  Per-task ephemeral sandboxes:                              │
│    - acquisition-urls-v1   snapshot                         │
│    - acquisition-books-v1  snapshot                         │
│    - tool-exec-py311-v1    snapshot (LLM tool runtime)      │
│    - skill-verify-v1       snapshot                         │
│    - backtest-replay-v1    snapshot (pinned)                │
│                                                             │
│  Sandboxes read inputs uploaded by the host, run, write     │
│  structured JSON to stdout, get destroyed.                  │
└─────────────────────────────────────────────────────────────┘
```

**Substrate stays on host. Daytona executes risky or parallel work.
The host owns persistence and audit.**

## 4. The new module: `runtime/remote_exec/`

All Daytona contact passes through one module. Direct `daytona.create()`
calls anywhere else in the tree are a discipline violation.

### 4.1 Interface

```python
# runtime/remote_exec/__init__.py

from contextlib import contextmanager
from typing import Iterator, Optional

from substrate.schemas import RemoteExecResult


@contextmanager
def remote_exec(
    snapshot: str,
    purpose: str,
    timeout_s: int = 120,
) -> Iterator["SandboxHandle"]:
    """Yield a sandbox; tear it down on exit. Emits:
        remote_exec_start
        remote_exec_succeed  OR  remote_exec_fail
    typed events to the event log, regardless of outcome.
    """


class SandboxHandle:
    def upload(self, local_path: str, remote_path: str) -> None: ...
    def exec(self, cmd: list[str], timeout_s: int) -> RemoteExecResult: ...
    def code_run(self, code: str, timeout_s: int) -> RemoteExecResult: ...
    def download(self, remote_path: str, local_path: str) -> None: ...
```

### 4.2 Required event surface

Every sandbox lifecycle emits three typed events to `substrate/event_log/`:

| Event | When |
|---|---|
| `remote_exec_start` | Before `daytona.create()` returns. Includes `snapshot`, `purpose`, `caller_module`. |
| `remote_exec_succeed` | After successful `exec` and clean teardown. Includes `duration_s`, `exit_code`, `stdout_len`. |
| `remote_exec_fail` | On any failure (create timeout, exec timeout, non-zero exit, network error, teardown failure). Includes `error_class`, `error_msg`. |

This is non-negotiable. Same discipline as `middleware/`: no silent
side effects. If the audit log can't reconstruct what happened in a
sandbox, the sandbox shouldn't have run.

### 4.3 Configuration

`runtime/remote_exec/config.py` reads:
- `DAYTONA_API_KEY` — env var only. Never in config files. Never in commits.
- `ANTIEK_DAYTONA_ENABLED` — feature flag. Default `false`. Disables all
  remote_exec calls and forces local fallback where one exists. Anyone
  who can run Antiek must be able to run it without Daytona, even if
  some surfaces degrade.
- `ANTIEK_DAYTONA_TIMEOUT_DEFAULT_S` — global default. Per-call override
  is allowed.

If `DAYTONA_API_KEY` is unset and `ANTIEK_DAYTONA_ENABLED=true`,
`remote_exec` raises at import time — fail loud, not at runtime.

## 5. Wedges, in build order

Each wedge has scope, exit criteria, and a rollback path. Wedges are
sequenced so the first one stands alone — if subsequent wedges are
abandoned, the first still delivers value.

### Wedge 1 — `acquisition/urls/` (first wedge, Sprint 10 scope)

**Why first.** Smallest blast radius. URL acquisition handles
untrusted bytes today. Sprint 10 already commits to closing this
acquisition surface. The integration validates the entire
`runtime/remote_exec/` plumbing on a non-critical path.

**Change.**
```python
# acquisition/urls/run.py — host side
from runtime.remote_exec import remote_exec

for url in urls:
    with remote_exec("acquisition-urls-v1", purpose=f"fetch:{url}") as sb:
        sb.upload("acquisition/urls/_sandbox_entry.py", "/work/entry.py")
        result = sb.exec(["python", "/work/entry.py", url], timeout_s=60)
        if result.exit_code == 0:
            chunk = json.loads(result.stdout)
            substrate.event_log.emit("ingest_chunk", chunk)
        else:
            substrate.event_log.emit("acquisition_fail", {...})
```

**Sandbox snapshot `acquisition-urls-v1` contents:**
- Python 3.11
- `httpx`, `readability-lxml`, `beautifulsoup4`, `lxml`
- A minimal entry script: `fetch_and_parse.py` that takes a URL
  argv and emits one JSON object to stdout matching the
  `ingest_chunk` schema.

**Exit criteria.**
- 50 consecutive URL fetches succeed end-to-end via Daytona.
- Both `static` and `rendered` modes work (rendered mode shells out
  to a Chrome MCP entry inside the sandbox snapshot).
- Every fetch leaves three typed events in the event log.
- Local fallback (`ANTIEK_DAYTONA_ENABLED=false`) still works.

**Rollback.** Feature flag off. `acquisition/urls/` reverts to host
execution. No data migration needed because the substrate never
moved.

### Wedge 2 — Parallel fan-out (the WP-A3 fix)

**Why second.** This is the highest-value wedge; it dissolves an
already-observed failure mode. It is second only because Wedge 1
shakes out the `remote_exec` module first.

**Change.** Wherever Antiek today wants `concurrent.futures` or `loky`
to fan a function across N inputs, replace with N concurrent
sandbox tasks. New helper:

```python
# runtime/remote_exec/fanout.py

def fanout(
    snapshot: str,
    purpose: str,
    inputs: list[dict],
    entry_script: str,
    timeout_s: int = 120,
    max_concurrency: int = 8,
) -> list[RemoteExecResult]:
    """Spawn up to max_concurrency sandboxes concurrently. Each handles
    one input. Returns one RemoteExecResult per input. Failures are
    returned in-band, never raised — caller decides retry policy."""
```

**Target callers** (in order):
1. `acquisition/arxiv/` — batch ingest of paper lists.
2. `acquisition/books/` — batch ingest of bibliographies.
3. Any future use of `roles/parameter_extractor/` over a chunk list
   that previously would have used loky.

**Exit criteria.**
- A 200-input arxiv batch completes with ≤ 2% sandbox-creation failure
  rate and no host-side process pool involved.
- Killing one sandbox mid-run does not affect the others (this is the
  acceptance test for the WP-A3 fix).
- Failures appear as `remote_exec_fail` events, not as exceptions
  bubbling into orchestration.

**Rollback.** Feature flag off; loky/concurrent.futures path remains
available as fallback. The fanout helper keeps a local-process
implementation behind the same signature.

### Wedge 3 — LLM tool-execution surface

**Why third.** Depends on the substrate having a clean `remote_exec`
module, and on at least one role actually wanting tool-exec (which is
post-Sprint-10).

**Change.** `substrate/dispatch/` is unaffected. When a role
(synthesizer, connector, evidence_retriever) emits a tool-call that
requires code execution, the orchestrator routes the code body to
`remote_exec("tool-exec-py311-v1", purpose=f"tool:{role}:{tool}")`
and returns the result to the model.

**Hard rules:**
- The sandbox has **no Antiek credentials**. No API keys. No DB
  access. Tool calls that need data get their inputs uploaded to the
  sandbox from the host.
- The sandbox has **no write access to the host event log**. The
  host writes the events based on the sandbox result.
- The sandbox has an **outbound network allowlist** if it can be
  configured at the Daytona level; otherwise the entry script
  enforces it.

**Exit criteria.**
- At least one role uses the tool-exec surface in a real
  investigation.
- A red-team test where the LLM emits malicious code (`rm -rf /`,
  exfiltration attempt, fork bomb) demonstrates: host filesystem
  unchanged, no credential leakage, sandbox destroyed, failure event
  logged.

**Rollback.** Feature flag off; roles fall back to refusing
tool-exec calls. This is acceptable because no role *requires*
tool-exec to function.

### Wedge 4 — Skill verification isolation

**Why fourth.** `compounding/verification/` today measures growth by
file diff. As skills get more substantive (Phase 8 starts producing
runnable artifacts), verification will want to *run* the new skill
end-to-end and check that it executes cleanly. Running unverified
skills on the host risks env-state poisoning that breaks later
verifications.

**Change.** When a skill version under verification has executable
artifacts, run them in `remote_exec("skill-verify-v1", purpose=...)`.

**Exit criteria.**
- At least one skill version is verified end-to-end via a sandbox
  run.
- A deliberately-broken skill (infinite loop, wrong output schema)
  fails verification cleanly, with the failure attributable in the
  event log to the specific skill version.

**Rollback.** Feature flag off; verification reverts to file-diff
only (current behavior).

### Wedge 5 — Backtest reproducibility

**Why last.** `middleware/backtest/` will produce signal "over months
not weeks" (per its own README). Sandbox-based reproducibility is
useful but not urgent.

**Change.** Each backtest run uses a pinned Daytona snapshot
(`backtest-replay-v1` with frozen pip dependencies and a frozen system
clock surface). The synthesis being replayed is uploaded; the backtest
script runs; results are downloaded; substrate stores them.

**Exit criteria.**
- A backtest re-run of the same archived synthesis + same snapshot +
  same pinned parameter version produces byte-identical results.

**Rollback.** Feature flag off; backtests run on host (current
behavior).

## 6. Contracts & invariants

These hold across all wedges. Violations are spec breaks.

1. **The host owns persistence.** No sandbox writes to DuckDB, the
   event log, the graph, the skill files, or any persistent host
   resource. Sandboxes return data to the host via stdout (JSON) or
   via downloaded files; the host commits.

2. **Every sandbox lifecycle emits three typed events.** See §4.2.

3. **Every sandbox is destroyed.** `remote_exec` uses `try/finally`.
   Quota leaks are a P1 bug, not a "we'll clean it up later" item.

4. **API key from env, nowhere else.** `DAYTONA_API_KEY` is read in
   `runtime/remote_exec/config.py` at process start. Never logged.
   Never serialized. Never copied into a sandbox.

5. **Snapshots are versioned.** `acquisition-urls-v1`, never
   `acquisition-urls`. When a snapshot's pinned deps change, version
   bumps. This is the same discipline as
   `middleware/archive/`'s ANTIEK_PARAM_VERSION stamping.

6. **Local fallback exists everywhere it can.** Antiek must remain
   runnable with `ANTIEK_DAYTONA_ENABLED=false`. Wedges 1, 2, 4, 5
   degrade gracefully; Wedge 3 (LLM tool-exec) is the only wedge
   where falling back means a role refuses a capability rather than
   running locally.

7. **The single-writer invariant on DuckDB is sacred.** Any
   appearance of `from runtime.remote_exec` in
   `runtime/db_lock.py` or `substrate/event_log/` is a CI failure.

## 7. Failure modes & responses

| Failure | Detection | Response |
|---|---|---|
| Daytona API outage | `create` raises after retries | `remote_exec_fail` event; caller's local fallback (where applicable) engages. |
| Sandbox network egress blocked | `exec` exits non-zero | Same as above. URL acquisition surfaces this as `acquisition_fail`. |
| Quota exhaustion | `create` 429 | Hard fail. Page the operator. No silent local fallback for cost reasons — running 1000 sandbox tasks locally because the quota ran out is worse than refusing. |
| Sandbox leaks (not destroyed) | A daily job lists active sandboxes and alerts if any are older than 1h | Force-delete and emit `remote_exec_orphan` event. Investigate. |
| Compromised API key | The key was pasted in chat / logged accidentally | Immediate rotation. Daytona dashboard → delete key → create new. Rotate every 90 days regardless. |
| Snapshot drift (a snapshot mutates between v1 and v2 without a version bump) | A backtest replay produces non-byte-identical results | Treated as a P1 bug in the snapshot publish process. |

## 8. Prerequisites

Before any wedge ships:

1. `runtime/remote_exec/` module exists with the §4 interface.
2. `DAYTONA_API_KEY` exists in env, account is verified, quota is
   known.
3. The three typed events (`remote_exec_start`, `remote_exec_succeed`,
   `remote_exec_fail`) are added to the `substrate/schemas/` event
   union and migrated into the event log.
4. CI has a check that rejects `from daytona` outside
   `runtime/remote_exec/`.
5. The `acquisition-urls-v1` snapshot is published and version-tagged
   in `runtime/remote_exec/snapshots.py` (or equivalent registry).

## 9. Cost & quota considerations

Daytona prices per sandbox-minute. A 200-paper arxiv ingest with a
60s per-paper budget = ~200 sandbox-minutes per run. Three runs per
day = ~600 sandbox-minutes/day = ~18,000 minutes/month.

**Action item before Wedge 2 ships:** confirm the monthly quota and
the cost-per-minute on the chosen Daytona plan. If it materially
changes the picture, this spec needs a re-evaluation, not a silent
acceptance.

The host-process fallback for Wedge 2 (loky/concurrent.futures) is
specifically retained because cost may force a hybrid posture: small
batches on host, large batches on Daytona.

## 10. Open questions / explicit risks

1. **Cold-start latency.** A `daytona.create()` call observed in the
   smoke test took several seconds. For per-task sandboxes at scale,
   this needs measurement. If cold-start dominates per-task wall
   clock, the fanout helper should pool warm sandboxes within a run.
   *Pre-Wedge-2 measurement required.*

2. **Network egress allowlisting.** Wedge 3 (LLM tool-exec) assumes
   we can constrain a sandbox's network egress. If Daytona does not
   support this out of the box, the entry-script-enforced allowlist
   is weaker. *Block Wedge 3 on a clear answer.*

3. **Snapshot reproducibility guarantees.** Backtest replay (Wedge
   5) assumes a snapshot is byte-stable across rebuilds. If Daytona
   rebuilds snapshots opaquely, Wedge 5 becomes weaker. *Pre-Wedge-5
   answer required.*

4. **Compliance / data residency.** If any acquisition source has
   data-residency requirements (e.g. EU data must not leave EU),
   Daytona's region selection has to honor that. *Audit per-source
   before any acquisition surface ships.*

5. **Vendor lock-in.** Daytona is one of several
   sandbox-as-a-service providers (e2b, Modal sandboxes, Codesandbox
   CSB). The `runtime/remote_exec/` module is the abstraction
   boundary; if Daytona becomes unviable, the replacement is a new
   adapter behind the same interface. **The abstraction is the
   insurance policy.** This is the same discipline as `db_lock.py`'s
   Quack swap point.

## 11. Acceptance criteria for the spec itself

This spec is considered ratified when:

1. Wedge 1 ships end-to-end and meets its exit criteria.
2. The §6 invariants are enforced by CI.
3. The §8 prerequisites are all true.
4. Open question §10.1 (cold-start latency) has a measured answer.

Until then, Daytona is a **scoped experiment**, not a **substrate
commitment**.

## 12. Out-of-scope topics that may be added later

- **Daytona as a workstation for `interfaces/research/`.** Could a
  researcher session run *entirely* in Daytona? Possibly. Not now.
- **Daytona for RL rollouts** in the Researchmaxx RL plan. The RL
  plan currently targets Prime Intellect. Daytona is not a training
  target; it could be a rollout *environment* but that requires its
  own evaluation against `verifiers`.
- **Daytona for the `interview/` capture surface.** Stateful,
  long-lived, user-facing. Wrong fit by §2.

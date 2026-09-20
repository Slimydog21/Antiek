# §16 exemption — research fan-out may use an external execution provider

**Date:** 2026-05-25
**Branch:** `unified/spr-02`
**Source spec:** `specs/antiek-unified/sprint-02-remote-exec-fanout.html`
**Status:** ✅ ratified by the operator 2026-05-25; scoped to research fan-out only.

## Decision

CLAUDE.md §16's REJECT list bars Daytona/Modal/Pulumi "until a specific
problem warrants it." A specific problem now warrants exactly one carve-out:
**research-runner fan-out may execute on an external provider** via the new
`runtime/remote_exec/` package, so a Deep Research Workspace cascade can run
N focused sub-question researches genuinely concurrently off-host rather than
capped at whatever the single host VM sustains.

The exemption is deliberately narrow. What is exempted:

- The `ResearchRunner` fan-out path — and only that path — may run its browse
  loops in external sandboxes behind the `RemoteExecProvider` interface.
- Daytona is the one provider implementation. No Modal, no Pulumi, no second
  provider behind the interface in this decision.

What is **not** exempted, and stays byte-for-byte as §16 had it:

- **Dispatch posture stays Hermes-primary.** LLM inference for non-research
  workloads is routed by `substrate/dispatch/`, not handed to Daytona/Modal/
  Prime as a cheaper dispatch provider. That is a different decision entirely
  (see `docs/integration_prime_intellect.md` §5 — "No Prime as a dispatch
  provider") and re-opening it is explicitly out of scope here.
- **DuckDB single-writer is untouched.** Remote researches append only to
  their own per-investigation JSONL event logs; none opens a graph write
  connection. A serialized funnel on the host
  (`runtime/remote_exec/funnel.py`) drains completed investigations through
  `runtime/db_lock.connect_write` and is the *only* graph writer — exactly
  as DRW SPR-02 specified for the host-local case. The `--workers 1`
  invariant holds.
- **ε > 10 on DP claims** and **no premature scaling** stay rejected.

## Motivation

The Research workflow's headline differentiator (master-spec §7; DRW spec) is
"cascade one problem into many focused deep researches and watch 20 run at
once." DRW SPR-02 shipped a `ResearchRunner` protocol with a `HostLocalRunner`
(asyncio + bounded semaphore) and a non-functional `DaytonaRunner` stub that
raised a §16 guard. The orchestration multiplexes 20 I/O-bound loops fine
on one event loop, but the *escalation-heavy* fraction of those loops
serialized behind shared host-process ceilings (the 3-session Browserbase
cap, the single VM's network/CPU). Off-host per-sandbox isolation lifts the
ceiling that the host process imposes; it does not lift the budget ceiling
(`TOTAL_ACQUISITION_BUDGET_USD`) or the per-key Exa rate limits, which are
honored unchanged.

This is the "specific problem" §16 reserved the exemption for: the headline
feature is real and is otherwise capped by the host VM, and the alternative
(scaling the host) corrupts the single-writer invariant (master-spec §16,
"Horizontal scaling of the FastAPI process").

## Why host-local stays the default (the steelman, honored)

DRW SPR-02's own analysis argued host-local-first is the *safer* default. Two
recorded reasons: (a) the `parameter_extractor` loky/multiprocessing
external-kill failure — a worker killed out-of-band leaked a semaphore and
wedged the pool — which is exactly the class of failure a remote-sandbox
fleet can reintroduce at the provider boundary; (b) the Daytona vendor
dependency itself.

The operator overrode the default, not the steelman. We honor the steelman by
making host-local the **automatic fallback**: `runtime/remote_exec/factory.py`
selects the remote runner only when remote-exec is both *enabled* (config/env)
and the provider is *available at launch*; otherwise it returns
`HostLocalRunner` with a single logged line (an operational state worth
seeing, not a silent degradation and not a crash). A cascade launched under
fallback runs at the host-local ceiling and says so.

Measured note (rigor): the fake-provider concurrency test shows the remote
runner sustains 20 concurrent researches without the host-process semaphore
contention the host-local runner has — but with deterministic fakes it
cannot prove a *real* throughput win, only that the orchestration scales and
isolates cleanly. The amendment therefore stands on the architecture (off-host
isolation removes a real host-process ceiling) with host-local as the default
until the operator's live smoke (runbook §M7) measures real throughput. If the
live numbers show no win, the amendment can stay on the books while the
default stays host-local — that is the whole point of the fallback design.

## Reconsider if

Revert to host-local-first (flip the config default off; keep the package as
dormant code) if **any** of these hold after the operator's live smoke:

1. Remote-exec proves *fragile* at the host-local ceiling level — i.e., the
   off-host fleet reintroduces an external-kill / orphaned-sandbox failure
   class comparable to the recorded `parameter_extractor` loky failure, and
   teardown does not reliably reclaim sandboxes.
2. Remote-exec proves *expensive* without a throughput win — sandbox time +
   inference cost per cascade exceeds the host-local cost by more than the
   concurrency gain justifies (measured against the aggregate budget).
3. The provider becomes a single point of failure that the fallback cannot
   absorb gracefully (e.g., partial-fleet failures that corrupt the merge).

Reverting is a one-env-flip operation (`ANTIEK_REMOTE_EXEC_ENABLED=0`), not a
code change, by construction of the factory + fallback. The exemption text in
§16 and this record would then be marked superseded, but the
`runtime/remote_exec/` code can stay in the tree dormant.

## Out of scope (do not let this exemption broaden)

- Lifting §16 for **anything other than research fan-out**. Dispatch stays
  Hermes-primary; "while §16 is open, let dispatch use Daytona for cheaper
  inference" is explicitly declined — it re-opens a settled negative.
- A **second remote-exec provider** (Modal/Pulumi/etc) behind the interface.
  The interface accommodates a swap, but adding a concurrent second vendor is
  a separate decision.
- The **live Daytona run** itself (credentials + spend) — operator-gated; see
  `infrastructure/runbooks/remote-exec-fanout.md`.

## Companion artifacts

- `CLAUDE.md` §16 — the scoped exemption paragraph (one added paragraph; the
  surrounding REJECT clauses are byte-identical).
- `runtime/remote_exec/` — the provider interface, the Daytona provider
  (lazy-import, optional dep), the `RemoteResearchRunner`, the single-writer
  funnel, the cost/budget path, and the runner factory.
- `infrastructure/runbooks/remote-exec-fanout.md` — enable / credentials /
  budget / fallback / disable, and the operator-gated live smoke.
- `runtime/research_runner/` — the host-local runner this sits beside,
  unchanged; the `daytona_gated.py` stub is now superseded by the real
  provider but left in place (its tests still pass; removing it is a
  follow-on cleanup, not this sprint).

## 2026-08-11 amendment — additive Prime Agent RLM evidence

This decision is superseded only narrowly enough to permit an optional Prime
Agent subprocess beside existing RLM workflows. The lane is default-disabled,
bounded, and returns labeled supplemental evidence plus an execution receipt;
the existing callable/Hermes result remains canonical on success and every
failure path.

This amendment grants no dispatch authority, does not add or replace a
`RemoteExecProvider`, and permits no DuckDB/graph writes, training, trajectory
publication, credentials in argv, or production enablement. Those boundaries
remain separate operator decisions. The implementation is confined to
`orchestration/rlm/prime_agent_backend.py`; removing it or leaving its enable
flag unset restores the prior behavior without data migration.

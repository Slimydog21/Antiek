# Resilience reconciliation (nygard-resilience, SPR-01..08)

Capstone record for the nygard-resilience lane: what was hardened, what was
found-and-fixed, and what is left to first-light. The permanent gate is
`.github/workflows/resilience_floor.yml` (informational-first; operator flips it
to a required check in branch protection).

## What was hardened

| Sprint | Invariant | Artifact |
|---|---|---|
| SPR-01 | Deterministic, inert-by-default fault injection at real seams | `tools/faultinject/` (readonly_fs / locked_db / provider_fault) |
| SPR-02 | I-LOUD: infra faults surface typed, not silently degraded | `substrate/errors.RetrieverInfraError` + `is_expected_degradation`; boundary at `retrieval_substrate.py` |
| SPR-03 | Every external call carries an explicit timeout | `tools/lints/no_unbounded_external_call.py` + baseline (empty — all fixed) |
| SPR-04 | A failing provider is shed fast; the fallback chain carries | `substrate/dispatch/breaker.py` + 3 router hooks |
| SPR-05 | No seam call under the single-writer lock; fault releases the funnel | `tools/lints/no_seam_call_under_write_lock.py` + baseline + isolation test |
| SPR-06 | The infra-fault agent-failure fixtures are runnably replayed | `tests/resilience/test_chaos_suite.py` |
| SPR-07 | FDs / DB connections / semaphores return to baseline under repeated fault | `tests/resilience/test_steady_state_*.py` + `resource_probe.py` |
| SPR-08 | A permanent CI floor keeps all of the above from regressing | `.github/workflows/resilience_floor.yml` + this doc |

## What was found and fixed

- **The 2026-05-17 read-only-FS class was a SILENT SWALLOW** at
  `substrate/graph/retrieval_substrate.py` `DuckDbVssSubstrate.open`: a copy
  `OSError` was downgraded to a brute-force fallback, erasing the cause. **Fixed**
  (SPR-02) — an infra `OSError` at the vss-copy now raises a typed
  `RetrieverInfraError`; the expected vss-unavailable degradation keeps its benign
  fallback. Fails-before/passes-after fixture records the class.
- **Bulkhead breach: `tools/arxiv_oai_sync.py:283`** holds the write lock across a
  network OAI-PMH harvest — a stalled harvest pins the single-writer funnel.
  **Surfaced + guarded, not fake-fixed:** baselined in the SPR-05 lint with an
  acquire-late follow-on (see below); the lint now catches any NEW seam-under-lock.
- **The Phase-A loky-semaphore leak is architecturally eliminated** (the runner
  migrated to `asyncio.Semaphore`; loky is not installed). SPR-07 proves the
  modern permit-release-on-fault guarantee; the leak class cannot recur.

## The silent-failure guard (SPR-08 M2) — how it is provided

The "do not re-encode an infra error as a benign domain result" invariant is
enforced by the composition already shipped, not a single new whole-tree lint:
- SPR-02's typed boundary + `is_expected_degradation` (the retriever seam surfaces
  infra faults; the three named degradations stay benign, by explicit type).
- SPR-05's `no_seam_call_under_write_lock` (an infra-prone seam call cannot hide
  under the write lock).
- SPR-03's `no_unbounded_external_call` (a timeout-less call — the most common
  silent-stall source — is forbidden).
- **Follow-on:** a dedicated whole-tree AST lint that flags `except <infra>: return
  <benign-domain>` directly. Deferred rather than shipped shaky — it needs a
  careful definition of "benign domain result" per seam to avoid false positives.

## Left to first-light (operator / follow-on)

1. **Flip `resilience-floor` to a required check** in branch protection (it is
   informational-first, green today).
2. **`arxiv_oai_sync` acquire-late refactor** — buffer the harvest, then persist
   under the lock, so the network stream no longer pins the funnel. Baselined
   today; changing it touches the streaming crash/memory semantics, so it is a
   dedicated follow-on, not an in-band capstone edit.
3. **Two chaos-suite stubs** (`arxiv-missing-ssl-env`, `undersized-metadata-cache`)
   need an env-scrub scenario / cache-internals hook to replay for real; currently
   visible documented stubs.
4. **Dedicated silent-failure AST lint** (see above).
5. **First-light** itself — this lane records what is left to it; it does not run it.

# Deep-research Exa gather — Wedge 1 discovery, env-gated, stub stays default

**Date:** 2026-06-13
**Source spec:** ANT-DRL SPR-DRL-08 ("Exa gather loop")
**Status:** Ratified at implementation
**Scope:** Wedge 1 (Exa `/search` discovery) ONLY.

## Decision

The DRW browse loop gets an Exa-backed gather path wired behind an environment
gate. `make_exa_gather_loop` (in `runtime/research_runner/host_local.py`) drives
`discover(sub_question)` → `promote_discovery` (top-k) → `StepEvents`, preserving
the full `discovery_id → document_id` provenance chain on every promoted source.

The **stub gather loop stays the production default.** The seam is a single
environment variable:

```
ANTIEK_DRW_GATHER=stub   # default — hermetic, no network, honest in prod until keys land
ANTIEK_DRW_GATHER=exa    # opt-in — operator sets it after EXA_API_KEY is provisioned
```

The factory signature (`cascade_routes._research_loop_factory`) is unchanged;
the env var only selects which loop the factory returns. This keeps hermetic CI
green and keeps prod honest (no silent live calls) until the operator explicitly
flips the gate.

This is the in-loop *gather* realization of the discovery adapter contract that
`docs/integration_exa_browserbase.md` §6 ("Wedge 1 — `acquisition/search/exa`
discovery adapter") defines: `discover(query, investigation_id, ...)` emits
`DiscoveryProposed` events, promotion mints a `DiscoverySelected` event tying the
`discovery_id` to the resulting `document_id` (§6.2, step 5), and **no graph
write happens until ingestion** (§6.1). SPR-DRL-08 binds that contract to the DRW
browse loop instead of an operator-driven one-shot `discover()` call.

## Why (citation)

`docs/integration_exa_browserbase.md` §6 is the canonical contract. Wedge 1 is
the only INTEGRATE-NOW discovery item; it sets the discovery-layer shape every
future search source inherits. The load-bearing properties this decision relies on:

- §6.1 — `discover(...)` returns proposed candidates; **no graph writes until
  `ingest_url` is called**.
- §6.2 — each result carries a stable `discovery_id`; promotion emits
  `DiscoverySelected` linking `discovery_id → document_id`, so the trajectory
  shows "this document came from this Exa query."

That per-source linkage is exactly what keeps the substrate invariant intact:
every chunk cites a document, every document carries an `ip_holder_id`. A gather
path that produces per-source `document_id`s preserves the chunk → document →
`ip_holder` attribution chain end to end.

## Rejected alternative — Exa `/answer` one-call gather

**Steelman.** Exa's `/answer` endpoint does search → content fetch → LLM
synthesis in a single opaque call. It is genuinely attractive: one HTTP round
trip replaces the discover → promote → ingest → chunk → synthesize sequence; it
is cheaper per question on naive token accounting; the returned text reads like a
finished mini-answer with citations attached; and for a "just give me the gist"
browse it would feel faster and lower-friction than wiring a multi-event loop.
On a surface read it looks like a shortcut to the same destination.

**Why it is rejected anyway.** `/answer` returns synthesized prose with **no
per-source `document_id`**. The citations it attaches are links in opaque
synthesized text, not substrate documents with `ip_holder_id`s. Routing gather
through `/answer` therefore collapses the attribution chain at its root: there is
no document to chunk, so no chunk to cite, so no `ip_holder` to attribute or
(per §9) to pay. It also collapses the *trajectory* — `/answer` does retrieval +
synthesis inside one call the operator cannot replay, the verifier-tier cannot
grade, and the event log cannot reconstruct (`docs/integration_exa_browserbase.md`
§2.3, "Exa `/answer` is NOT a synthesis primitive", Hard reject §12.5). Antiek's
synthesis is a typed-event sequence by design; `/answer` is a black box that
defeats every reason that sequence exists. The cost saving is illusory because it
buys a result that cannot enter the substrate, cannot be attributed, and cannot
be audited. The discover-then-promote path costs one extra hop and keeps every
invariant; `/answer` saves the hop and breaks all of them.

## Reconsider if

- Exa ships a `/answer` (or successor) response that returns **stable per-source
  `document_id`-able URLs with replayable retrieval provenance** — i.e. the
  collapse no longer happens — AND the typed-event trajectory can be
  reconstructed from it. Then `/answer` becomes a candidate *discovery* source
  feeding the same promotion seam, not a synthesis substitute.
- The operator deprecates the typed-event synthesis trajectory in favor of an
  opaque-call posture (which would also reverse §2.3, "Exa `/answer` is NOT a
  synthesis primitive", and Hard reject §12.5). Not anticipated.

## Scope — what this does NOT touch

- **Wedge 1 only.** This decision links `docs/integration_exa_browserbase.md` §6
  and nothing else.
- **No Browserbase (Wedge 2).** The live-browsing escalation fallback inside
  `acquisition/urls/` (§7) is out of scope / deferred.
- **No Exa `/contents` (Wedge 3).** In-loop verifier-tier fact lookup (§8) is
  Phase 2, explicitly not wired here.
- **No Parallel web APIs.** Out of scope.
- The stub remains the default; nothing changes on prod until the operator
  provisions `EXA_API_KEY` and sets `ANTIEK_DRW_GATHER=exa`. The Sprint 18
  retrieval-time legal gate (§2.5) is upstream-unchanged: Exa-discovered URLs
  hit the gate exactly as manually-typed URLs do.

## Failure isolation — what is (and is not) proved

`make_exa_gather_loop` adds no try/except of its own around `discover` /
`promote_discovery`. A `discover`-level `DiscoveryBudgetExceeded` (the Exa daily
cap raised by `check_and_reserve`) or an `ExaClientError` therefore propagates to
the runner's per-leaf catch-all (`HostLocalRunner._run`), which marks **that
single leaf** `RunState.FAILED`, logs `INVESTIGATION_FAILED`, and emits one
`error`-kind `StepEvent`. This is honest per-leaf isolation: the failing leaf
surfaces its failure, siblings in the same cascade are unaffected, and **no
fabricated `doc-url-*` provenance** is emitted (the loop never reaches its
promotion notes). `tests/test_exa_gather_loop.py::test_exa_gather_loop_discover_raise_fails_leaf_cleanly`
proves this hermetically (a `discover` patched to raise the real
`DiscoveryBudgetExceeded`).

**Not proved (hermetic gate cannot reach it):**

- Partial-ingest under a mid-stream raise — i.e. the budget cap tripping *after*
  some proposals have already promoted in a single leaf — is not load-tested. The
  test raises at the first `discover` call (before any promotion), so the
  "some-ingested-then-fail" provenance shape is unverified.
- Budget-exhaustion under concurrency — many leaves racing the same Exa daily cap
  via `check_and_reserve`, where the cap trips for some leaves and not others — is
  not load-tested. The single-leaf isolation is proved; the aggregate behavior
  under contention is the live-only delta.

## Verification

The Exa gather path is exercised hermetically (mocked, no network) by
`tests/test_exa_gather_loop.py`, registered as **P-16** in
`docs/agent-execution/PLATFORM_EXEC_MATRIX.md` and run by
`./scripts/canonical_verify.sh deep-research` (after P-11..P-15, before the
`CANONICAL_VERIFY_OK: deep-research` marker). Live `EXA_API_KEY` discover→ingest
cost is the live-only delta and is **not** proved by the hermetic gate.

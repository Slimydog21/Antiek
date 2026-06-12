# Deep research Parallel Search gather (SPR-DRL-08)

**Status:** Closed (2026-06-12)  
**Operator decision:** Parallel-first for Wave 6 gather; Exa deferred to SPR-DRL-10.

## Decision

Wire **Parallel Search** (`POST https://api.parallel.ai/v1/search`) into the DRW browse loop via `make_parallel_gather_loop`, env-gated at `cascade_routes._research_loop_factory`:

- Default: `ANTIEK_DRW_GATHER=stub` → `make_contract_gather_stub` (hermetic CI)
- Operator prod: `ANTIEK_DRW_GATHER=parallel` + `PARALLEL_API_KEY` in `.env`

Flow per leaf investigation:

1. `discover(sub_question)` → `DiscoveryProposed` events (`provider=parallel`, `disc-parallel-*` ids)
2. Auto-promote top-k via `promote_discovery` → `ingest_url` (single graph-write seam)
3. `StepEvent`s carry `gather_mode=parallel`, `discovery_id`, `document_id`

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Exa-first (pre-contract) | Terminal contract undefined until SPR-DRL-01..04 |
| Exa Wedge 1 in SPR-DRL-08 | Operator ratified Parallel-first |
| Parallel Task API one-call research | Collapses attribution chain (same failure mode as Exa `/answer`) |
| Direct graph writes from search results | Breaks substrate provenance; all docs via `ingest_url` |

## Verification

- Hermetic: `pytest tests/test_parallel_gather_loop.py -q` (httpx `MockTransport` only)
- Profile: `./scripts/canonical_verify.sh deep-research` includes P-16

## Not proved (operator)

- Live Parallel index blind spots on operator queries
- End-to-end prod pack with real fetched documents (HTTP ingest latency)
- Parallel daily spend cap (no sidecar yet; cost estimate on proposals only)

## Reconsider if

- Parallel Search latency or index gaps block operator DRW sessions → evaluate Exa Wedge 1 (SPR-DRL-10)
- Legal gate rejection rate on auto-promote top-k exceeds tolerance → operator review UI
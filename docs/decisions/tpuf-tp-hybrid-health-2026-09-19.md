# Decision: TurboPuffer SERVABLE hybrid on Thought Partner + /health

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: #3135 reuse hybrid; `resolve_reuse_substrate_kind`; master dual-structure (DuckDB SoT; TP SERVABLE-only); rollup TurboPuffer ~72.

## Context

Hybrid mount was env-gated for cascade/flywheel reuse only. `POST /thought-partner`
library grounding still called DuckDB `search()` directly — so corpus SERVABLE
index never reached Surface E / AISidecar / Dialogue. `/health` also hid dogfood
status (`production_default_mount` stayed an opaque False inside the adapter).

## Decision

1. `_retrieve_thought_partner_context` uses the same `resolve_reuse_substrate_kind`
   gate: when turbopuffer, `make_substrate_from_con` + `query(policy_tag=…)`.
   Non-`attribution_eligible` stays DuckDB inside the adapter.
2. `/health` reports honest TurboPuffer fields (`servable_enabled`,
   `api_key_present`, `active_pointer`, `hybrid_ready`, `resolved_kind`) via
   `probe_turbopuffer_health` (no vendor network). **`production_default_mount`
   remains False** — do not fake readiness.
3. `ANTIEK_TURBOPUFFER_MANIFEST_DIR` overrides the promote-pointer directory.

## Non-goals

- Flipping production default mount.
- Talk-to-book book-scoped `/books/{id}/ask` corpus hybrid (book-local stays).
- Indexing gated / private content into TurboPuffer.

## Consequences

TP UI library grounding can hit the SERVABLE hybrid when env+key+promote are
live. Operators see dogfood status on `/health` without grepping manifests.

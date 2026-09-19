# Decision: TP SERVABLE reading mount (auto book/page context)

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: #3135 TurboPuffer hybrid (attribution_eligible → TP; gated→DuckDB); `ThoughtPartnerRequest.system_context`; BookReader `ownerReadable` / `servable_full_text`; Surface E / AISidecar / FloatMenu Dialogue.

## Context

Thought Partner retrieved library notes via `_retrieve_thought_partner_context` and accepted optional `system_context` from ContextPicker / workspace JSON — but the open book page was never auto-mounted. Operators had to @-compose or rely on FloatMenu selection Dialogue alone.

## Decision

1. Client `readingFocus` bus: Reading mode publishes `{documentId, pageIndex, title, pageText?, servable}`.
2. **Dual structure**: `servable === false` never retains or formats page body — honest withheld stub only.
3. `composeThoughtPartnerSystemContext()` merges reading focus into every TP post (AISidecar, Surface E, Dialogue) after picker/workspace base — no manual @-compose required on the reading path.
4. Server retrieval path unchanged (#3135 / DuckDB search + policy_tag). No TurboPuffer for gated content.

## Non-goals

- Replacing TalkToBook (`/books/{id}/ask`).
- Server re-fetch of page body on `/thought-partner` (client mount is enough for SERVABLE; gated stays empty).
- Inventing a new product surface.

## Consequences

Reading → ⌘/ Thought Partner / Surface E / Dialogue sees current SERVABLE page automatically. Next: composite 100 rollup.

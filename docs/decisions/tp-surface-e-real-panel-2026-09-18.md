# Decision: Surface E thought-partner pane is real (not CTA)

**Date**: 2026-09-18  
**Status**: accepted  
**Cite**: `docs/master-product-spec.md` §4.5; `docs/anti-ek-vision-map-2026-09-17.md` pillar 2; `roles/thought_partner/program.md`; Herdr Antiek w7.

## Context

Thinking Partner graded ~45 vs Speak/Research: substrate role + `POST /thought-partner` + AISidecar + in-book FloatMenu Dialogue + TalkToBook (`/books/{id}/ask`) already existed, but Surface E's docked **Thought partner** panel was still a Sprint-17 placeholder that only toggled the sidecar. Dialogue also discarded the role's CHALLENGE/SYNTHESIS/EXTENSION `shape`.

## Decision

1. Replace `ThoughtPartnerPanel` CTA with a real one-shot `/thought-partner` composer (ContextPicker + shape display + @@actions parse) — same endpoint as AISidecar / Dialogue.
2. Shared seed bus `antiek:thought-partner:seed` (`thoughtPartnerSeed.ts`): BrainstormStation seeds on parked-question select; AISidecar listens too.
3. Surface `shape` on FloatMenu Dialogue replies (API already returned it).

## Non-goals (honest residual)

- Lego-block drag slotting of graph insights into the pane.
- Multi-turn TP thread (TalkToBook remains the book multi-turn path).
- SERVABLE book auto-mount into TP `system_context` without @-compose.
- Voice-note → park → discuss end-to-end polish.
- Unifying TalkToBook (`/books/ask`) onto the `thought_partner` role.

## Consequences

Daily-use Surface E finally hosts the active thought-partner component beside watch-for-later. Reading Dialogue exposes role shapes. Next gaps: notebook polish / TP SERVABLE mount / composite 100.

# Decision: Voice note → park → Thought Partner discuss (reading path)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** Read SPR-06 voice notes; master-spec §4.5 Surface E watch-for-later;
`thoughtPartnerSeed` / SERVABLE reading mount (#3135); composite residual
voice→park→TP.

## Context

Pieces already existed in isolation:

- `VoiceNote` → `POST /books/{id}/voice-note` → `note.emerged`
- Watch-for-later ← `question.identified`
- BrainstormStation / AISidecar listen on `antiek:thought-partner:seed`
- `composeThoughtPartnerSystemContext()` appends the current book page

The reading path never parked voice questions or seeded TP with the reading
mount after save — blocking TP literal 100.

## Decision

1. **Park (substrate):** After voice distill, emit `question.identified` for
   question-shaped notes (`?` or interrogative opener). If none, park the
   transcript when it itself looks like a question. Anchor =
   `book_page:{page_index}`. Return `parked_question_ids` / `_texts` on the
   HTTP response.
2. **Discuss (reading UI):** On save with parks, dispatch
   `THOUGHT_PARTNER_SEED_EVENT` with prompt +
   `composeThoughtPartnerSystemContext()` + `Discuss in Thought Partner`
   affordance to re-seed.
3. **Surface E:** Parked-question select also passes reading-mount
   `system_context` (same helper) — no new product surface.

## Non-goals

- New park storage table (event log remains SoT).
- Inventing a separate “voice discuss” mode.
- Requiring BrainstormStation to be open for reading-path seed (sidecar /
  Surface E both listen on the shared bus).

## Consequences

Voice → park → discuss works on the reading path. Watch-for-later lists the
same parks. Dual structure unchanged.

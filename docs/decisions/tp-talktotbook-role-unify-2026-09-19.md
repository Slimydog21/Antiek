# Decision: TalkToBook ↔ thought_partner role unify

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: master-spec §4.5; `roles/thought_partner/*`; `substrate/books/book_qa.py`; Surface E / AISidecar / FloatMenu Dialogue; anti-ek rollup residual 3; #3169 SERVABLE mount.

## Context

Reading daily loop had two partner personalities: TalkToBook (`POST /books/{id}/ask` → `user_agent`) and Thought Partner (`POST /thought-partner` → `thought_partner` + shapes). Same operator, same book, different voice — residual blocking TP 100.

## Decision

1. **One role**: `answer_book_question` dispatches `thought_partner` (compose + system prompt + parse shape). Book chunks map to `selected_notes` (same shape as `_retrieve_thought_partner_context`).
2. **Dual structure kept**: `/books/{id}/ask` remains the book-scoped retrieval + page-citation + multi-turn path; `/thought-partner` remains library-wide one-shot. Not a merge of HTTP surfaces.
3. **Display**: API returns `shape`; TalkToBook labels replies `thought partner · {shape}` and bookmark copy says Thought partner (this book).
4. **Ungrounded** path unchanged (no dispatch, no shape).

## Non-goals

- Deleting `/books/{id}/ask` or converting TalkToBook to one-shot.
- Lego insight slotting into TP pane.
- Inventing a third partner surface.

## Consequences

Reading path feels like one partner. TP grade climbs. Next: flywheel_ready on prod or CLI/Herdr.

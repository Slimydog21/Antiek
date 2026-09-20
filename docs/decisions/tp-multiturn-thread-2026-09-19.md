# Decision: Multi-turn Thought Partner thread (Surface E / AISidecar)

**Date**: 2026-09-19 (Asia/Riyadh)
**Status**: accepted
**Cite**: TalkToBook `useTalkThread`; `POST /thought-partner`; SERVABLE reading mount; Lego insight slotting.

## Context

TalkToBook already kept a multi-turn thread (`history` on `/books/{id}/ask`).
Surface E `ThoughtPartnerPanel` and AISidecar were one-shot (`reply` replaced
each send), so follow-ups lost prior turns even though reading mount + Lego
focus tray stayed put.

## Decision

1. Optional `history: [{question, answer}]` on `ThoughtPartnerRequest` (max 8),
   folded into `compose_thought_partner_prompt` as prior conversation — same
   bound spirit as `book_qa.MAX_HISTORY_TURNS`.
2. Client `useThoughtPartnerThread`: sessionStorage thread scoped by reading
   `documentId` or `__workspace__`; Surface E + AISidecar share it.
3. Each send posts completed-turn history; Lego slots + ContextPicker +
   SERVABLE `composeThoughtPartnerSystemContext` unchanged per turn.
4. Shapes (CHALLENGE / SYNTHESIS / EXTENSION) still returned and displayed
   per message.

## Non-goals

- Merging HTTP surfaces (`/thought-partner` vs `/books/ask`).
- DuckDB persistence of the TP chat (session view-state only).
- FloatMenu Dialogue multi-turn (selection stays one-shot).

## Consequences

TP daily-use on reading + Brainstorm keeps a conversation. Dual structure
intact. Next: PDF→HTML or composite 100 rollup.

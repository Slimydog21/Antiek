# Decision: Notebook continuity polish (outline→Write / citations / distill)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** notebook-daily-loop-polish-2026-09-19 (#3168); outline-write-auto-import-2026-09-19 (#3174); SPR-06 AutoNotebook; DistillView.

## Context

Daily loop handoffs existed but frayed: Write required re-typing a title before ConnectResearch appeared; citations showed raw document ids; outline items were not jump links; NotebookLoopNav “distill” duplicated “back to research”; NotebooksIndex never named the auto-notebook.

## Decision

1. `writeHandoffHref(investigation, title?)` → `/write?investigation=&title=`; AutoNotebook LoopNav + **Import outline into Write →** pass the real notebook title.
2. WriteHome honors `?title=` prefill + `write-from-notebook-banner` when `?investigation=` is set.
3. Grounded insight citations link to `/read/:documentId` (no invented sources).
4. Outline entries are in-page anchors (`#notebook-section-*`).
5. Distill continuity: `/inv/:id#distill` + `id="distill"` scrollIntoView.
6. NotebooksIndex honesty blurb: TipTap = manual; auto-notebook = derived `/notebook/auto/:id`.

## Non-goals

- New DuckDB notebook store.
- Merging TipTap NotebooksIndex with AutoNotebook.
- Fabricating outline sections without synthesis (from-investigation 404 path unchanged).

## Consequences

Notebook daily-loop grade rises on honest continuity surfaces without inventing content or money.

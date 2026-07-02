# Golden-path walk evidence — SPR-09 (activation SPR-01)

**Walked:** 2026-06-30 · **Branch:** `caffen/RDR-SPR-09` · **Harness:** `apps/reading/e2e/operator-day.spec.ts` (extended) + Storybook iframe

**INERT-AI banner (every AI step):** Dialogue and research spin-out are **cassette / inert until activation SPR-03 provider keys**. Green here means wiring is correct, not that the operator can feel live AI.

| Step | Activation SPR-01 intent | Evidence | Label |
|------|--------------------------|----------|-------|
| **1 · Open a paper** | Rich typography over the SPR-02 document model (headings, lists, tables, code, math, figures) | Storybook `reader--the-one-reader--every-block-type`; e2e asserts `[data-reader-root]`, `h1[data-block-type="heading"]`, `table[data-block-type="table"]`, KaTeX `.katex` node | **REAL** — SPR-03 `<Reader>` at `apps/reading/src/components/reader/Reader.tsx:129` |
| **2 · Select text** | Highlight gesture opens the shared FloatMenu on the reading surface | Rich `p[data-block-type="paragraph"]` is selectable in the Reader story; in-book FloatMenu host proven in `Reading.test.tsx:962` (`articleRef` scope survives on rich path) | **REAL** — `apps/reading/src/modes/shared/FloatMenu/FloatMenu.tsx` mounted by `modes/Reading/index.tsx` |
| **3 · Dialogue thread** | Passage-anchored multi-turn thread (SPR-06) | e2e records `cassette/inert-until-SPR-03-keys`; no live `/api/passage-dialogue` in Storybook CI | **INERT** — `floatMenuActions.ts:184` `buildDialoguePrompt`; awaits **activation SPR-03 provider keys** |
| **4 · Research spin-out** | Deep-research escalation from the passage (SPR-04 loop) | e2e records `cassette/inert-until-SPR-03-keys`; `startInvestigation` boundary mocked in unit tests | **INERT** — `FloatMenu` → `startInvestigation` (`floatMenuActions.ts:27-28`); awaits **activation SPR-03 provider keys** |
| **5 · Citation opens source** | Clicking a `citation` span opens the **real ingested source** in the one Reader (SPR-07), not a link-out | Reader unit coverage clicks `button[data-citation-marker][data-source-document-id="doc-source-42"]` and navigates to `/read/doc-source-42?chunk=chunk-7&from=doc-1&fromPage=0&fromTitle=A+Servable+Book` | **REAL** — `apps/reading/src/components/reader/blocks/Citation.tsx`; resolver `lib/openDocument.ts:205` |
| **6 · Return to original paper** | The cited source view exposes a return flow that preserves the original Reader document/page context closely enough to continue reading | Reader unit coverage loads `/read/doc-source-42?chunk=chunk-7&from=doc-1&fromPage=1&fromTitle=A+Servable+Book`, clicks the return action, and navigates to `/read/doc-1?page=1` | **REAL** — `apps/reading/src/modes/Reading/index.tsx` parses `from`, `fromPage`, and `fromTitle` into the shared `openDocument` resolver |

## Manual walk notes (hand-walked alongside e2e)

- Step 1 rendered every block type in the fixture story — no flattener fallback on structured docs.
- Steps 3–4 deliberately do **not** claim live model output; cassettes only.
- Step 5 proves provenance triple (`source_document_id` + `chunk_id`) routes through `openDocument`, not `window.open` or `/wrestle/:id`.
- Step 6 proves the source jump carries return-origin context; dogfood still must record whether scroll/selection/context felt good enough during real reading.

## Pointer for activation SPR-05

Activation should re-walk this table on the **deployed** build with real keys (SPR-03) and record operator verdicts per step in the dogfood log (SPR-07).

# Golden-path walk evidence — SPR-09 (activation SPR-01)

**Walked:** 2026-06-30 · **Branch:** `caffen/RDR-SPR-09` · **Harness:** `apps/reading/e2e/operator-day.spec.ts` (extended) + Storybook iframe. **Updated on `reader/integration`:** `apps/reading/e2e/read-golden-path.spec.ts` now proxies steps 1-6 through the real `/read/:documentId` route.

**INERT-AI banner (every AI step):** Dialogue and research spin-out are **cassette / inert until activation SPR-03 provider keys**. Green here means wiring is correct, not that the operator can feel live AI.

| Step | Activation SPR-01 intent | Evidence | Label |
|------|--------------------------|----------|-------|
| **1 · Open a paper** | Rich typography over the SPR-02 document model (headings, lists, tables, code, math, figures) | Storybook `reader--the-one-reader--every-block-type`; real-route e2e asserts `[data-reader-root]`, heading, and readable paragraph at `/read/doc-1` | **REAL** — SPR-03 `<Reader>` at `apps/reading/src/components/reader/Reader.tsx:129` |
| **2 · Select text** | Highlight gesture opens the shared FloatMenu on the reading surface | Real-route e2e performs a browser mouse drag over `[data-reader-root] p` and asserts the `Highlight actions` menu | **REAL** — `apps/reading/src/modes/shared/FloatMenu/FloatMenu.tsx` mounted by `modes/Reading/index.tsx` |
| **3 · Dialogue thread** | Passage-anchored multi-turn thread (SPR-06) | Real-route e2e opens Dialogue from the FloatMenu, stubs `/thought-partner/stream` as no-provider, and asserts the honest activation SPR-03 boundary | **INERT** — `floatMenuActions.ts:184` `buildDialoguePrompt`; awaits **activation SPR-03 provider keys** |
| **4 · Research spin-out** | Deep-research escalation from the passage (SPR-04 loop) | Real-route e2e opens Deep-research from the FloatMenu, stubs `POST /investigations` as no-provider, and asserts the honest activation SPR-03 boundary in `ChaseThread` | **INERT** — `FloatMenu` → `ChaseThread` → `startInvestigation`; awaits **activation SPR-03 provider keys** |
| **5 · Citation opens source** | Clicking a `citation` span opens the **real ingested source** in the one Reader (SPR-07), not a link-out | Real-route e2e clicks `Open the cited source [1]` and navigates to `/read/doc-source-42?chunk=chunk-7&from=doc-1&fromPage=0&fromTitle=A+Servable+Book` | **REAL** — `apps/reading/src/components/reader/blocks/Citation.tsx`; resolver `lib/openDocument.ts:205` |
| **6 · Return to original paper** | The cited source view exposes a return flow that preserves the original Reader document/page context closely enough to continue reading | Real-route e2e clicks `Return to A Servable Book` and lands on `/read/doc-1?page=0` with `Chapter One` visible | **REAL** — `apps/reading/src/modes/Reading/index.tsx` parses `from`, `fromPage`, and `fromTitle` into the shared `openDocument` resolver |
| **7 · Operator dogfood** | Read for 20+ minutes and record whether the surface felt good enough for sustained work | `tools/activation/read_dogfood.py` requires `minutes_reading >= 20`, step 7 `operator_note`, 10 valid sessions, live-provider/citation/non-Library coverage, and final verdict `ACTIVATE` | **NOT CLOSED BY CI** — activation SPR-07 operator log is the product done-bar |

## Manual walk notes (hand-walked alongside e2e)

- Step 1 rendered every block type in the fixture story — no flattener fallback on structured docs.
- Steps 3–4 deliberately do **not** claim live model output; cassettes only.
- Step 5 proves provenance triple (`source_document_id` + `chunk_id`) routes through `openDocument`, not `window.open` or `/wrestle/:id`.
- Step 6 proves the source jump carries return-origin context; dogfood still must record whether scroll/selection/context felt good enough during real reading.
- Step 7 cannot be simulated by CI. It is enforced only by the operator-authored JSONL log and `tools/activation/read_dogfood.py`.

## Pointer for activation SPR-05

Activation should re-walk this table on the **deployed** build with real keys (SPR-03) and record operator verdicts per step in the dogfood log (SPR-07).

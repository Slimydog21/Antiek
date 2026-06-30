# Handoff to activation — antiek-reader SPR-09 → activation SPR-05/07

**Generated:** 2026-06-30 · **Branch:** `caffen/RDR-SPR-09` (not merged to `reader/integration` yet)

## NON-CLOSURE (read first — governance act)

**Read is NOT done.** This sprint's CI green is **necessary, not sufficient**. The product done-bar is **activation SPR-07's 10-day operator dogfood** — which no CI can close. Anyone who infers "Read is done" from green gates is misled: the **operator** (who would skip the walk that catches what cassettes hide) and **future instances** (who would inherit false closure). The sibling pact holds: **CI is the floor; USE is the gate.**

---

## Real vs inert (itemized)

| Capability | Status | Location (`file:line`) | Awaits |
|------------|--------|------------------------|--------|
| One `<Reader>` body renderer | **REAL** | `apps/reading/src/components/reader/Reader.tsx:129` (`data-reader-root`) | — |
| `openDocument(id, opts)` resolver | **REAL** | `apps/reading/src/lib/openDocument.ts:59` (`buildReaderTarget`), `:205` (`useOpenDocument`) | — |
| Canonical Reader route | **REAL** | `apps/reading/src/App.tsx:161` (`/read/:documentId` → `BookReader`) | — |
| §9.0 serve gate (structured body) | **REAL** | `substrate/books/serve.py:99` (`serve_full_text`); BookReader gate `modes/Reading/index.tsx:119` | — |
| Structured ingest (urls + arXiv) | **REAL** | `acquisition/urls/adapter.py`, `acquisition/arxiv/adapter.py` (SPR-02 handoff) | — |
| Door convergence (11 OPEN doors) | **REAL** | `apps/reading/src/__tests__/oneReader.conformance.test.ts` door (a); `migration-map.md` §2 | — |
| Forbidden renderer seams gone | **REAL** | `oneReader.conformance.test.ts` door (b) + tree-wide guard | — |
| Provenance citation → real source open | **REAL** | `apps/reading/src/components/reader/blocks/Citation.tsx`; DRW `modes/DeepResearchWorkspace/index.tsx:197` | — |
| UnifiedSearch local vector | **REAL** (no key) | `apps/reading/src/components/UnifiedSearch.tsx` | — |
| Conformance regression guard | **REAL** | `substrate/contracts/__tests__/test_reader_conformance.py`; `oneReader.conformance.test.ts` | — |
| Unification proof (4 entry points) | **REAL** | `oneReader.conformance.test.ts` M3 block | — |
| Highlight Dialogue (SPR-06) | **INERT** | `apps/reading/src/modes/shared/FloatMenu/floatMenuActions.ts:184` | **activation SPR-03 provider keys** |
| Research loop / deep-research spin-out (SPR-04) | **INERT** | `FloatMenu` → `startInvestigation` (`floatMenuActions.ts:27-28`); backend `interfaces/research/api/cascade_routes.py` | **activation SPR-03 provider keys** |
| Enter-escalate agentic search (SPR-08) | **INERT** | `apps/reading/src/components/UnifiedSearch.tsx` + `useStartInvestigation` | **activation SPR-03 provider keys** |
| Operator dogfood closure | **NOT THIS SPRINT** | activation SPR-07 | **10 distinct operator sessions** |

---

## What activation SPR-05 should walk

Follow **`walk-evidence.md`** step-by-step on the deployed build:

1. Open a real corpus paper → confirm rich Reader typography.
2. Select text → FloatMenu appears with four actions.
3. Dialogue → **requires SPR-03 keys**; score against activation SPR-01 rubric.
4. Research spin-out → **requires SPR-03 keys**.
5. Click a citation → same Reader opens the ingested source at the cited chunk.

Golden-path script authority: activation SPR-01 (`specs/activation/golden-path.md` when frozen).

---

## Prior sprint handoffs reconciled

| Sprint | Status | SPR-09 reconciliation |
|--------|--------|----------------------|
| SPR-02 ingest | Done | Round-trip leg (c) proven in `test_reader_conformance.py::test_document_survives_ingest_store_serve_render_round_trip` |
| SPR-03 Reader | Done | Conformance imports real `Reader`; Reader.test.tsx block-type suite green |
| SPR-04 research loop | Built, inert | Golden-path step 4 labelled cassette; no claim of live operator research |
| SPR-05 one door | Done | Door (a)/(b) assertions green; lying seam test **deleted** |
| SPR-06 Dialogue | Done, inert | Golden-path step 3 labelled cassette; graph anchor real, live model awaits keys |
| SPR-07 provenance | Done | Citation step REAL; `test_provenance_ingestion_spr07.py` cited in SPR-07 handoff |
| SPR-08 search | Done | Fourth unification entry point; escalate inert per SPR-08 handoff |

No contradiction with prior handoffs: partial surfaces (Research/Write FloatMenu anchor) remain deferred per SPR-06 handoff.

---

## Steelman: "it's all green — call Read done"

**Strongest case:** Every door routes to one Reader, forbidden renderers are gone, conformance imports the production tree, provenance opens real sources, search converges, and the suite is green — so ship and declare Read done.

**Why USE-is-the-gate still wins:** Cassettes prove structure, not feel. Activation SPR-05 unboxing and SPR-07 dogfood catch latency, dead-ends, and mediocre first answers that CI cannot see. Premature "done" misleads the operator into skipping the walk and misleads future instances into building on a false closure.

---

## Verification gates (SPR-09)

```bash
.venv/bin/python -m pytest substrate/contracts/__tests__/test_reader_conformance.py -q
# 9 passed

cd apps/reading && npm test -- --run src/__tests__/oneReader.conformance.test.ts
# 27 passed

cd apps/reading && npx tsc -b
# exit 0
```

Old lying test: `tests/test_seam_reader_surface_contract.py` — **DELETED** (grep returns nothing).
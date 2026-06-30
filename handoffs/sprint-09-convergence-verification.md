## Sprint SPR-09 — Handoff (capstone → activation)

### Status
**done** (prove-only; no features)

### Honesty banner — DO NOT DROP
CI green here is **necessary, not sufficient**. **Read is NOT done.** Product done-bar = **activation SPR-07 dogfood**, not this sprint's gates.

### Deliverables
- `substrate/contracts/__tests__/test_reader_conformance.py` — REAL conformance (doors a/b/c green)
- `apps/reading/src/__tests__/oneReader.conformance.test.ts` — door convergence + unification proof (M3)
- `tests/test_seam_reader_surface_contract.py` — **DELETED** (was green-but-lying)
- `apps/reading/e2e/operator-day.spec.ts` — golden-path extension (cassette AI)
- `~/specs/antiek-reader/walk-evidence.md` — per-step evidence + INERT labels
- `~/specs/antiek-reader/handoff-to-activation.md` — real vs inert table for activation SPR-05
- `~/specs/antiek-reader/README.md` — non-closure note (M5)

### Milestones
- [x] M1 real conformance green; lying test deleted; forbidden-import catch test bites
- [x] M2 golden path in e2e + walk-evidence.md (cassette/inert on AI steps)
- [x] M3 unification proof — same `document_id`, 4 entry points, identical `[data-reader-root]` DOM
- [x] M4 handoff-to-activation.md (real vs inert, file:line, reconciled SPR-02..08)
- [x] M5 non-closure in handoff + README

### Verification gate results
| Gate | Result |
|------|--------|
| conformance (Python) | **pass** — 9 passed |
| conformance (TS) | **pass** — 27 passed |
| tsc | **pass** |
| lying test deleted | **pass** — file absent |
| unification | **pass** — 3 tests in M3 block |
| golden-path e2e | **added** — requires Storybook for `npm run e2e` (not in required gate list) |
| handoff / non-closure | **pass** — artifacts at `~/specs/antiek-reader/` |

### Gate commands + results
```bash
.venv/bin/python -m pytest substrate/contracts/__tests__/test_reader_conformance.py -q
# 9 passed

cd apps/reading && npm test -- --run src/__tests__/oneReader.conformance.test.ts
# 27 passed

cd apps/reading && npx tsc -b
# exit 0
```

### REAL now (structurally converged, CI-proven)
- one `<Reader>` behind every door: `apps/reading/src/components/reader/Reader.tsx:129`
- `openDocument(id, opts)`: `apps/reading/src/lib/openDocument.ts:59`, `:205`
- four redundant open renderers converged: conformance door (b) + `migration-map.md` §5
- provenance citation → real source: `components/reader/blocks/Citation.tsx`; DRW `index.tsx:197`
- ingest→serve round-trip: `test_reader_conformance.py::test_document_survives_ingest_store_serve_render_round_trip`

### INERT until activation SPR-03 keys
- Dialogue (SPR-06): `floatMenuActions.ts:184` — awaits provider keys
- research loop (SPR-04): `floatMenuActions.ts:27-28` / `cascade_routes.py` — awaits provider keys
- escalate-to-agentic search (SPR-08): `UnifiedSearch.tsx` — awaits provider keys

### What activation SPR-05 should walk
`~/specs/antiek-reader/walk-evidence.md` — five steps, AI steps labelled cassette/inert.

### Steelman + verdict
See `handoff-to-activation.md` — green does not close the product; activation SPR-07 dogfood does.

### Blockers
None for SPR-09 scope. **Not merged** to `reader/integration` per sprint instructions.

### Next can start when
Branch merges: activation SPR-05 walks deployed surface; SPR-03 keys light inert gestures; SPR-07 dogfood closes done-bar.
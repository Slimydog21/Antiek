# ANT-AHT caffenagent run ledger

**Spec:** `docs/htmlspec/antiek-html-transport/index.html`  
**Gate:** P-18 `./scripts/canonical_verify.sh html-transport`  
**Cycle:** 1 · **Phase:** `done` · **Verdict:** `done-no-ship` → **committed** `d3f30c42` on `main` (local; push/PR = operator)  
**exec-7 (2026-06-24):** Re-invoked `/caffenagent-cycle` — no new sprint scope; fast proof 6 pytest + 3 vitest green; landscape rebuilt (75 rows).  
**exec-8 (2026-06-24):** Added `docs/html/ant-aht-vision-map.html` — answers “is agent form factor in htmlspec?” with tabbed vision→spec→code map + copy handoff.

## Sprint closure (SPR-AHT-01…06)

| Sprint | Deliverable | Proof |
|--------|-------------|-------|
| 01 | `ResearchArtifactBody` v1, dual-channel render | `tests/test_research_artifact_template.py` |
| 02 | Export + `artifact.generated` | `tests/test_research_artifact_export.py` |
| 03 | `RESEARCH_ARTIFACT_TRANSPORT.md` + two-way notes UI | `substrate/research_artifact/render.py` |
| 04 | Reader snapshot on URL ingest | `tests/test_reader_snapshot.py`, env `ANTIEK_READER_SNAPSHOT` |
| 05 | Compose / merge index | `tests/test_research_artifact_compose.py` |
| 06 | FastAPI routes + Write shelf | `tests/test_artifact_routes.py`, `ArtifactOutlineShelf.tsx` |

## exec-6 (2026-06-24) — resume fix

- **Finding:** `test_canonical_verify_html_transport_hermetic` failed — artifact HTTP returned 404 in full pytest bundle.
- **Cause:** `artifact_router` existed in `artifact_routes.py` but was never `include_router`'d in `create_app()`.
- **Fix:** One-line inclusion beside distill/cascade routers in `interfaces/research/api/app.py`.
- **Re-verify:** `./scripts/canonical_verify.sh html-transport` → **13 passed**, `CANONICAL_VERIFY_OK: html-transport`, exit 0 (2026-06-24, ~7m46s wall).

## HTML assets (Thariq thesis)

- **Landscape:** `docs/html/html-landscape.html` (inventory + use-case grid)
- **Operator guide:** `docs/html/ant-aht-operator-guide.html`
- **htmlspec pages:** `docs/htmlspec/antiek-html-transport/sprint-*.html`

## steipete gates

| Phase | Skill | Status |
|-------|-------|--------|
| egghead-2 | github-deep-review | N/A — no open PR; diff reviewed inline |
| exec-1 | create-cli | `substrate/research_artifact/__main__.py` |
| hardenx-1 | hardenx --strict | substrate/research_artifact (prior session) |

## Not proved (P-18 matrix)

- Full Write canvas tab-complete
- Book/EPUB reader HTML ingest

## Operator next

1. **PRcrouch** — commit uncommitted ANT-AHT + exec-6 router fix; CI must pass P-18.
2. **New ledger** — if book ingest or full Write UI is priority, spawn new htmlspec subtree (not re-grind 01–06).
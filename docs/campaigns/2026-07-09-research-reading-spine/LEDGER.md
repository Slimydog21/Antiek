# Campaign ledger — research/reading residual (2026-07-09+)

**Honest scope:** Finite residual slices only. Not infinite platform finish.

| Field | Value |
|---|---|
| Branch | `campaign/research-reading-spine-2026-07-09-main` |
| PR | https://github.com/Slimydog21/Antiek/pull/465 |

## Cycles

| Cycle | Package | Status |
|---|---|---|
| 1–9 | spine … Settings decision-tree install | done |
| 10 | **Highlight → session + deep-research window product path** | **done** |

## Cycle 10 details

| Item | Status |
|---|---|
| `open_deep_research_from_highlight` (Python) | done |
| `openDeepResearchFromHighlight` (TS) | done |
| Stable re-invoke (same region/session/window) | done |
| HTML-first payload | done |

## Non-claims

No browser Playwright e2e; does not replace chase-launcher write path; operator merges only.
## residual (al) Settings suite-proposal visibility — 2026-07-09
- settings_suite_proposal_payload + GET /settings/antiek-bench/suite-proposal
- Settings panel data-testid antiek-bench-suite-proposal-panel; view_format html
- tests: test_settings_suite_proposal.py (4) + Settings.test.tsx suite proposal case
- NEVER auto-promote; empty usage → has_proposal=false
## residual (am) Settings suite approve/promote — 2026-07-09
- POST /settings/antiek-bench/suite-proposal/approve
- settings_approve_suite_proposal_payload; UI gate buttons
- GET propose path remains non-promoting
## residual (an) merge draft/parent product path — 2026-07-09
- POST /engagement/merge via merge_product_payload
- draft_combined default; parent left untouched
- tests/test_engagement_merge_product.py (4)
## residual (ao) CollectiveResearchPanel document merge UI — 2026-07-09
- draft_combined + into_parent actions on multi-select panel
- host passes parentAssetId
## residual (ap) competitive deep-research notes→spec — 2026-07-09
- docs/htmlspec/competitive-deep-research/VERDICT.md + index.html
- backlog aq–av for hydrate/telemetry/evidence/tiers/dogfood
## residual (gd) Write open-piece HTML re-import — 2026-07-09
- importHtmlDraftIntoDeliverable shared chokepoint (create + re-import)
- Load html_draft on open piece; section_index offset; seedTwins:false
- UI: write-piece-html-reimport / write-piece-reimport-run / status
- tests: WriteHome.test.tsx 14 passed
## residual (ge) Write piece deep research + pub refs — 2026-07-09
- write-piece-research-launch panel: pubs + budget + float|full
- launchFloatingDeepResearch + hydratePublicationRefs shared paths
- tests: WriteHome.test.tsx 15 passed
## residual (gf) Write piece collective multi-select — 2026-07-09
- write-piece-collective-mount when collectDeepResearchSpawnIds non-empty
- parentAssetId=deliverable; onDocMerged remounts context
- tests: WriteHome.test.tsx 17 passed

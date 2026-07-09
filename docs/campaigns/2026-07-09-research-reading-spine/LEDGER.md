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
## residual (gg) Write twins remount key — 2026-07-09
- write-piece-twins-refresh shares contextRefreshKey with context panel
- TwinNotesPanel remounts on promote/DR/collective/re-import
- NEXT-WAVE-after-gf.md map; tests: WriteHome 18 passed
## residual (gh) Write DR live selection budget — 2026-07-09
- write-piece-selection-preview + clear highlight
- ResearchLaunchBudgetPanel promptText tracks highlight
- tests: WriteHome 19 passed
## residual (gi) Marketplace → Write HTML draft handoff — 2026-07-09
- marketplace-open-write on host-result
- library-open-write-{document_id} on library rows
- tests: MarketplaceHost 5 passed
## residual (gj) Marketplace host twin seed — 2026-07-09
- seedTwinNotes force_offline after host/purchase
- marketplace-twin-seed-status UI
- tests: MarketplaceHost 5 passed
## residual (gk) Midnight Oil deposit twin reseed — 2026-07-09
- seedTwinNotes force_offline after deposit + auto-deposit
- moil-twin-reseed-status UI
- tests: MidnightOil 6 passed
## residual (gl) Midnight Oil deposit progress panel — 2026-07-09
- moil-deposit-progress-mount + ResearchProgressPanel per spawn_id
- autoLoad + autoSeedIfEmpty
- tests: MidnightOil 6 passed
## residual (gm) Research depth tier picker flash|pro|wrestle — 2026-07-09
- ResearchLaunchBudgetPanel allowTierPick + wrestle projection
- Write piece enables picker
- tests: ResearchLaunchBudgetPanel 8 + WriteHome 19
## residual (gn) depth-tier picker flywheel — 2026-07-09
- allowTierPick on hosted book, Midnight Oil, collective continue
- tests: HostedHtml 10 + MidnightOil 6 + Collective 8
## residual (go) workstation depth-tier picker — 2026-07-09
- allowTierPick on DR session host, ResearchThis, StartResearch, ChatInput
- tests: DeepResearchSessionHost 22 + ResearchThis 7 + ChatInput budget 1
## residual (gp) wrestle research tier closed-set — 2026-07-09
- RESEARCH_TIERS += wrestle; zai_reasoning/glm-5.2
- StartResearch Fast|Deep|Wrestle; TS ResearchTier
- tests: test_research_tier_dispatch 23 passed
## residual (gq) wrestle type alignment — 2026-07-09
- books.ts research_tier + Talk opts include wrestle
- generated/types.ts research_tier Literal += wrestle
## residual (gr) wrestle budget pick → startInvestigation — 2026-07-09
- StartResearch onResearchTierChange=setTier
- ChatInputArea launchTier + research_tier on POST
- tests: StartResearch 17 + ChatInputArea.budget 2
## residual (gs) Midnight Oil research_tier — 2026-07-09
- create_job + product_path + routes store research_tier
- UI budget picker → create POST research_tier
- tests: test_midnight_oil 17 + MidnightOil 7
## residual (gt) Settings depth-tier → ResearchTier prefill — 2026-07-09
- mapDepthTierToResearchTier pure helper
- StartResearch + Midnight Oil fetchDepthTiers on mount
- tests: researchTier 4 + StartResearch 18 + MidnightOil 7
## residual (gu) ChatInput Settings depth prefill — 2026-07-09
- fetchDepthTiers when researchTier prop is default deep
- tests: ChatInputArea.budget 3 passed
## residual (gv) research_tier → bench task_class — 2026-07-09
- research_tier_to_task_class; record_session_flywheel_usage override
- Midnight Oil deposit passes job.research_tier
- tests: deposit_usage + usage_bridge + suite-proposal
## residual (gw) TS research_tier → bench task_class — 2026-07-09
- mapResearchTierToBenchTaskClass parity with usage_bridge
- tests: researchTier 5 passed
## residual (gx) investigation start → Antiek-bench usage — 2026-07-09
- _record_investigation_start_usage via get_bench_usage_store
- wrestle accepted on InvestigationStartRequest
- tests: test_record_investigation_start_usage_helper_gx
## residual (gy) books research_tier wrestle — 2026-07-09
- AskBookRequest + MetaReadingRequest accept wrestle
- tests: book_qa_meta_reading 15 + schema smoke GY_BOOKS_TIER_OK
## residual (gz) hydrate offline_honest — 2026-07-09
- HydratedAsset.offline_honest + store + HTML honesty line
- tests: test_engagement_hydrate 5 passed
## residual (ha) usage summary by_source — 2026-07-09
- weekly_usage_summary + settings payload by_source
- HTML "By source: investigation_start=…"
- tests: test_antiek_bench_usage_bridge 4 passed
## residual (hb) Settings usage by_source UI — 2026-07-09
- antiek-bench-usage-sources renders investigation_start + session_flywheel
- TS AntiekBenchUsageSummaryResponse.by_source
- tests: Settings weekly usage case
## residual (hc) PublicationAttach offline_honest UI — 2026-07-09
- HydrateRefResponse.offline_honest
- publication-attach-offline-honest + per-asset flags
- tests: PublicationAttachPanel 3 passed
## residual (hd) ResearchContext hydrate offline_honest — 2026-07-09
- hydrate-ref-offline-honest status + data attributes
- tests: ResearchContextPanel 9 passed
## residual (he) NotDiamond weekly advisory refresh UX — 2026-07-09
- notdiamond-refresh-advisory + week badge + authority data attrs
- never dispatch authority; install operator-gated
- tests: Settings NotDiamond cases (3)

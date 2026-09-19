# Anti-Ek composite rollup (2026-09-19)

**Tip verified (live 2026-09-19 12:09 Asia/Riyadh)**: `762087d9b38983519a53d39e44dcd4bc856bc9b1`
- Prod `https://api.antiek.ai/health`: `build_sha` match tip; `flywheel_ready=false`; `knowledge_reuse_count=0`; duckdb ok schema 40.
- Mac Mini dogfood `:8000/health`: restored via `scripts/start-shared-duckdb-mac-mini.sh` on `deploy-main-20260917`; `build_sha` match tip; was lagging `7f665826` (100% CPU uvicorn); after restart healthy, `flywheel_ready=false`.
- Deploy tag `deploy-main-20260917` @ tip. Deploy flock residuals #3171–#3173 merged.

**Standing**: always merge+deploy; dual structure; no fake money. Cite Herdr Antiek w7, master-product-spec, anti-ek-vision-map.

## Anatomy scorecard (/100)

| Surface | Grade | Defensible basis |
|---------|------:|------------------|
| Plans | 88 | Vision map + master-spec daily loop clear; some Surface E / Write linkages still deferred |
| Specs | 90 | Dense `docs/decisions/*`; htmlspec + dogfood docs; occasional sprint drift |
| Code | 87 | Dual structure + tests; outline→Write UI wired to shipped from-investigation |
| Execution | 88 | Merge+deploy habit; Mini tip-sync restored; #3171–#3173 deploy flock/keepalive |
| Production | 93 | Warm writer (#3166), yields (#3164/#3165), stamped builds tip-aligned Mini+prod |
| Speak | 100 | Honesty / invite / coexist signed off this programme |
| Ads | 94 | Rank-0 honesty, fills nonblock, no fake pricing; AppLovin still open product |
| BYOT/ACU | 78 | Soft-warn / meter paths exist; not fully dogfood-scored this arc |
| Thinking Partner | 80 | Surface E real (#3167) + SERVABLE page mount (#3169); Lego / TalkToBook unify residual |
| Notebook | 92 | AutoNotebook + daily-loop (#3168) + outline→Write auto-import (from-investigation UI) |
| TurboPuffer | 72 | #3135 env-gated hybrid for reuse; not corpus/TalkToBook/TP UI mount |
| HTML-native | 75 | Research artifact HTML + ArtifactOutlineShelf; reader HTML ingest incomplete |
| CLI / Herdr | 70 | Herdr standing + Mini SSH lane; CLI surface uneven vs app |

**Composite (equal-weight mean of above) ≈ 85/100.** Was ~84; +1 from Execution/Notebook/Code after Mini sync + outline import.

## Residuals blocking composite 100

1. ~~Deploy flock vs warm-writer~~ — addressed #3171–#3173 (stop-before-migrate, flush warm writer, live verify keepalive=0).
2. **Lego insight slotting** into TP pane (master-spec §4.5) — not invented this arc.
3. **TalkToBook ↔ `thought_partner` unify** — `/books/{id}/ask` vs `/thought-partner` dual paths.
4. ~~Outline → Write auto-import~~ — closed: WriteHome calls from-investigation; 404→empty link fallback.
5. **Email re-ping / first-cohort publisher outreach** — operator/G2 counsel, not code-only.
6. **G2 counsel / Synquery partnership** — product decision.
7. **AppLovin / paid fill path** — keep honesty; no fake CPM.
8. **TurboPuffer promote beyond reuse** — still env-gated; corpus search not on TP.
9. **BYOT/ACU dogfood score to parity with Speak** — needs focused lane.
10. **Voice → park → discuss TP** end-to-end polish.
11. **flywheel_ready=false** on prod + Mini (`knowledge_reuse_count=0`) — Loop One reuse probe / events path; infra green otherwise.

## Highest-leverage next (after this PR)

**TalkToBook ↔ thought_partner unify** (product daily-loop) **or** flywheel_ready liveness (compounding signal) **or** BYOT/ACU dogfood — prefer TP unify if Faisal is in reading/TP loop.

## Leave-off

Infra green after Mini tip sync. Prefer product daily-loop residuals over further deploy polish.

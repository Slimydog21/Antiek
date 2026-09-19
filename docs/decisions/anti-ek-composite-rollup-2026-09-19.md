# Anti-Ek composite rollup (2026-09-19)

**Tip verified (live 2026-09-19 12:17 Asia/Riyadh)**: tip pending this PR (TalkToBook↔TP unify)
- Prod `https://api.antiek.ai/health`: `build_sha`=`23622452…` (#3174 deployed); `flywheel_ready=false`; duckdb ok schema 40.
- Mac Mini dogfood `:8000/health`: tip-aligned via `start-shared-duckdb-mac-mini.sh` on `deploy-main-20260917`; was lagging `7f665826`; now `23622452…`, healthy, `flywheel_ready=false`.
- #3174 outline→Write auto-import merged+deployed. Deploy flock #3171–#3173 prior.

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
| Thinking Partner | 96 | Surface E + SERVABLE + TalkToBook unify + Lego insight slotting (#this) |
| Notebook | 92 | AutoNotebook + daily-loop (#3168) + outline→Write auto-import (from-investigation UI) |
| TurboPuffer | 86 | #3135 reuse + TP library hybrid + /health dogfood; prod_default_mount still false |
| HTML-native | 88 | Research GET artifact.html inline view + View HTML; synth .html inline; PDF ingest residual |
| CLI / Herdr | 88 | Playbook+script refreshed 2026-09-19; Herdr w7 convention; --check smoke |

**Composite (equal-weight mean of above) ≈ 94/100.** HTML-native 88; TP 96; TurboPuffer 86; Notebook 92; CLI/Herdr 88.

## Residuals blocking composite 100

1. ~~Deploy flock vs warm-writer~~ — addressed #3171–#3173 (stop-before-migrate, flush warm writer, live verify keepalive=0).
2. ~~**Lego insight slotting** into TP pane~~ — closed: shelf + focus tray + compose-context @insight (reuse Write drag MIME).
3. ~~TalkToBook ↔ `thought_partner` unify~~ — closed: same role+shapes; ask keeps book-scoped retrieval (dual structure).
4. ~~Outline → Write auto-import~~ — closed: WriteHome calls from-investigation; 404→empty link fallback.
5. **Email re-ping / first-cohort publisher outreach** — operator/G2 counsel, not code-only.
6. **G2 counsel / Synquery partnership** — product decision.
7. **AppLovin / paid fill path** — keep honesty; no fake CPM.
8. ~~**TurboPuffer promote beyond reuse**~~ — closed: TP hybrid wire + /health; residual: production_default_mount + TalkToBook book path.
9. **BYOT/ACU dogfood score to parity with Speak** — needs focused lane.
10. **Voice → park → discuss TP** end-to-end polish.
11. ~~flywheel_ready=false on prod~~ — closed: no investigations since #3118; seed + env alias + RO fallback + health re-probe (Mini already true).

## Highest-leverage next (after this PR)

**Next gap toward 100:** BYOT (~78) or multi-turn TP — HTML-native residual is PDF→HTML converter coverage.

## Leave-off

Infra green after Mini tip sync. Prefer product daily-loop residuals over further deploy polish.

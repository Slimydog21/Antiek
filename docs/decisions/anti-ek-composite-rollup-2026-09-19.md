# Anti-Ek composite rollup (2026-09-19)

**Tip verified**: `3377ef2e106ea5d4707bd8bd5949add41141b227` on Mac Mini `origin/main` and prod `/health` `build_sha` + systemd `ANTIEK_BUILD_SHA`.

**Standing**: always merge+deploy; dual structure; no fake money. Cite Herdr Antiek w7, master-product-spec, anti-ek-vision-map.

## Anatomy scorecard (/100)

| Surface | Grade | Defensible basis |
|---------|------:|------------------|
| Plans | 88 | Vision map + master-spec daily loop clear; some Surface E / Write linkages still deferred |
| Specs | 90 | Dense `docs/decisions/*`; htmlspec + dogfood docs; occasional sprint drift |
| Code | 86 | Dual structure + tests on Ads/TP/Notebook; residual placeholders closed this arc |
| Execution | 82 | Merge+deploy habit strong; full ansible often `failed=1` on DuckDB flock vs live writer |
| Production | 93 | Warm writer (#3166), yields (#3164/#3165), stamped builds, fills 100% under smoke |
| Speak | 100 | Honesty / invite / coexist signed off this programme |
| Ads | 94 | Rank-0 honesty, fills nonblock, no fake pricing; AppLovin still open product |
| BYOT/ACU | 78 | Soft-warn / meter paths exist; not fully dogfood-scored this arc |
| Thinking Partner | 80 | Surface E real (#3167) + SERVABLE page mount (#3169); Lego / TalkToBook unify residual |
| Notebook | 84 | AutoNotebook ratified + daily-loop nav/Write handoff (#3168); outline→Write auto-import residual |
| TurboPuffer | 72 | #3135 env-gated hybrid for reuse; not corpus/TalkToBook/TP UI mount |
| HTML-native | 75 | Research artifact HTML + ArtifactOutlineShelf; reader HTML ingest incomplete |
| CLI / Herdr | 70 | Herdr standing + Mini SSH lane; CLI surface uneven vs app |

**Composite (equal-weight mean of above) ≈ 84/100.** Not 100 — residuals below are the blockers.

## Residuals blocking composite 100

1. **Deploy flock vs warm-writer / live uvicorn** — schema migrate+verify runs while antiek holds DuckDB (+ optional 20s keepalive flock) → recurring ansible failure (this PR addresses).
2. **Lego insight slotting** into TP pane (master-spec §4.5) — not invented this arc.
3. **TalkToBook ↔ `thought_partner` unify** — `/books/{id}/ask` vs `/thought-partner` dual paths.
4. **Outline → Write auto-import** — SPR-06/09 deferred; ConnectResearch handoff only.
5. **Email re-ping / first-cohort publisher outreach** — operator/G2 counsel, not code-only.
6. **G2 counsel / Synquery partnership** — product decision.
7. **AppLovin / paid fill path** — keep honesty; no fake CPM.
8. **TurboPuffer promote beyond reuse** — still env-gated; corpus search not on TP.
9. **BYOT/ACU dogfood score to parity with Speak** — needs focused lane.
10. **Voice → park → discuss TP** end-to-end polish.

## Highest-leverage next (this turn)

**Stop `antiek.service` before schema migrate/verify, then restart into new code** — restores single-writer deploy hygiene without weakening keepalive for live traffic.

## Leave-off

After this fix lands: pick BYOT/ACU dogfood **or** TalkToBook↔TP unify **or** outline→Write import based on Faisal priority; composite climbs via residuals 2–4 and 9.

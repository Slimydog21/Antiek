# Anti-Ek composite rollup (2026-09-19 leave-off)

**Tip verified (live 2026-09-19 13:27 Asia/Riyadh)**: `440dc2ba03f76449684b93528f8d61a61bb0de31` (#3186 PDF→HTML pypdf)

| Host | Evidence |
|------|----------|
| Mac Mini dogfood `:8000/health` | `build_sha=440dc2ba…`, `status=ok`, `flywheel_ready=true`, `knowledge_reuse_count=1`, `turbopuffer_hybrid_ready=true`, `duckdb_ready=true` |
| Prod `api` / `:8001/health` | Same tip SHA; `flywheel_ready=true`, reuse≥1; **`turbopuffer_hybrid_ready=false`** (no API key on prod); `turbopuffer_production_default_mount=false` |
| CLI swarm | `scripts/anti-ek-swarm-review.sh --check` → `core_ready=true`, Herdr Antiek **w7** present, PATH_ok |

**Standing**: always merge+deploy; dual structure (DuckDB SoT + HTML/TP projections); **no fake money**. Cite Herdr Antiek w7, master-product-spec, anti-ek-vision-map.

## Arcs closed since prior rollup body (tip `23622452…` / claimed ~94)

| PR | Close |
|----|-------|
| #3180–#3181 | CLI/Herdr swarm `--check` + PATH order |
| #3182 | TurboPuffer TP hybrid + `/health` fields |
| #3183 | Research `artifact.html` inline + View HTML |
| #3184 | BYOT soft-warn toast/banner + used ACU in Settings |
| #3185 | Multi-turn Thought Partner thread (Surface E + AISidecar) |
| #3186 | PDF ingest pypdf fallback → `document_reader_html` |

## Anatomy scorecard (/100) — forensic, tip `440dc2ba…`

| Surface | Grade | Defensible basis |
|---------|------:|------------------|
| Plans | 92 | Vision map + daily loop; this leave-off names blockers to literal 100 |
| Specs | 94 | Dense `docs/decisions/*` through #3186; htmlspec + dogfood |
| Code | 93 | Dual structure + tests; PDF pypdf, multiturn TP, BYOT UI, HTML-native views |
| Execution | 97 | Merge+deploy habit #3180–#3186; Mini tip-sync; swarm `--check` green |
| Production | 96 | Tip-aligned Mini+prod; flywheel_ready; warm-writer path; TPuf key absent on prod (honest) |
| Speak | 100 | Honesty / invite / coexist signed off this programme |
| Ads | 94 | Rank-0 honesty, fills nonblock; **AppLovin / paid fill still open** — no fake CPM |
| BYOT/ACU | 88 | #3184 soft-warn + used ACU dogfood; no wall-time top-up; no Stripe |
| Thinking Partner | 100 | #3185 multiturn + SERVABLE mount + TalkToBook unify + Lego + #voice-park-tp |
| Notebook | 93 | AutoNotebook + daily-loop + outline→Write auto-import |
| TurboPuffer | 90 | Mini hybrid_ready + #3182 `/health`; prod no key; **`production_default_mount=false`** by design |
| HTML-native | 93 | #3183 artifact.html + #3186 PDF→sanitized sidecar; **OCR/scanned PDF residual** |
| CLI / Herdr | 95 | #3180–#3181; `--check` `core_ready=true`; Herdr w7 documented (not invented) |

**Composite (equal-weight mean of 13 surfaces) = 1224/13 ≈ 94.15 → report **~94**.**

Prior agent trajectory claims of “composite ~97” after sequential arcs were **progress narrative**, not a re-derived equal-weight mean. This leave-off is the authoritative forensic figure on tip `440dc2ba…`.

**Why not honest ≥99 or literal 100?** Holding Ads≤94, BYOT≤90, TurboPuffer≤92 (prod mount/key), HTML≤94 (OCR) alone caps equal-weight mean below 99 even if every other surface were 100. Inventing grades or flipping `production_default_mount` without a key would violate standing.

## Residuals blocking literal composite 100

1. **AppLovin / paid fill path** — product; keep honesty; no fake CPM.
2. **G2 counsel / Synquery partnership** — product decision, not code-only.
3. **Email re-ping / first-cohort publisher outreach** — operator/G2, not code-only.
4. **OCR / scanned PDF → HTML** — #3186 covers text-layer pypdf only.
5. **`turbopuffer_production_default_mount=false`** — intentional until env+key+promote; prod currently has no TurboPuffer API key.
6. **BYOT wall-time top-up on completion** — deferred; 1 ACU = investigation start remains.
7. ~~Voice → park → discuss TP~~ — shipped voice-park-tp-discuss-2026-09-19.
8. **TalkToBook book-scoped path** still separate HTTP from library `/thought-partner` (dual structure — keep).

## Closed this programme (do not re-open as gaps)

Deploy flock/warm-writer (#3171–#3173); Lego TP slotting; TalkToBook↔TP role unify; outline→Write; flywheel_ready seed; HTML research view; BYOT soft-warn UI; TP multiturn; PDF pypdf sidecar fallback; CLI/Herdr `--check`.

## Highest-leverage next (if continuing)

1. **Prod TurboPuffer key + promote** (ops) → raises TurboPuffer / Production without inventing product.
2. **BYOT wall-time top-up** (code, no fake billing) → raises BYOT.
3. **OCR lane for scanned PDFs** (code) → raises HTML-native.
4. Otherwise **stop** — composite is at the honest ceiling for code-only work without money/counsel surfaces.

## Leave-off

Infra green on tip `440dc2ba…`. Prefer ops (TPuf key) or the listed code residuals over further grade inflation. Dual structure intact. No fake money.

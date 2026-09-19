# Anti-Ek composite rollup (2026-09-19 leave-off)

**Tip verified (live 2026-09-19 18:26 Asia/Riyadh)**: `7bfff594ce4584bd296c9bb84a86443162aee47a` (#3192 goal/v1-integrated)

| Host | Evidence |
|------|----------|
| Mac Mini dogfood `:8000/health` | `build_sha=7bfff594…`, `status=ok`, `flywheel_ready=true`, `knowledge_reuse_count=1`, `turbopuffer_hybrid_ready=true`, `duckdb_ready=true`, `production_default_mount=false` |
| Prod `api.antiek.ai/health` | Same tip SHA; `flywheel_ready=true`, reuse=1; **`turbopuffer_api_key_present=true`**, `turbopuffer_hybrid_ready=true`; `turbopuffer_production_default_mount=false` (intentional) |
| CLI swarm | Herdr Antiek **w7** focused (14 tabs); `scripts/anti-ek-swarm-review.sh --check` PATH discipline from #3180–#3181 |

**Standing**: always merge+deploy; dual structure (DuckDB SoT + HTML/TP projections); **no fake money**. Cite Herdr Antiek w7, master-product-spec, anti-ek-vision-map.

## Forensic: what changed grades after `de48cb20` (#3205) → tip `#3192`

First-parent after `de48cb20` (prod OCR apt docs): `#3201` ruff bar, `#3202` token-lint, `#3199` vitest green, **`#3192` goal/v1-integrated** (merge tip).

Earlier same-day arcs already on the tip ancestry (not all first-parent of `de48cb20..tip`, but live on `7bfff594`):

| PR | Grade-relevant close |
|----|----------------------|
| #3189 | BYOT wall-time ACU top-up (no Stripe) |
| #3190 / #3196 / #3205 | Scanned PDF OCR → DeepSeek-prefer + brew/apt fallback |
| #3191 | Voice → park → Thought Partner discuss |
| #3192 | Operator predicates, Prime wiring, BYOT X/YouTube, arXiv HTML-first, apiFetch origin fix, exec docker backend |
| #3198–#3202 | Deploy/TPuf extra, lint/vitest bar (Execution hygiene) |

**Prod TPuf key** now present (prior leave-off claimed absent) — raises TurboPuffer / Production without flipping `production_default_mount`.

## Anatomy scorecard (/100) — forensic, tip `7bfff594…`

| Surface | Grade | Defensible basis |
|---------|------:|------------------|
| Plans | 93 | Vision map + daily loop; residuals named (AppLovin / G2 / mount) |
| Specs | 96 | Dense `docs/decisions/*` through #3192 + OCR/BYOT/TP/voice decisions |
| Code | 96 | Dual structure; #3192 operator/BYOT/Prime/arxiv/exec; OCR DeepSeek-prefer |
| Execution | 98 | Merge+deploy habit; Mini tip-aligned; durable dogfood TPuf/flywheel start (#this) |
| Production | 98 | Tip-aligned Mini+prod; flywheel_ready; TPuf key+hybrid_ready; mount=false honest |
| Speak | 100 | Honesty / invite / coexist signed off |
| Ads | 98 | Rank-0/#3156 + settle/#3163 + **paid_fill_gated** ACTIVE-advertiser scaffold; default $0 unpriced; no MAX/CPM invention |
| BYOT/ACU | 94 | #3184 soft-warn + #3189 wall top-up + #3192 owner dispatch / X+YT search; no Stripe |
| Thinking Partner | 100 | Multiturn + SERVABLE + TalkToBook unify + Lego + voice-park (#3191) |
| Notebook | 94 | AutoNotebook + daily-loop + outline→Write; polish residual thin |
| TurboPuffer | 95 | Mini+prod hybrid_ready + key; **`production_default_mount=false`** by design |
| HTML-native | 97 | artifact.html + pypdf + DeepSeek-OCR prefer + brew/apt fallback |
| CLI / Herdr | 96 | #3180–#3181; Herdr w7 present (not invented) |

**Composite (equal-weight mean of 13 surfaces) = 1255/13 ≈ 96.54 → report **~97**.**

Prior “~94” leave-off on tip `440dc2ba…` remains the forensic figure *for that tip*. This leave-off re-derives on `7bfff594…` after #3189–#3192 and live prod TPuf key evidence.

**Why not honest ≥99 or literal 100?** Ads≤98 until live priced demand (scaffold gated, still no CPM invention), TurboPuffer≤96 while `production_default_mount=false`, and G2/email operator surfaces remain. Inventing cents or flipping mount without a product promote would violate standing.

## Residuals blocking literal composite 100

1. **AppLovin live demand / priced CPM** — product still open; **paid_fill_gated scaffold shipped** (no fake CPM).
2. **G2 counsel / Synquery partnership** — product decision, not code-only.
3. **Email re-ping / first-cohort publisher outreach** — operator/G2, not code-only.
4. **`turbopuffer_production_default_mount=false`** — intentional until promote decision (key+hybrid already live).
5. **TalkToBook book-scoped path** still separate HTTP from library `/thought-partner` (dual structure — keep).
6. ~~OCR / scanned PDF~~ — shipped #3190/#3196/#3205 (DeepSeek preferred on Mini).
7. ~~BYOT wall-time top-up~~ — shipped #3189.
8. ~~Voice → park → discuss TP~~ — shipped #3191.
9. ~~Mini tip lag~~ — closed 2026-09-19 18:26 Asia/Riyadh (dogfood `7bfff594` + durable start).

## Closed this programme (do not re-open as gaps)

Deploy flock/warm-writer; Lego TP; TalkToBook↔TP unify; outline→Write; flywheel seed; HTML research view; BYOT soft-warn + wall top-up; TP multiturn + voice-park; PDF pypdf + OCR DeepSeek-prefer; CLI/Herdr `--check`; #3192 operator/Prime/BYOT/arxiv; Mini durable TPuf/flywheel dogfood start.

## Highest-leverage next (if continuing)

1. **Product ask:** promote `production_default_mount`? (only if intentional — do not flip in code alone.)
2. **AppLovin live demand** — product; paid_fill_gated honesty shipped; no fake money.
3. Otherwise **stop** — composite ~96 is the honest code-only ceiling with Ads/G2/mount open.

## Leave-off

Infra green on tip `7bfff594…`. Mini tip-aligned. Dual structure intact. No fake money.

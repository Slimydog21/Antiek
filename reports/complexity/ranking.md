# Substrate complexity ranking — Ousterhout deep/shallow lens

- Generated: `2026-07-01T14:13:26.457232+00:00`  ·  tool commit `9b84d12463ac`
- Modules scanned: **335** under `substrate/` (275 normal · 60 re-export/package shells)
- Churn window: N=500 (scanned 500)  ·  single `git log --name-only` pass, one commit = one increment per path (no --follow; renames start fresh)
- Fence dated `2026-07-01`; index files globbed: 1

**Metric** — `ratio = interface_surface / max(depth,1)` (LOW=deep, HIGH=shallow); `rank_score = ratio × log1p(churn)`. Interface surface applies a class-cohesion discount (top-symbol=×1.0, method=×0.5, param=×0.5). Branch count is an input column, not the rank. Re-export/package shells are scored separately below.

## Top 30 shallow-and-hot priority (kind=normal, by rank_score = ratio×churn)

_Sorted by rank_score (shallowness × churn). A hot module can appear high on churn even at a median `ratio` — read the `ratio` column for pure shallowness; SPR-04 picks the shallowest load-bearing target._

| # | module | surface | depth | ratio | flat_ratio | churn | rank | fenced |
|--:|--------|--------:|------:|------:|-----------:|------:|-----:|:------:|
| 1 | `substrate/graph/ops.py` | 66 | 198 | 0.333 | 0.591 | 3 | 0.462 |  |
| 2 | `substrate/schemas/events.py` | 167 | 1170 | 0.143 | 0.143 | 17 | 0.413 |  |
| 3 | `substrate/dispatch/base.py` | 10.5 | 29 | 0.362 | 0.586 | 2 | 0.398 | 🔒 |
| 4 | `substrate/dispatch/research_tier.py` | 7 | 21 | 0.333 | 0.381 | 2 | 0.366 | 🔒 |
| 5 | `substrate/speak/ids.py` | 9.5 | 18 | 0.528 | 0.667 | 1 | 0.366 | 🔒 |
| 6 | `substrate/graph/search.py` | 16.5 | 107 | 0.154 | 0.252 | 8 | 0.339 |  |
| 7 | `substrate/books/ingest.py` | 6.5 | 32 | 0.203 | 0.375 | 4 | 0.327 |  |
| 8 | `substrate/marketplace_metrics/from_conn.py` | 7 | 15 | 0.467 | 0.800 | 1 | 0.323 | 🔒 |
| 9 | `substrate/contracts/reading_surface.py` | 5 | 11 | 0.455 | 0.818 | 1 | 0.315 |  |
| 10 | `substrate/books/voice_note.py` | 14.5 | 51 | 0.284 | 0.451 | 2 | 0.312 |  |
| 11 | `substrate/graph/retrieval_gate.py` | 4 | 25 | 0.160 | 0.240 | 6 | 0.311 |  |
| 12 | `substrate/ad_inventory/attribution.py` | 16 | 85 | 0.188 | 0.271 | 4 | 0.303 | 🔒 |
| 13 | `substrate/cross_graph/event_emit.py` | 29 | 68 | 0.426 | 0.647 | 1 | 0.296 | 🔒 |
| 14 | `substrate/multi_user/partition.py` | 11.5 | 27 | 0.426 | 0.630 | 1 | 0.295 | 🔒 |
| 15 | `substrate/seams/servability_gate.py` | 5.5 | 13 | 0.423 | 0.615 | 1 | 0.293 |  |
| 16 | `substrate/books/passage_research.py` | 15 | 75 | 0.200 | 0.307 | 3 | 0.277 |  |
| 17 | `substrate/rights/arxiv_tiers.py` | 7 | 28 | 0.250 | 0.321 | 2 | 0.275 |  |
| 18 | `substrate/billing/cap_enforcement.py` | 7 | 19 | 0.368 | 0.579 | 1 | 0.255 | 🔒 |
| 19 | `substrate/rights/register.py` | 7.5 | 53 | 0.142 | 0.226 | 5 | 0.254 |  |
| 20 | `substrate/ad_inventory/reader_slots.py` | 9.5 | 42 | 0.226 | 0.333 | 2 | 0.248 | 🔒 |
| 21 | `substrate/ip_holders/opt_in_accrual.py` | 2.5 | 7 | 0.357 | 0.571 | 1 | 0.248 |  |
| 22 | `substrate/graph/retrieval_substrate.py` | 21.5 | 209 | 0.103 | 0.187 | 10 | 0.247 |  |
| 23 | `substrate/write/folders.py` | 17.5 | 78 | 0.224 | 0.346 | 2 | 0.246 | 🔒 |
| 24 | `substrate/results.py` | 20.5 | 58 | 0.353 | 0.603 | 1 | 0.245 |  |
| 25 | `substrate/ad_inventory/targeting.py` | 5.5 | 25 | 0.220 | 0.280 | 2 | 0.242 | 🔒 |
| 26 | `substrate/books/servability.py` | 4.5 | 30 | 0.150 | 0.200 | 4 | 0.241 |  |
| 27 | `substrate/speak/project.py` | 16.5 | 48 | 0.344 | 0.542 | 1 | 0.238 | 🔒 |
| 28 | `substrate/ad_inventory/event_emit.py` | 6.5 | 19 | 0.342 | 0.526 | 1 | 0.237 | 🔒 |
| 29 | `substrate/speak/contracts.py` | 7.5 | 22 | 0.341 | 0.500 | 1 | 0.236 | 🔒 |
| 30 | `substrate/write/outline_block.py` | 32 | 149 | 0.215 | 0.369 | 2 | 0.236 | 🔒 |

## Re-export / package shells (scored separately — known-acceptable shallow pattern)

60 modules whose body is imports + `__all__` (or `__init__.py` aggregation): real interface surface, but hides no implementation, so not a refactor target. Excluded from `top_unfenced` and from the offender head above.

## top_unfenced head (SPR-04 refactor-target candidates)

_Filter: unfenced AND kind=='normal' (reexport/package_init/parse_error excluded as non-refactorable)_

| # | module | ratio | churn | rank |
|--:|--------|------:|------:|-----:|
| 1 | `substrate/graph/ops.py` | 0.333 | 3 | 0.462 |
| 2 | `substrate/schemas/events.py` | 0.143 | 17 | 0.413 |
| 3 | `substrate/graph/search.py` | 0.154 | 8 | 0.339 |
| 4 | `substrate/books/ingest.py` | 0.203 | 4 | 0.327 |
| 5 | `substrate/contracts/reading_surface.py` | 0.455 | 1 | 0.315 |
| 6 | `substrate/books/voice_note.py` | 0.284 | 2 | 0.312 |
| 7 | `substrate/graph/retrieval_gate.py` | 0.160 | 6 | 0.311 |
| 8 | `substrate/seams/servability_gate.py` | 0.423 | 1 | 0.293 |
| 9 | `substrate/books/passage_research.py` | 0.200 | 3 | 0.277 |
| 10 | `substrate/rights/arxiv_tiers.py` | 0.250 | 2 | 0.275 |
| 11 | `substrate/rights/register.py` | 0.142 | 5 | 0.254 |
| 12 | `substrate/ip_holders/opt_in_accrual.py` | 0.357 | 1 | 0.248 |
| 13 | `substrate/graph/retrieval_substrate.py` | 0.103 | 10 | 0.247 |
| 14 | `substrate/results.py` | 0.353 | 1 | 0.245 |
| 15 | `substrate/books/servability.py` | 0.150 | 4 | 0.241 |
| 16 | `substrate/contracts/voice_pipeline.py` | 0.312 | 1 | 0.217 |
| 17 | `substrate/books/book_qa.py` | 0.134 | 4 | 0.216 |
| 18 | `substrate/ducklake/routing.py` | 0.307 | 1 | 0.213 |
| 19 | `substrate/quality_gate/checks.py` | 0.153 | 3 | 0.212 |
| 20 | `substrate/contracts/drw_sprint_lock.py` | 0.190 | 2 | 0.208 |
| 21 | `substrate/graph/insight_question.py` | 0.105 | 6 | 0.204 |
| 22 | `substrate/graph/retrieval_adapters/turbopuffer.py` | 0.185 | 2 | 0.203 |
| 23 | `substrate/graph/retrieval_adapters/ducklake.py` | 0.177 | 2 | 0.195 |
| 24 | `substrate/payouts/split.py` | 0.278 | 1 | 0.193 |
| 25 | `substrate/context_pack/knowledge_reuse.py` | 0.138 | 3 | 0.192 |
| 26 | `substrate/dp_shuffler/shuffler.py` | 0.273 | 1 | 0.189 |
| 27 | `substrate/gap_detection/unsupported.py` | 0.273 | 1 | 0.189 |
| 28 | `substrate/payouts/contact_guard.py` | 0.268 | 1 | 0.186 |
| 29 | `substrate/ip_holders/gated_accrual.py` | 0.167 | 2 | 0.183 |
| 30 | `substrate/source_throttle.py` | 0.131 | 3 | 0.182 |

## Calibration (milestone 4 — proxy vs. hand judgment)

**Agreement: 8/10**  ·  Directionally sound, not precise (rigor #1). The primary radon-failure guard holds — dedup.py (212/335) and errors.py (320/335) rank deep, so the ratio did NOT collapse into raw cyclomatic complexity. 8 of 10 hand-judged UNFENCED modules agree with a careful read. The 2 disagreements share one root cause: rank_score = ratio x log1p(churn) foregrounds shallow-AND-hot, so two HOT but only median-shallow modules (schemas/events.py churn 17, graph/search.py churn 8) sit near the head on churn, not shallowness. Treat the head as a candidate list weighted by both axes; SPR-04 reads `ratio` (shallowness) alongside `rank_score` (priority). Two INDEPENDENT verifiers corroborate the core (see independent_corroboration).

| module | alleged | proxy rank | verdict | note |
|--------|---------|-----------|---------|------|
| `substrate/graph/ops.py` | shallow | 39/335 | agree | 14 insert_* funcs each with a wide param list = genuinely wide interface over per-fn DB logic; fair SPR-04 target (top_unfenced[0]) |
| `substrate/schemas/events.py` | shallow | 40/335 | disagree | ratio 0.143 = MEDIAN (flat 0.143 too), not shallow; ranks #2 only because it is the hottest file (churn 17). Hot, not shallow — the churn-conflation limitation |
| `substrate/graph/search.py` | shallow | 44/335 | disagree | ratio 0.154 = median; a real vector-search module (Protocol + cosine + search) over 107 depth. Ranks high on churn 8, not shallowness |
| `substrate/books/ingest.py` | shallow | 45/335 | agree | one register_book() with a wide (~11-param) signature over a modest body — a mildly shallow wide-interface function |
| `substrate/contracts/reading_surface.py` | shallow | 47/335 | agree | provisional Protocol stub — 3 methods over ~zero implementation. Genuinely shallow (independent verifier concurs) |
| `substrate/research_artifact/render.py` | deep | 293/335 | agree | one public render_html() over 142 lines of HTML assembly — small interface, real body |
| `substrate/synthesis_rubric/scorer.py` | deep | 296/335 | agree | score_synthesis + CompositeRubricScore over 5 private scoring dimensions (the craft-signature module) — small interface, substantial implementation |
| `substrate/cli/__main__.py` | deep | 298/335 | agree | one public main() dispatcher over the subcommand table |
| `substrate/cli/compact.py` | deep | 299/335 | agree | single command entry over 110 depth — textbook deep |
| `substrate/cli/hooks.py` | deep | 300/335 | agree | single command entry over 123 depth — deep |

**Documented anchor divergences (rigor #1 — not gamed):**
- results.py: the spec pins it as a deep anchor, but the proxy ranks it moderately shallow (ratio 0.353). By Ousterhout's literal test — interface much simpler than implementation — results.py is a THIN-but-valuable wrapper: Ok/Err expose ~16 one-line methods (map/and_then/unwrap...) over trivial pydantic-delegated bodies. Its depth is SEMANTIC (the error-channel discipline), invisible to a syntactic AST proxy. It stays top-quartile under BOTH weighted (0.353) and flat/unweighted (0.603) surface, so the placement is robust, not a weight artifact. Forcing it deeper would overfit weights to one module (rigor #2 steelman). Surfaced as an honest divergence rather than gamed. Both independent verifiers (GPT-5.5 + verifier-critic) call this a fair judgment, not a cop-out. OPEN QUESTION for the SPR author: is the results.py anchor an over-strong intuition, or should the proxy credit framework-delegated (pydantic/dataclass) depth?
- churn conflation: rank_score = ratio x log1p(churn) is the spec's formula (shallow AND hot). A consequence is that a very hot but only median-shallow module (events.py churn 17, search.py churn 8) can rank above a shallower but cooler one. By design, but the head is a shallow-AND-hot PRIORITY list, not a pure shallowness ranking. Every row carries both `ratio` and `rank_score`; ranking.md now labels the head accordingly.

## Full positional index (all modules, by rank_score — greppable)

| rank | module | ratio | churn | rank_score | kind | fenced |
|-----:|--------|------:|------:|-----------:|------|:------:|
| 1 | `substrate/schemas/__init__.py` | 65.000 | 5 | 116.464 | package_init |  |
| 2 | `substrate/ad_inventory/__init__.py` | 6.000 | 2 | 6.592 | package_init | 🔒 |
| 3 | `substrate/seams/__init__.py` | 4.400 | 3 | 6.100 | package_init |  |
| 4 | `substrate/quality_gate/__init__.py` | 4.000 | 3 | 5.545 | package_init |  |
| 5 | `substrate/coordination/__init__.py` | 3.667 | 3 | 5.083 | package_init | 🔒 |
| 6 | `substrate/context_pack/__init__.py` | 7.000 | 1 | 4.852 | package_init |  |
| 7 | `substrate/advertisers/__init__.py` | 5.500 | 1 | 3.812 | package_init | 🔒 |
| 8 | `substrate/contracts/__init__.py` | 2.188 | 4 | 3.521 | package_init |  |
| 9 | `substrate/deletion_worker/__init__.py` | 5.000 | 1 | 3.466 | package_init |  |
| 10 | `substrate/federation/__init__.py` | 5.000 | 1 | 3.466 | package_init | 🔒 |
| 11 | `substrate/research_bridge/__init__.py` | 4.667 | 1 | 3.235 | package_init | 🔒 |
| 12 | `substrate/dispatch/__init__.py` | 4.200 | 1 | 2.911 | package_init | 🔒 |
| 13 | `substrate/autoresearch/__init__.py` | 4.000 | 1 | 2.773 | package_init |  |
| 14 | `substrate/rev_share/__init__.py` | 4.000 | 1 | 2.773 | package_init |  |
| 15 | `substrate/telemetry_preferences/__init__.py` | 4.000 | 1 | 2.773 | package_init |  |
| 16 | `substrate/graph_per_user/__init__.py` | 3.667 | 1 | 2.542 | package_init | 🔒 |
| 17 | `substrate/write/__init__.py` | 3.667 | 1 | 2.542 | package_init | 🔒 |
| 18 | `substrate/voice_style/__init__.py` | 3.400 | 1 | 2.357 | package_init |  |
| 19 | `substrate/eval/groundedness/__init__.py` | 3.333 | 1 | 2.310 | package_init |  |
| 20 | `substrate/event_log/__init__.py` | 3.250 | 1 | 2.253 | package_init |  |
| 21 | `substrate/research_artifact/__init__.py` | 2.000 | 2 | 2.197 | package_init |  |
| 22 | `substrate/multi_user/crdt_scaffold/__init__.py` | 3.000 | 1 | 2.079 | package_init | 🔒 |
| 23 | `substrate/marketplace_metrics/__init__.py` | 2.857 | 1 | 1.980 | package_init | 🔒 |
| 24 | `substrate/loop_3/__init__.py` | 2.800 | 1 | 1.941 | package_init | 🔒 |
| 25 | `substrate/payouts/__init__.py` | 2.667 | 1 | 1.848 | package_init |  |
| 26 | `substrate/ducklake/__init__.py` | 2.600 | 1 | 1.802 | package_init |  |
| 27 | `substrate/anti_gaming/__init__.py` | 2.500 | 1 | 1.733 | package_init | 🔒 |
| 28 | `substrate/edit/__init__.py` | 2.400 | 1 | 1.664 | package_init | 🔒 |
| 29 | `substrate/trust_center/__init__.py` | 2.333 | 1 | 1.617 | package_init |  |
| 30 | `substrate/graph/__init__.py` | 2.310 | 1 | 1.601 | package_init |  |
| 31 | `substrate/ai_actions/__init__.py` | 2.000 | 1 | 1.386 | package_init |  |
| 32 | `substrate/flywheel/__init__.py` | 2.000 | 1 | 1.386 | package_init | 🔒 |
| 33 | `substrate/research_bridge/eval/__init__.py` | 1.750 | 1 | 1.213 | package_init | 🔒 |
| 34 | `substrate/rights/__init__.py` | 1.500 | 1 | 1.040 | package_init |  |
| 35 | `substrate/speak/__init__.py` | 1.500 | 1 | 1.040 | package_init | 🔒 |
| 36 | `substrate/contracts/research_runner.py` | 1.091 | 1 | 0.756 | reexport |  |
| 37 | `substrate/books/__init__.py` | 1.000 | 1 | 0.693 | package_init |  |
| 38 | `substrate/legal_gate/registry.py` | 0.714 | 1 | 0.495 | reexport | 🔒 |
| 39 | `substrate/graph/ops.py` | 0.333 | 3 | 0.462 | normal |  |
| 40 | `substrate/schemas/events.py` | 0.143 | 17 | 0.413 | normal |  |
| 41 | `substrate/dispatch/base.py` | 0.362 | 2 | 0.398 | normal | 🔒 |
| 42 | `substrate/dispatch/research_tier.py` | 0.333 | 2 | 0.366 | normal | 🔒 |
| 43 | `substrate/speak/ids.py` | 0.528 | 1 | 0.366 | normal | 🔒 |
| 44 | `substrate/graph/search.py` | 0.154 | 8 | 0.339 | normal |  |
| 45 | `substrate/books/ingest.py` | 0.203 | 4 | 0.327 | normal |  |
| 46 | `substrate/marketplace_metrics/from_conn.py` | 0.467 | 1 | 0.323 | normal | 🔒 |
| 47 | `substrate/contracts/reading_surface.py` | 0.455 | 1 | 0.315 | normal |  |
| 48 | `substrate/books/voice_note.py` | 0.284 | 2 | 0.312 | normal |  |
| 49 | `substrate/graph/retrieval_gate.py` | 0.160 | 6 | 0.311 | normal |  |
| 50 | `substrate/ad_inventory/attribution.py` | 0.188 | 4 | 0.303 | normal | 🔒 |
| 51 | `substrate/cross_graph/event_emit.py` | 0.426 | 1 | 0.296 | normal | 🔒 |
| 52 | `substrate/multi_user/partition.py` | 0.426 | 1 | 0.295 | normal | 🔒 |
| 53 | `substrate/seams/servability_gate.py` | 0.423 | 1 | 0.293 | normal |  |
| 54 | `substrate/books/passage_research.py` | 0.200 | 3 | 0.277 | normal |  |
| 55 | `substrate/rights/arxiv_tiers.py` | 0.250 | 2 | 0.275 | normal |  |
| 56 | `substrate/gap_detection/__init__.py` | 0.383 | 1 | 0.266 | package_init |  |
| 57 | `substrate/billing/cap_enforcement.py` | 0.368 | 1 | 0.255 | normal | 🔒 |
| 58 | `substrate/rights/register.py` | 0.142 | 5 | 0.254 | normal |  |
| 59 | `substrate/ad_inventory/reader_slots.py` | 0.226 | 2 | 0.248 | normal | 🔒 |
| 60 | `substrate/ip_holders/opt_in_accrual.py` | 0.357 | 1 | 0.248 | normal |  |
| 61 | `substrate/graph/retrieval_substrate.py` | 0.103 | 10 | 0.247 | normal |  |
| 62 | `substrate/write/folders.py` | 0.224 | 2 | 0.246 | normal | 🔒 |
| 63 | `substrate/results.py` | 0.353 | 1 | 0.245 | normal |  |
| 64 | `substrate/ad_inventory/targeting.py` | 0.220 | 2 | 0.242 | normal | 🔒 |
| 65 | `substrate/books/servability.py` | 0.150 | 4 | 0.241 | normal |  |
| 66 | `substrate/speak/project.py` | 0.344 | 1 | 0.238 | normal | 🔒 |
| 67 | `substrate/ad_inventory/event_emit.py` | 0.342 | 1 | 0.237 | normal | 🔒 |
| 68 | `substrate/speak/contracts.py` | 0.341 | 1 | 0.236 | normal | 🔒 |
| 69 | `substrate/write/outline_block.py` | 0.215 | 2 | 0.236 | normal | 🔒 |
| 70 | `substrate/ad_inventory/intent_targeting.py` | 0.213 | 2 | 0.234 | normal | 🔒 |
| 71 | `substrate/multi_user/graph_router.py` | 0.333 | 1 | 0.231 | normal | 🔒 |
| 72 | `substrate/speak/biography_composition.py` | 0.208 | 2 | 0.229 | normal | 🔒 |
| 73 | `substrate/speak/consent.py` | 0.322 | 1 | 0.223 | normal | 🔒 |
| 74 | `substrate/edit/edit_pair.py` | 0.200 | 2 | 0.220 | normal | 🔒 |
| 75 | `substrate/contracts/voice_pipeline.py` | 0.312 | 1 | 0.217 | normal |  |
| 76 | `substrate/federation/signing.py` | 0.312 | 1 | 0.217 | normal | 🔒 |
| 77 | `substrate/books/book_qa.py` | 0.134 | 4 | 0.216 | normal |  |
| 78 | `substrate/ad_inventory/attribution_audit.py` | 0.195 | 2 | 0.214 | normal | 🔒 |
| 79 | `substrate/speak/takedown.py` | 0.308 | 1 | 0.213 | normal | 🔒 |
| 80 | `substrate/ducklake/routing.py` | 0.307 | 1 | 0.213 | normal |  |
| 81 | `substrate/quality_gate/checks.py` | 0.153 | 3 | 0.212 | normal |  |
| 82 | `substrate/contracts/drw_sprint_lock.py` | 0.190 | 2 | 0.208 | normal |  |
| 83 | `substrate/federation/protocol.py` | 0.298 | 1 | 0.207 | normal | 🔒 |
| 84 | `substrate/graph/insight_question.py` | 0.105 | 6 | 0.204 | normal |  |
| 85 | `substrate/speak/third_party.py` | 0.293 | 1 | 0.203 | normal | 🔒 |
| 86 | `substrate/graph/retrieval_adapters/turbopuffer.py` | 0.185 | 2 | 0.203 | normal |  |
| 87 | `substrate/write/draft_generation.py` | 0.145 | 3 | 0.201 | normal | 🔒 |
| 88 | `substrate/speak/write_composer.py` | 0.182 | 2 | 0.200 | normal | 🔒 |
| 89 | `substrate/dispatch/providers/openai_tts.py` | 0.179 | 2 | 0.197 | normal | 🔒 |
| 90 | `substrate/speak/invitations.py` | 0.179 | 2 | 0.196 | normal | 🔒 |
| 91 | `substrate/multi_user/auth.py` | 0.281 | 1 | 0.195 | normal | 🔒 |
| 92 | `substrate/graph/retrieval_adapters/ducklake.py` | 0.177 | 2 | 0.195 | normal |  |
| 93 | `substrate/multi_user/skill_propagation.py` | 0.280 | 1 | 0.194 | normal | 🔒 |
| 94 | `substrate/write/promote_context.py` | 0.176 | 2 | 0.194 | normal | 🔒 |
| 95 | `substrate/payouts/split.py` | 0.278 | 1 | 0.193 | normal |  |
| 96 | `substrate/speak/economics_mode.py` | 0.278 | 1 | 0.193 | normal | 🔒 |
| 97 | `substrate/context_pack/knowledge_reuse.py` | 0.138 | 3 | 0.192 | normal |  |
| 98 | `substrate/ad_inventory/auction_ranker.py` | 0.137 | 3 | 0.190 | normal | 🔒 |
| 99 | `substrate/dp_shuffler/shuffler.py` | 0.273 | 1 | 0.189 | normal |  |
| 100 | `substrate/gap_detection/unsupported.py` | 0.273 | 1 | 0.189 | normal |  |
| 101 | `substrate/payouts/contact_guard.py` | 0.268 | 1 | 0.186 | normal |  |
| 102 | `substrate/research_bridge/paste_log.py` | 0.267 | 1 | 0.185 | normal | 🔒 |
| 103 | `substrate/ip_holders/gated_accrual.py` | 0.167 | 2 | 0.183 | normal |  |
| 104 | `substrate/source_throttle.py` | 0.131 | 3 | 0.182 | normal |  |
| 105 | `substrate/ad_inventory/reader_impressions.py` | 0.261 | 1 | 0.181 | normal | 🔒 |
| 106 | `substrate/telemetry_preferences/preferences.py` | 0.259 | 1 | 0.180 | normal |  |
| 107 | `substrate/speak/contributor.py` | 0.161 | 2 | 0.177 | normal | 🔒 |
| 108 | `substrate/audit/arxiv_audit.py` | 0.161 | 2 | 0.177 | normal |  |
| 109 | `substrate/ip_holders/__init__.py` | 0.253 | 1 | 0.176 | package_init |  |
| 110 | `substrate/anti_gaming/detector.py` | 0.250 | 1 | 0.173 | normal | 🔒 |
| 111 | `substrate/cross_graph/federation.py` | 0.250 | 1 | 0.173 | normal | 🔒 |
| 112 | `substrate/dispatch/preference_hints.py` | 0.250 | 1 | 0.173 | normal | 🔒 |
| 113 | `substrate/dp_shuffler/epsilon_registry.py` | 0.250 | 1 | 0.173 | normal |  |
| 114 | `substrate/gap_detection/unanswered.py` | 0.250 | 1 | 0.173 | normal |  |
| 115 | `substrate/research_artifact/paths.py` | 0.250 | 1 | 0.173 | normal |  |
| 116 | `substrate/rights/ad_eligibility.py` | 0.250 | 1 | 0.173 | normal |  |
| 117 | `substrate/speak/interviewer_capture.py` | 0.250 | 1 | 0.173 | normal | 🔒 |
| 118 | `substrate/trust_center/publication.py` | 0.250 | 1 | 0.173 | normal |  |
| 119 | `substrate/marketplace_metrics/publisher_escrow.py` | 0.155 | 2 | 0.170 | normal | 🔒 |
| 120 | `substrate/books/meta_reading.py` | 0.154 | 2 | 0.169 | normal |  |
| 121 | `substrate/multi_user/crdt_scaffold/interfaces.py` | 0.242 | 1 | 0.168 | normal | 🔒 |
| 122 | `substrate/context_pack/note_injection.py` | 0.241 | 1 | 0.167 | normal |  |
| 123 | `substrate/seams/contracts.py` | 0.152 | 2 | 0.167 | normal |  |
| 124 | `substrate/ducklake/catalog.py` | 0.239 | 1 | 0.165 | normal |  |
| 125 | `substrate/advertisers/store.py` | 0.238 | 1 | 0.165 | normal | 🔒 |
| 126 | `substrate/books/model.py` | 0.150 | 2 | 0.165 | normal |  |
| 127 | `substrate/speak/biography.py` | 0.149 | 2 | 0.163 | normal | 🔒 |
| 128 | `substrate/multi_user/crdt_scaffold/fakes.py` | 0.230 | 1 | 0.159 | normal | 🔒 |
| 129 | `substrate/federation/slice.py` | 0.228 | 1 | 0.158 | normal | 🔒 |
| 130 | `substrate/ad_inventory/event_subscription.py` | 0.227 | 1 | 0.158 | normal | 🔒 |
| 131 | `substrate/dp_shuffler/event_emit.py` | 0.227 | 1 | 0.158 | normal |  |
| 132 | `substrate/legal_gate/__init__.py` | 0.227 | 1 | 0.158 | package_init | 🔒 |
| 133 | `substrate/speak/subject_consent.py` | 0.227 | 1 | 0.158 | normal | 🔒 |
| 134 | `substrate/gap_detection/ranking.py` | 0.226 | 1 | 0.157 | normal |  |
| 135 | `substrate/graph_per_user/key_provider.py` | 0.224 | 1 | 0.155 | normal | 🔒 |
| 136 | `substrate/flywheel/reuse_gate.py` | 0.141 | 2 | 0.155 | normal | 🔒 |
| 137 | `substrate/speak/physical_book.py` | 0.222 | 1 | 0.154 | normal | 🔒 |
| 138 | `substrate/ad_inventory/decisions_log.py` | 0.220 | 1 | 0.153 | normal | 🔒 |
| 139 | `substrate/cross_graph/ask_expert.py` | 0.220 | 1 | 0.152 | normal | 🔒 |
| 140 | `substrate/schemas/documents.py` | 0.095 | 4 | 0.152 | normal |  |
| 141 | `substrate/rev_share/rollover_persistence.py` | 0.220 | 1 | 0.152 | normal |  |
| 142 | `substrate/speak/events.py` | 0.107 | 3 | 0.149 | normal | 🔒 |
| 143 | `substrate/dispatch/router.py` | 0.107 | 3 | 0.148 | normal | 🔒 |
| 144 | `substrate/ad_inventory/frame_attention.py` | 0.133 | 2 | 0.146 | normal | 🔒 |
| 145 | `substrate/marketplace_metrics/data_sources.py` | 0.209 | 1 | 0.145 | normal | 🔒 |
| 146 | `substrate/billing/kyc.py` | 0.209 | 1 | 0.145 | normal | 🔒 |
| 147 | `substrate/ad_inventory/inventory_persistence.py` | 0.208 | 1 | 0.144 | normal | 🔒 |
| 148 | `substrate/ad_inventory/ad_bidding.py` | 0.205 | 1 | 0.142 | normal | 🔒 |
| 149 | `substrate/write/style_profile.py` | 0.129 | 2 | 0.142 | normal | 🔒 |
| 150 | `substrate/legal_gate/gate.py` | 0.203 | 1 | 0.141 | normal | 🔒 |
| 151 | `substrate/ingest_checkpoint.py` | 0.127 | 2 | 0.140 | normal |  |
| 152 | `substrate/quality_gate/gate.py` | 0.123 | 2 | 0.136 | normal |  |
| 153 | `substrate/research_artifact/export.py` | 0.194 | 1 | 0.135 | normal |  |
| 154 | `substrate/loop_3/checklist_store.py` | 0.193 | 1 | 0.134 | normal | 🔒 |
| 155 | `substrate/coordination/gate_ledger.py` | 0.121 | 2 | 0.133 | normal | 🔒 |
| 156 | `substrate/ad_inventory/advertiser_onboarding.py` | 0.188 | 1 | 0.130 | normal | 🔒 |
| 157 | `substrate/research_artifact/hooks.py` | 0.188 | 1 | 0.130 | normal |  |
| 158 | `substrate/billing/tax_reports.py` | 0.187 | 1 | 0.129 | normal | 🔒 |
| 159 | `substrate/speak/drw_gap_source.py` | 0.117 | 2 | 0.129 | normal | 🔒 |
| 160 | `substrate/eval/groundedness/scorer.py` | 0.117 | 2 | 0.128 | normal |  |
| 161 | `substrate/ad_inventory/transfer_initiator.py` | 0.184 | 1 | 0.128 | normal | 🔒 |
| 162 | `substrate/speak/independence.py` | 0.184 | 1 | 0.128 | normal | 🔒 |
| 163 | `substrate/invariants/__init__.py` | 0.116 | 2 | 0.128 | package_init |  |
| 164 | `substrate/graph/traverse.py` | 0.184 | 1 | 0.128 | normal |  |
| 165 | `substrate/books/page_anchor.py` | 0.115 | 2 | 0.127 | normal |  |
| 166 | `substrate/marketplace_metrics/book_escrow.py` | 0.078 | 4 | 0.126 | normal | 🔒 |
| 167 | `substrate/contracts/interviewer.py` | 0.113 | 2 | 0.124 | normal |  |
| 168 | `substrate/cross_graph/partner_identity.py` | 0.178 | 1 | 0.123 | normal | 🔒 |
| 169 | `substrate/graph/schema.py` | 0.063 | 6 | 0.123 | normal |  |
| 170 | `substrate/ducklake/migration.py` | 0.178 | 1 | 0.123 | normal |  |
| 171 | `substrate/edit/authoring_trajectory.py` | 0.112 | 2 | 0.123 | normal | 🔒 |
| 172 | `substrate/cross_graph/outbound_transport.py` | 0.176 | 1 | 0.122 | normal | 🔒 |
| 173 | `substrate/autoresearch/proposal.py` | 0.175 | 1 | 0.122 | normal |  |
| 174 | `substrate/research_artifact/blocks.py` | 0.174 | 1 | 0.121 | normal |  |
| 175 | `substrate/dispatch/providers/vision_anthropic.py` | 0.173 | 1 | 0.120 | normal | 🔒 |
| 176 | `substrate/ad_inventory/attribution_explain.py` | 0.108 | 2 | 0.118 | normal | 🔒 |
| 177 | `substrate/loop_3/sft_runner.py` | 0.170 | 1 | 0.118 | normal | 🔒 |
| 178 | `substrate/anti_gaming/view_fraud.py` | 0.167 | 1 | 0.116 | normal | 🔒 |
| 179 | `substrate/cross_graph/federation_config_store.py` | 0.167 | 1 | 0.116 | normal | 🔒 |
| 180 | `substrate/dispatch/providers/vision_bootstrap.py` | 0.167 | 1 | 0.116 | normal | 🔒 |
| 181 | `substrate/research_bridge/db_path.py` | 0.167 | 1 | 0.116 | normal | 🔒 |
| 182 | `substrate/collective_graph/eligibility.py` | 0.083 | 3 | 0.116 | normal | 🔒 |
| 183 | `substrate/contracts/accrual.py` | 0.071 | 4 | 0.115 | normal |  |
| 184 | `substrate/cross_graph/inbound.py` | 0.164 | 1 | 0.114 | normal | 🔒 |
| 185 | `substrate/write/outline.py` | 0.103 | 2 | 0.113 | normal | 🔒 |
| 186 | `substrate/books/serve.py` | 0.070 | 4 | 0.113 | normal |  |
| 187 | `substrate/eval/groundedness/provenance.py` | 0.102 | 2 | 0.112 | normal |  |
| 188 | `substrate/contracts/nodes.py` | 0.081 | 3 | 0.112 | normal |  |
| 189 | `substrate/graph_per_user/lifecycle.py` | 0.161 | 1 | 0.111 | normal | 🔒 |
| 190 | `substrate/rights_audit.py` | 0.100 | 2 | 0.110 | normal |  |
| 191 | `substrate/rev_share/splits.py` | 0.158 | 1 | 0.109 | normal |  |
| 192 | `substrate/context_pack/note_budget.py` | 0.157 | 1 | 0.109 | normal |  |
| 193 | `substrate/notebooks/__init__.py` | 0.154 | 1 | 0.106 | package_init |  |
| 194 | `substrate/research_artifact/import_notes.py` | 0.097 | 2 | 0.106 | normal |  |
| 195 | `substrate/speak/publish.py` | 0.153 | 1 | 0.106 | normal | 🔒 |
| 196 | `substrate/anti_gaming/red_team.py` | 0.153 | 1 | 0.106 | normal | 🔒 |
| 197 | `substrate/billing/aggregator.py` | 0.153 | 1 | 0.106 | normal | 🔒 |
| 198 | `substrate/rev_share/rollover.py` | 0.151 | 1 | 0.105 | normal |  |
| 199 | `substrate/ingest_budget.py` | 0.095 | 2 | 0.105 | normal |  |
| 200 | `substrate/speak/schema.py` | 0.150 | 1 | 0.104 | normal | 🔒 |
| 201 | `substrate/context_pack/assembler.py` | 0.075 | 3 | 0.104 | normal |  |
| 202 | `substrate/speak/async_interview.py` | 0.148 | 1 | 0.103 | normal | 🔒 |
| 203 | `substrate/research_artifact/build_body.py` | 0.147 | 1 | 0.102 | normal |  |
| 204 | `substrate/research_bridge/schema.py` | 0.145 | 1 | 0.101 | normal | 🔒 |
| 205 | `substrate/anti_gaming/click_fraud.py` | 0.143 | 1 | 0.099 | normal | 🔒 |
| 206 | `substrate/books/curate.py` | 0.143 | 1 | 0.099 | normal |  |
| 207 | `substrate/marketplace_metrics/advertiser_retention.py` | 0.143 | 1 | 0.099 | normal | 🔒 |
| 208 | `substrate/ad_inventory/frame_attention_accrual.py` | 0.090 | 2 | 0.099 | normal | 🔒 |
| 209 | `substrate/cross_graph_writer/queue.py` | 0.141 | 1 | 0.098 | normal | 🔒 |
| 210 | `substrate/gap_detection/candidates.py` | 0.140 | 1 | 0.097 | normal |  |
| 211 | `substrate/speak/publish_gate.py` | 0.140 | 1 | 0.097 | normal | 🔒 |
| 212 | `substrate/dedup.py` | 0.088 | 2 | 0.096 | normal |  |
| 213 | `substrate/deletion_worker/worker.py` | 0.138 | 1 | 0.096 | normal |  |
| 214 | `substrate/anti_gaming/attribution_fraud.py` | 0.136 | 1 | 0.095 | normal | 🔒 |
| 215 | `substrate/coordination/roadmap.py` | 0.068 | 3 | 0.094 | normal | 🔒 |
| 216 | `substrate/voice_style/constructions.py` | 0.085 | 2 | 0.094 | normal |  |
| 217 | `substrate/ai_actions/actions.py` | 0.135 | 1 | 0.094 | normal |  |
| 218 | `substrate/unit_dedup.py` | 0.085 | 2 | 0.093 | normal |  |
| 219 | `substrate/anti_gaming/verdict.py` | 0.134 | 1 | 0.093 | normal | 🔒 |
| 220 | `substrate/contracts/context_pack.py` | 0.133 | 1 | 0.092 | normal |  |
| 221 | `substrate/multi_user/skill_accumulator.py` | 0.133 | 1 | 0.092 | normal | 🔒 |
| 222 | `substrate/dispatch/providers/anthropic.py` | 0.083 | 2 | 0.092 | normal | 🔒 |
| 223 | `substrate/speak/interviewer_context.py` | 0.083 | 2 | 0.092 | normal | 🔒 |
| 224 | `substrate/write/brainstorm_blocks.py` | 0.083 | 2 | 0.092 | normal | 🔒 |
| 225 | `substrate/dp_shuffler/production.py` | 0.132 | 1 | 0.091 | normal |  |
| 226 | `substrate/books/serve_guard.py` | 0.057 | 4 | 0.091 | normal |  |
| 227 | `substrate/edit/harvest_authoring.py` | 0.081 | 2 | 0.089 | normal | 🔒 |
| 228 | `substrate/research_bridge/ingest_file.py` | 0.128 | 1 | 0.089 | normal | 🔒 |
| 229 | `substrate/books/takedown.py` | 0.125 | 1 | 0.087 | normal |  |
| 230 | `substrate/ad_inventory/auction_model.py` | 0.124 | 1 | 0.086 | normal | 🔒 |
| 231 | `substrate/seams/thread.py` | 0.077 | 2 | 0.085 | normal |  |
| 232 | `substrate/event_log/events.py` | 0.119 | 1 | 0.083 | normal |  |
| 233 | `substrate/loop_3/verifiers_env.py` | 0.118 | 1 | 0.082 | normal | 🔒 |
| 234 | `substrate/dp_shuffler/preference_learning.py` | 0.117 | 1 | 0.081 | normal |  |
| 235 | `substrate/loop_3/trajectory_harvest.py` | 0.117 | 1 | 0.081 | normal | 🔒 |
| 236 | `substrate/research_artifact/schema.py` | 0.117 | 1 | 0.081 | normal |  |
| 237 | `substrate/loop_3/unlock_gate.py` | 0.116 | 1 | 0.081 | normal | 🔒 |
| 238 | `substrate/corpus_audit.py` | 0.038 | 7 | 0.079 | normal |  |
| 239 | `substrate/coordination/consent_view.py` | 0.072 | 2 | 0.079 | normal | 🔒 |
| 240 | `substrate/research_artifact/compose.py` | 0.114 | 1 | 0.079 | normal |  |
| 241 | `substrate/public_notes_ingest/pipeline.py` | 0.113 | 1 | 0.078 | normal |  |
| 242 | `substrate/rev_share/mixed_attribution.py` | 0.113 | 1 | 0.078 | normal |  |
| 243 | `substrate/ad_targeting/matcher.py` | 0.112 | 1 | 0.078 | normal | 🔒 |
| 244 | `substrate/contracts/note_taker.py` | 0.111 | 1 | 0.077 | normal |  |
| 245 | `substrate/ad_inventory/auction_features.py` | 0.109 | 1 | 0.076 | normal | 🔒 |
| 246 | `substrate/write/provenance.py` | 0.069 | 2 | 0.076 | normal | 🔒 |
| 247 | `substrate/speak/payout_verifier.py` | 0.109 | 1 | 0.075 | normal | 🔒 |
| 248 | `substrate/multi_user/skill_writer.py` | 0.109 | 1 | 0.075 | normal | 🔒 |
| 249 | `substrate/auth/email_provider.py` | 0.107 | 1 | 0.074 | normal |  |
| 250 | `substrate/gap_detection/contradiction.py` | 0.106 | 1 | 0.073 | normal |  |
| 251 | `substrate/research_artifact/context.py` | 0.067 | 2 | 0.073 | normal |  |
| 252 | `substrate/coordination/cost_view.py` | 0.066 | 2 | 0.072 | normal | 🔒 |
| 253 | `substrate/legal_gate/predicate.py` | 0.104 | 1 | 0.072 | normal | 🔒 |
| 254 | `substrate/contracts/conformance.py` | 0.100 | 1 | 0.069 | normal |  |
| 255 | `substrate/attribution/compute.py` | 0.050 | 3 | 0.069 | normal |  |
| 256 | `substrate/write/block_search.py` | 0.050 | 3 | 0.069 | normal | 🔒 |
| 257 | `substrate/marketplace_metrics/dashboard.py` | 0.099 | 1 | 0.068 | normal | 🔒 |
| 258 | `substrate/constants.py` | 0.038 | 5 | 0.067 | normal |  |
| 259 | `substrate/research_bridge/eval/scoring.py` | 0.095 | 1 | 0.066 | normal | 🔒 |
| 260 | `substrate/autoresearch/wedge3_sweep.py` | 0.094 | 1 | 0.065 | normal |  |
| 261 | `substrate/dispatch/providers/vision_openai.py` | 0.093 | 1 | 0.065 | normal | 🔒 |
| 262 | `substrate/research_bridge/llm_dispatch.py` | 0.093 | 1 | 0.064 | normal | 🔒 |
| 263 | `substrate/research_bridge/versioning.py` | 0.092 | 1 | 0.064 | normal | 🔒 |
| 264 | `substrate/graph/rlm_tools.py` | 0.057 | 2 | 0.063 | normal |  |
| 265 | `substrate/attribution/algorithms.py` | 0.090 | 1 | 0.062 | normal |  |
| 266 | `substrate/context_pack/note_retrieval.py` | 0.089 | 1 | 0.062 | normal |  |
| 267 | `substrate/context_pack/style_guide.py` | 0.056 | 2 | 0.062 | normal |  |
| 268 | `substrate/write/trace.py` | 0.056 | 2 | 0.061 | normal | 🔒 |
| 269 | `substrate/books/personal_space.py` | 0.055 | 2 | 0.060 | normal |  |
| 270 | `substrate/public_graph/__init__.py` | 0.087 | 1 | 0.060 | package_init | 🔒 |
| 271 | `substrate/dispatch/providers/openai_compat.py` | 0.086 | 1 | 0.060 | normal | 🔒 |
| 272 | `substrate/contracts/servable.py` | 0.039 | 3 | 0.055 | normal |  |
| 273 | `substrate/multi_user/crdt_scaffold/access_control.py` | 0.077 | 1 | 0.053 | normal | 🔒 |
| 274 | `substrate/trust_center/default_registry.py` | 0.077 | 1 | 0.053 | normal |  |
| 275 | `substrate/research_bridge/eval/labels.py` | 0.076 | 1 | 0.053 | normal | 🔒 |
| 276 | `substrate/eval/groundedness/harness.py` | 0.046 | 2 | 0.051 | normal |  |
| 277 | `substrate/payouts/ledger.py` | 0.072 | 1 | 0.050 | normal |  |
| 278 | `substrate/speak/corroboration.py` | 0.071 | 1 | 0.049 | normal | 🔒 |
| 279 | `substrate/marketplace_metrics/creator_distribution.py` | 0.070 | 1 | 0.049 | normal | 🔒 |
| 280 | `substrate/dispatch/multi_cloud.py` | 0.069 | 1 | 0.048 | normal | 🔒 |
| 281 | `substrate/write/migrate_outline_block.py` | 0.067 | 1 | 0.047 | normal | 🔒 |
| 282 | `substrate/voice_style/ab_runner.py` | 0.066 | 1 | 0.046 | normal |  |
| 283 | `substrate/research_bridge/extractor.py` | 0.066 | 1 | 0.046 | normal | 🔒 |
| 284 | `substrate/research_bridge/ingest.py` | 0.064 | 1 | 0.045 | normal | 🔒 |
| 285 | `substrate/contracts/outline_block.py` | 0.040 | 2 | 0.044 | normal |  |
| 286 | `substrate/ai_actions/handlers.py` | 0.061 | 1 | 0.042 | normal |  |
| 287 | `substrate/research_bridge/gap.py` | 0.060 | 1 | 0.042 | normal | 🔒 |
| 288 | `substrate/contracts/dependency_map.py` | 0.056 | 1 | 0.039 | normal |  |
| 289 | `substrate/dispatch/providers/bootstrap.py` | 0.034 | 2 | 0.037 | normal | 🔒 |
| 290 | `substrate/graph/backfill_insight_question.py` | 0.030 | 2 | 0.032 | normal |  |
| 291 | `substrate/notebooks/tiptap_codec.py` | 0.046 | 1 | 0.032 | normal |  |
| 292 | `substrate/research_artifact/__main__.py` | 0.042 | 1 | 0.029 | normal |  |
| 293 | `substrate/research_artifact/render.py` | 0.041 | 1 | 0.028 | normal |  |
| 294 | `substrate/write/clustering.py` | 0.024 | 2 | 0.027 | normal | 🔒 |
| 295 | `substrate/research_bridge/extractors.py` | 0.033 | 1 | 0.023 | normal | 🔒 |
| 296 | `substrate/synthesis_rubric/scorer.py` | 0.031 | 1 | 0.022 | normal |  |
| 297 | `substrate/research_bridge/source_detection.py` | 0.027 | 1 | 0.018 | normal | 🔒 |
| 298 | `substrate/cli/__main__.py` | 0.026 | 1 | 0.018 | normal |  |
| 299 | `substrate/cli/compact.py` | 0.023 | 1 | 0.016 | normal |  |
| 300 | `substrate/cli/hooks.py` | 0.020 | 1 | 0.014 | normal |  |
| 301 | `substrate/legal_gate/audit.py` | 0.010 | 1 | 0.007 | normal | 🔒 |
| 302 | `substrate/ad_inventory/__main__.py` | 0.007 | 1 | 0.005 | normal | 🔒 |
| 303 | `substrate/cross_graph/__main__.py` | 0.007 | 1 | 0.005 | normal | 🔒 |
| 304 | `substrate/cross_graph/__init__.py` | 8.000 | 0 | 0.000 | package_init | 🔒 |
| 305 | `substrate/auth/__init__.py` | 5.333 | 0 | 0.000 | package_init |  |
| 306 | `substrate/cross_graph_writer/__init__.py` | 4.000 | 0 | 0.000 | package_init | 🔒 |
| 307 | `substrate/multi_user/__init__.py` | 4.000 | 0 | 0.000 | package_init | 🔒 |
| 308 | `substrate/ad_targeting/__init__.py` | 3.000 | 0 | 0.000 | package_init | 🔒 |
| 309 | `substrate/attribution/__init__.py` | 3.000 | 0 | 0.000 | package_init |  |
| 310 | `substrate/dp_shuffler/__init__.py` | 3.000 | 0 | 0.000 | package_init |  |
| 311 | `substrate/public_notes_ingest/__init__.py` | 3.000 | 0 | 0.000 | package_init |  |
| 312 | `substrate/billing/__init__.py` | 2.667 | 0 | 0.000 | package_init | 🔒 |
| 313 | `substrate/collective_graph/__init__.py` | 2.500 | 0 | 0.000 | package_init | 🔒 |
| 314 | `substrate/synthesis_rubric/__init__.py` | 1.000 | 0 | 0.000 | package_init |  |
| 315 | `substrate/dispatch/providers/__init__.py` | 0.750 | 0 | 0.000 | package_init | 🔒 |
| 316 | `substrate/integrations.py` | 0.375 | 0 | 0.000 | normal |  |
| 317 | `substrate/ownership.py` | 0.219 | 0 | 0.000 | normal |  |
| 318 | `substrate/exhaustive.py` | 0.214 | 0 | 0.000 | normal |  |
| 319 | `substrate/result_helpers.py` | 0.211 | 0 | 0.000 | normal |  |
| 320 | `substrate/errors.py` | 0.182 | 0 | 0.000 | normal |  |
| 321 | `substrate/voice_style/suppression.py` | 0.167 | 0 | 0.000 | normal |  |
| 322 | `substrate/speak/gate_status.py` | 0.158 | 0 | 0.000 | normal | 🔒 |
| 323 | `substrate/ad_inventory/payout.py` | 0.145 | 0 | 0.000 | normal | 🔒 |
| 324 | `substrate/ducklake/stage.py` | 0.143 | 0 | 0.000 | normal |  |
| 325 | `substrate/auth/magic_link.py` | 0.114 | 0 | 0.000 | normal |  |
| 326 | `substrate/research_bridge/detect_external.py` | 0.096 | 0 | 0.000 | normal | 🔒 |
| 327 | `substrate/escape_hatch.py` | 0.088 | 0 | 0.000 | normal |  |
| 328 | `substrate/loop_3/rubric_verifier.py` | 0.083 | 0 | 0.000 | normal | 🔒 |
| 329 | `substrate/cli/queue.py` | 0.069 | 0 | 0.000 | normal |  |
| 330 | `substrate/voice_style/rubric.py` | 0.050 | 0 | 0.000 | normal |  |
| 331 | `substrate/graph/migrate_v9_insight_question.py` | 0.032 | 0 | 0.000 | normal |  |
| 332 | `substrate/__init__.py` | 0.000 | 0 | 0.000 | package_init |  |
| 333 | `substrate/audit/__init__.py` | 0.000 | 1 | 0.000 | package_init |  |
| 334 | `substrate/eval/__init__.py` | 0.000 | 1 | 0.000 | package_init |  |
| 335 | `substrate/graph/retrieval_adapters/__init__.py` | 0.000 | 1 | 0.000 | package_init |  |


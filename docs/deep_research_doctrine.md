# Deep-Research Doctrine — competitive study → binding design verdicts

**Status:** Draft v1 for operator ratification · 2026-07-10
**Author:** Fable 5 /infinite orchestrator (session 80c31883), hatch `inf-competitive-deep-research-study`
**Mandate (operator, verbatim intent):** "I want to provide the highest quality deep research
product in the world (so study the technical decisions made by competition, write specs, and
execute meaningful code to reach that goal)."
**Evidence base:** four primary-source dossiers (OpenAI Deep Research/Agent, Perplexity,
Gemini Deep Research + Anthropic multi-agent system, open-source/infra/benchmarks) at
`~/Antiek/.infinite/research/competitive-deep-research/*.md` — every load-bearing claim below
carries its public source; the dossiers carry the full citation register. Six load-bearing
claims were independently adversarially re-checked (verdicts in §8).

---

## 0. The one-paragraph read

Across four independent lineages the same physics shows up: **research quality is bought with
verified-useful token/tool-call budget** (OpenAI's pass-rate-vs-tool-calls curve; Anthropic:
token spend explains ~80% of eval variance; Gemini prices two tiers by input tokens; GPT-Researcher
spans the frontier with two integers). Everything else that measurably works is stack
engineering that Antiek can adopt: a **user-editable brief/plan gate** before spending, **context
isolation with compression at every agent boundary**, **statement-level citation binding scored
by a mechanical gate**, **multi-agent gathering with a single writer**, **perspective-conditioned
sub-questions**, a **durable async runner with resume**, and an **eval harness that exists before
any quality claim**. The moats we cannot copy are OpenAI's RL-trained browsing model and
Perplexity's in-house index — and the HF-replication gap (55 vs 67 GAIA) plus open-source RACE
leaders (55.77, above 2025 commercial products) bound how much those moats matter for a
personal workstation. Antiek's own unfair advantage is one nobody in the field has: **a personal
knowledge graph of twin insight/question notes to seed perspectives, and an HTML-first document
model where offset-bound citations are native markup.**

## 1. Binding invariants (adopt as law; each has a falsifiable failure signature)

| # | Invariant | Evidence | Falsified when |
|---|---|---|---|
| I-1 | **Budget is the quality dial and must be explicit.** Every research run declares a `(breadth, depth, token_budget, max_tool_calls)` tuple; tiers fast/deep/wrestle are definitions of these tuples, surfaced in the run record and the #440 cost projection. | OpenAI tool-call curve; Anthropic 80%-variance; Gemini $1–3/$3–7 tiers; GPT-R breadth/depth knobs | Rubric scores flat while budget scales — then the loop, not the budget, is the bottleneck |
| I-2 | **No raw page ever enters the synthesis context.** Per-source extractive, attribution-preserving spans (~200–1k tokens/doc) at fetch time; findings pruned at every agent boundary; raw HTML offloaded to the doc store. | Perplexity compressed-low beats uncompressed-high on BrowseComp at 3× fewer tokens; LangChain prune-before-return; deepagents filesystem offload | Span-fed runs lose >2pts accuracy vs full-page on our eval set |
| I-3 | **Statement-level citation binding, mechanically gated.** Citations are `(start, end, source_url, verbatim_span)` annotations in the HTML projection (`<cite>`-class markup, not bibliographies). A FACT-style claim-support checker gates "report done". | OpenAI offset annotations; Perplexity extractive-for-citation-fidelity; DeepResearch-Bench FACT scores statement support | <90% claim-support rate on a 20-report sample, or the gate misses a regression a human catches |
| I-4 | **Multi-agent for gathering, ONE writer for synthesis.** Never parallel section-writing. Spawn-merge keeps draft-before-merge; the merged document is projected from one structure by one writer. | LangChain shipped parallel writers and reverted (disjoint); STORM writes from one outline | Blind pairwise prefers parallel-section variants on coherence |
| I-5 | **Brief-gate before budget.** Every non-trivial run mints an editable HTML brief (question, scope, exclusions, source preferences, proposed budget tuple) the operator can amend before execution; midnight-oil's price-ceiling approval IS this gate for unattended runs. | Gemini `collaborative_planning` revise-or-approve; OpenAI clarify+rewrite outside the research model; LangChain scope→brief; Co-STORM turn-taking | Edited briefs fail to beat unedited on blind pairwise preference over 20 runs |
| I-6 | **Refuse-or-re-retrieve below a retrieval floor.** A weak result set is discarded and re-queried, or the run says "insufficient sources" — it never synthesizes from thin evidence. | Perplexity discard-and-restart; Srinivas "only say things it can find… from multiple sources" | Hallucination rate is flat above vs below the floor (floor is theater) |
| I-7 | **Durable async runner with resume-from-error.** Runs >5 min are background jobs with a live steps+sources trace, notification on completion, checkpointed state, and resume instead of restart on transient failure. | Gemini async task manager w/ graceful recovery; Anthropic resume+checkpoints+rainbow deploys; OpenAI async+sidebar | ≥30-min runs fail end-to-end from single transient tool errors at a measurable rate |
| I-8 | **Read-only research boundary.** The research loop cannot construct arbitrary URLs, code-exec runs in a no-internet sandbox, any shell surface is GET-only. | OpenAI post-mitigation injection ≈0–0.5%; complete-mediation pattern already proven in Sanabil bridge work | An injection eval exfiltrates, or the boundary blocks a legitimate research pattern with no override path |
| I-9 | **The eval harness precedes the quality claim.** ~20 real queries + single-call LLM judge (factual accuracy, citation accuracy, completeness, source quality, tool efficiency), judge version pinned; RACE+FACT self-benchmark before ever saying "highest quality". | Anthropic 20-query start-small; DeepResearch-Bench judge-swap non-comparability warning | A human-visible regression passes the judge (then extend the rubric, don't abandon it) |

## 2. INTEGRATE NOW (wedges in dependency order; each with its done-bar)

**W0 — Research eval harness (prerequisite to every other wedge's done-bar).**
20 operator-real queries; judge rubric per I-9 pinned to a named judge model+version; scores
logged per run into the substrate event log; wire into Antiek-bench's weekly cycle (the operator's
recursive-bench vision gets its first real per-task dataset here — `by_task=deep_research`).
*Done:* two consecutive weekly runs produce comparable scores; a deliberately degraded retriever
run is detected as a regression. *(Owner-shaped: substrate + antiek_bench; no UI needed for v1.)*

**W1 — Budget tuples behind the tiers (I-1).**
Define fast/deep/wrestle as explicit `(breadth, depth, token_budget, max_tool_calls)` in one
module; run record carries the declared tuple + actuals; #440 cost projection reads the tuple
instead of ad-hoc estimates; decision-tree driver displays it.
*Done:* ≥90% of runs complete within declared budget; projection error vs actual <25% median.

**W2 — Brief-gate (I-5).**
Highlight-spawn and workstation-launch mint a brief artifact (HTML, editable, versioned like any
document); Run starts only on approve; midnight-oil reuses the identical brief schema with the
price-ceiling field required. Clarifier stage = one cheap-model pass generating 2–3 questions
folded into the brief.
*Done:* A/B over 20 runs per I-5; brief stored + linked from the report's provenance.

**W3 — Compression-at-boundary (I-2) + refuse floor (I-6).**
Per-source extractive spans with attribution at fetch; retrieval-quality score; discard-and-requery
below floor; raw pages parked in the doc store with stable ids.
*Done:* synthesis-stage tokens −60% at equal-or-better W0 citation accuracy; floor trips visibly
in the trace.

**W4 — Offset citation binding + FACT gate (I-3).**
Writer emits claims bound to fetched spans; HTML projection renders per-sentence source cards
(Perplexity UX, native to our HTML vision); a checker pass scores claim-support and blocks "done"
below threshold; midnight-oil runs get the checker mandatory (async = free).
*Done:* ≥90% claim-support on 20 reports under an independent judge; every report's sources
panel resolves.

**W5 — Perspective seeding from the twin substrate (STORM, made Antiek-native).**
Derive 3–5 personas from the asset's graph neighborhood; generate sub-questions per persona,
seeded with the asset's existing twin question notes; sub-agents get isolated contexts (I-4).
This is the differentiation wedge: STORM simulates perspectives from Wikipedia — Antiek grows
them from the operator's own accumulated questions.
*Done:* persona-seeded runs beat flat decomposition by ≥10% on W0 coverage items.

**W6 — search/fetch corpus contract.**
Every Antiek corpus (notebooks, KB, arXiv cache, hosted books, twin notes) exposes exactly
`search(query)→ids` + `fetch(id)→document`; the research loop consumes corpora only through this
contract (OpenAI's MCP shape — also what makes "call arxiv/substack into my research" one
uniform mechanism).
*Done:* one new corpus becomes researchable with zero loop changes; recall parity on W0 queries.

**W7 — Scholarly + newsletter acquisition repair.**
arXiv via OAI-PMH daily harvest + local metadata cache (replaces the polling that earned the
2026-05 429-ban); OpenAlex (keyless) as cross-discipline backbone; Semantic Scholar for CS/AI
enrichment; Substack = RSS `/feed` for change-detection + `api/v1/archive` JSON for backfill,
honoring Retry-After.
*Done:* 30 days of midnight-oil ingestion, zero 429/ban events, metadata freshness ≤24h.

**W8 — Two-vendor web layer.**
Exa for semantic discovery (findSimilar maps directly onto highlight-spawned research — seed-URL →
similar sources; extends the standing Exa wedge in `integration_exa_browserbase.md`) + Jina-class
cheap extraction for reading. Never one vendor for both legs (~10× cost asymmetry).
*Done:* per-report web-infra cost −70% vs single-vendor at equal recall on 20 held-out queries.

**W9 — Midnight-oil durability (I-7).**
Checkpointed run state, resume-from-error, live trace, notify-on-done; reuse the audited keep-set
of the MO dispatch protocol (two-phase plan/apply with budget reservation) as the control plane —
the convergence audit (docs/decisions/midnight-oil-convergence-audit.md) already partitioned
which stages bind real effects.
*Done:* injected transient tool failures do not kill a 30-minute run; kill-and-resume produces
the same report modulo timestamps.

## 3. INTEGRATE LATER (gated, in this order)

- **L1 — Search-as-Code spike** (Perplexity v2: model writes Python against retrieval primitives —
  retrieve/filter/dedupe/rerank/fanout — in a sandbox; BrowseComp 40.7→83.8, <$1/task, −85% tokens
  in their case study). Gate: W0 exists AND W3 landed, so the lift is measurable; sandbox = the
  existing remote-exec/Daytona wedge with I-8 boundaries. 1-day spike on 20 multi-hop queries
  before any product commitment (same spike-first sequencing as the turbopuffer verdict).
- **L2 — Parallel-subagent head-to-head at matched budget.** Anthropic (10+ subagents, 90.2% lift)
  vs Gemini (single-agent iterative + test-time compute) is a genuine open disagreement; run both
  shapes on W0 at equal token budget before hard-coding either as default for `wrestle`.
  Effort-scaling rules (1 agent/3–10 calls; 2–4/10–15; 10+ for complex) adopted as prompt law
  either way — unconstrained effort choice is the documented 50-subagent failure mode.
- **L3 — Answer-as-eval-datapoint.** Judge-score every production research answer (Perplexity's
  loop) once W0's rubric is stable; feeds the recursive Antiek-bench rewrite the operator wants.
- **L4 — ML-prioritized source refresh** (importance × update-frequency) for the acquisition
  daemon; only meaningful once W7's harvest baseline has a month of data.
- **L5 — Post-hoc CitationAgent vs assembly-time binding A/B.** W4 ships assembly-time (fits
  extractive spans); Anthropic's post-hoc pass is the challenger; judge axis = citation accuracy.

## 4. REJECT (explicit, with reasons — hard to vary means saying no)

| Rejected | Why |
|---|---|
| In-house web crawl/index (Perplexity's 200B-URL Vespa moat) | Capital- and ops-intensive infra for a personal workstation; the two-vendor layer (W8) buys the capability at per-report cents |
| RL-training a browsing model (OpenAI's moat) | Not reachable with our resources; the HF gap (55 vs 67 GAIA) shows orchestration lands ~80% of the premium; revisit only via Prime-Intellect lane and only after W0 exists |
| 20-model routing orchestra (Perplexity "Computer") | The decision-tree driver + NotDiamond L7 advisory already cover model choice at Antiek's scale; per-subtask 20-model routing is complexity without a measured payer |
| Parallel section-writing | Reverted by LangChain for disjoint output; violates I-4 |
| Uniform-cadence recrawl of sources | Loses to prioritized refresh at any fixed budget (Perplexity's framing); do W7 first, L4 later |
| Speed as a headline goal (sub-3-min runs) | Perplexity's differentiator, wrong for ours: the operator's stated posture is depth/wrestling; async+durable (I-7) removes the latency pressure honestly |
| Adopting DeepSeek-R1-class engine for cost (Perplexity v1 move) | Model choice is already operator-owned via decision-tree/settings; doctrine binds the STACK, not a vendor |
| Building our own benchmark before running public ones | RACE/FACT + DeepConsult protocols exist, are open, and are position-debiased; Antiek-bench extends them rather than reinventing (I-9) |

## 5. What Antiek already has (do not rebuild)

Campaign PR #465 substrate this doctrine binds to, not duplicates: research tiers + #440 cost
projection + decision-tree driver badge (→W1); highlight-spawn floating research + spawn-merge
draft-before-merge (→W2/I-4); twin insight/question notes + promote-to-graph (→W5); MidnightOil
mode + price ceiling + MO dispatch-protocol keep-set (→W2/W9); Antiek-bench weekly by_source +
usage bridge (→W0/L3); HTML-first projection everywhere (→W4). The doctrine's job is wiring
these into the convergent architecture, not adding modes.

## 6. Sequencing & ownership

W0 → W1/W2 (parallel) → W3 → W4 → W5/W6 (parallel) → W7/W8 (parallel, acquisition-side) → W9 →
L-gates. Each wedge is one sprint-page-sized unit; htmlspec pages should be cut per wedge with
the invariant table (§1) embedded verbatim as the rigor block. Merges ride the normal operator
gate; nothing here touches §9.0 serve-rights or monetization surfaces.

## 7. Honest limits of this study

- Perplexity hub posts 403'd direct fetch; some quotes are as-syndicated (flagged [S] in the dossier).
- MarkTechPost "Computer/20 models" and ZipTie "60+ sources" are secondary teardowns — treated
  as color, never load-bearing for a verdict.
- Benchmarks move fast (DeepResearch-Bench swapped judges 2026-05); all numbers are 2026-07-10
  snapshots; W0 pins judge versions for exactly this reason.
- The four dossiers were produced by subagents of the same host model family; §8's adversarial
  re-check used a different engine lineage where available (see verdict lines for engine).

## 8. Adversarial re-check verdicts (heterogeneous refuter)

Six load-bearing claims were re-checked 2026-07-10 by a codex (OpenAI-lineage) adversarial
refuter instructed to REFUTE against primary sources (glm-cc judge attempted first; failed on
an HTTP 429 with zero verdicts — engine substitution logged per fleet doctrine):

- CLAIM-1 **CONFIRMED** — Opus-4-lead + Sonnet-4-subagents beat single-agent Opus 4 by 90.2%; token usage alone explains 80% of BrowseComp variance (anthropic.com/engineering/multi-agent-research-system).
- CLAIM-2 **CONFIRMED** — agents ≈4× chat tokens; multi-agent ≈15× (same source).
- CLAIM-3 **CONFIRMED** — `max_tool_calls` is the documented cost/latency control; URL-citation annotations carry start_index/end_index/url (platform.openai.com/docs/guides/deep-research).
- CLAIM-4 **CONFIRMED** — Search-as-Code: model-generated Python pipelines over a retrieval SDK in a sandbox; BrowseComp 40.7%→83.8% (research.perplexity.ai/articles/rethinking-search-as-code-generation).
- CLAIM-5 **CONFIRMED** — STORM: +25pp absolute on organization, +10pp on coverage vs outline-driven RAG on FreshWiki (arxiv.org/abs/2402.14207).
- CLAIM-6 **CONFIRMED** — GPT-Researcher: ~3 minutes / ~$0.10 per average research task (docs.gptr.dev).

---
*Evidence dossiers: `~/Antiek/.infinite/research/competitive-deep-research/{openai,perplexity,gemini-anthropic,opensource-infra}.md` (committed via fleet-state). This doc is the verdict layer; the dossiers are the record.*

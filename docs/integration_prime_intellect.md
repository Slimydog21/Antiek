# Spec: Prime Intellect ↔ Antiek Integration

**Status:** Draft v1, 2026-05-17. Owner: Faisal.
**Companion:** [loop_3_unlock_criteria.md](loop_3_unlock_criteria.md) (gate document for the deferred RL path).

**Stance:** Prime Intellect is a sharp tool for a narrow band of problems Antiek will eventually have. Adopting it across the board today would be cargo-culting — Antiek doesn't ship business logic yet (README: "No business logic ships yet"). The defensible integration is narrow and sequenced: wire two cheap insurance hooks now, scaffold one Phase 2 surface against Sprint 10's "first real-LLM run," and explicitly reject three superficially-attractive integrations that would weaken Antiek's architecture.

This spec is constrained by Antiek's existing decisions: the dispatch-tier model selections are deliberate, the trajectory schema is the locked RL substrate, and Loop 3 (RL) is gated on Loops 1–2 producing trajectories. The spec respects those gates; it does not relitigate them.

---

## 1. Verdict Matrix

| # | Integration | Verdict | Sprint |
|---|---|---|---|
| F | Trajectory schema → verifiers-compatibility test | **INTEGRATE NOW** | Sprint 10 |
| D | `prime eval run` as runner for Antiek-defined rubrics | **INTEGRATE NOW** (scaffolding) | Sprint 10 |
| A | GEPA prompt optimization on `parameter_extractor` | **INTEGRATE PHASE 2** | After eval set exists (Sprint 11–12) |
| B | `verifiers` env wrapping `parameter_extractor` | **STUB NOW, TRAIN NEVER (this sprint)** | Sprint 11; training deferred per Loop 3 gate |
| E | Hosted RL (`prime rl run`) on Antiek-derived model | **DEFER** | No earlier than 9–12 months out, gated on documented prerequisites |
| C | Add Prime Intellect as a dispatch provider | **REJECT** | — |
| G | Publish Antiek envs to Prime Hub | **REJECT (for now)** | — |

---

## 2. INTEGRATE NOW

### F. Trajectory schema compatibility test

**Why:** `substrate/event_log/events.py:35` already names Prime Intellect (verifiers / prime-rl / Hosted Training) as the intended downstream consumer of the Parquet event log. That's a commitment with no test backing it. If the verifiers' trajectory schema diverges from what Antiek emits, you find out 9 months from now when you actually want to train — too late.

**Scope:**
- Add `tests/test_event_log_verifiers_compat.py`. Construct a synthetic Antiek investigation Parquet from `substrate/event_log/`, then attempt to materialize it as a `verifiers.Trajectory` (or whatever the prime-rl trainer ingests). Assert round-trip on at least: `event_id`, `policy_id`, `parent_event_id`, `payload.prompt`, `payload.response`, `payload.reward` (when present).
- One paragraph in `docs/architecture_notes.md` §9 documenting the mapping (Antiek event → verifiers field).
- If the schemas diverge, **do not retrofit Antiek to match Prime**. Document the gap and write the adapter. Antiek's schema is the source of truth; verifiers compatibility is downstream.

**Cost:** ~half a day. **Reversibility:** total — it's a test.
**Reward:** insurance against a 9-month surprise.

**Honest caveat:** Prime's verifiers format may change between now and when you actually train. The test catches *today's* compatibility, not future-proofing. Re-run quarterly.

### D. `prime eval run` as the runner for Antiek rubrics

**Why:** Sprint 10 includes "first real-LLM run." The moment you run a real LLM you need an eval harness. Antiek's `middleware/constraint_check/` and `middleware/outcomes/RUBRIC_SCORED` define the rubric schema but the *runner* is unspecified. Building one from scratch is wasted work when `prime eval run` already does (a) parallel rollouts, (b) per-example logging, (c) cost tracking, (d) a dashboard, (e) re-running against multiple models for ablations.

**Scope:**
- Build `tests/eval/antiek_rubric_to_verifiers.py`: a thin adapter that wraps an Antiek `RUBRIC_SCORED` definition as a verifiers `Rubric`. Adapter must preserve the deterministic / judged / final split (do not collapse to a single scalar — Antiek tracks them separately for reasons).
- Build the first concrete eval set: 50 hand-curated (sub-question, expected extraction shape) pairs from arXiv abstracts in `acquisition/arxiv/`. Store at `tests/eval/datasets/parameter_extractor_v0.jsonl`. **Curated, not synthetic** — synthetic eval sets that you trained the prompt against are how Goodhart wins.
- Wire `prime eval run` to invoke against `substrate/dispatch/router.dispatch(role='parameter_extractor', ...)`. The eval calls Antiek's router, not Prime's provider directly — preserves dispatch as the source of truth for which model is used.

**Cost:** ~3 days including the curated 50-example set (the dataset is most of the work).
**Reversibility:** moderate — once teams depend on the eval, ripping it out is painful.

**Honest caveat:** Prime's eval API is opinionated (single reward scalar per example). Forcing Antiek's tri-part rubric through it requires choices. Default the `final_score` to what Prime sees, log `deterministic_score`/`judged_score` separately into Antiek's event log — do not lose information to fit Prime's shape.

---

## 3. INTEGRATE PHASE 2 (Sprint 11+)

### A. GEPA on `parameter_extractor`

**Why this role specifically:** It's the only role where every input has a *machine-checkable* output (Pydantic schema conformance + extracted-fact-vs-source overlap). Decomposer, connector, synthesizer all have rubrics that are mostly judged-by-LLM — GEPA on those amplifies judge bias.

**Prerequisites (all must be true before launching):**
1. The eval set from §D exists and has been validated by you spot-checking >20% of examples by hand.
2. Two baseline runs (current prompt, current model) on the eval set have produced stable scores (low variance across runs).
3. The constraint-check pipeline from `middleware/constraint_check/` is shipping `fail_constraint` events. GEPA's reward must include constraint pass rate, not just schema conformance.

**Scope when ready:**
- `prime gepa run parameter_extractor -m deepseek/v4-flash` against the curated eval set. Budget: $50 of inference (~1k rollouts × 50 examples). Walk away if scores haven't moved by 5 generations.
- **Output:** an evolved prompt that goes into `roles/parameter_extractor/prompts/v_gepa_1.md`. Versioned. The old prompt stays. Production prompt switch is a separate human decision, not an automatic GEPA win.

**Reject:** Running GEPA on `synthesizer`. Claude Opus 4.7 is the model; the prompt is not the bottleneck; iteration cost is prohibitive; the judge ↔ optimizer correlation is unmanaged.

### B. `verifiers` env stub for `parameter_extractor` (RL-ready, no training)

**Why:** Researchmaxx RL plan: Phase 3 = verifiers env. Antiek's `parameter_extractor` is the cleanest first env because: single-turn, schema-checkable, cheap to roll out. Building the env now (without training) means when Loop 3 unlocks you press a button instead of designing a substrate.

**Scope:**
- `~/Desktop/Antiek/environments/parameter_extractor/` — a `vf.Environment` subclass whose `load_environment` reads from the curated dataset, runs the extractor, and returns the constraint-check tri-part score as the reward.
- One round of `prime eval run` against this env to verify rollouts complete.
- **Do not run `prime rl run`.** The env exists as substrate, not as a training command.

**Cost:** ~2 days once the eval set + adapter from §D + §A exist.

**Hard rule:** No PR that launches `prime rl run` lands before the Loop 3 unlock criteria from [loop_3_unlock_criteria.md](loop_3_unlock_criteria.md) are met. The env is the *substrate* for training — it is not training.

---

## 4. EXPLICITLY DEFER

### E. Hosted RL training

The Researchmaxx vision states "on-policy RL via Prime Intellect" as the long-term posture. This spec does not reject that — it enforces the sequencing the Researchmaxx RL plan itself already commits to. Hosted RL requires all of these to be true:

1. **Trajectory volume:** ≥10k investigations in the event log, ≥80% with `policy_id` resolvable to an open-weight model. Currently: 0 production trajectories.
2. **SFT model:** A supervised-fine-tuned base exists on Antiek trajectories. Not started.
3. **Reward function:** Constraint-check + outcome record produce a stable, low-noise scalar correlated with downstream success. Currently: schema locked, scorer not implemented.
4. **Open-weight justification:** A concrete argument for why the open-weight model is needed (cost? latency? policy control? privacy?). Currently: missing. Today every tier uses a closed-weight provider because the closed-weight option is better. RL training only produces a useful artifact if you actually want to *deploy* an open-weight model.
5. **Eval headroom:** Eval on the SFT model shows the policy is consistently underperforming a documented ceiling. Currently: no eval, no ceiling.

**Spec deliverable:** [loop_3_unlock_criteria.md](loop_3_unlock_criteria.md) codifies the above. No RL work begins before that doc's checkboxes are all ticked.

---

## 5. EXPLICITLY REJECT

### C. Adding Prime Intellect as a dispatch provider

**Rejection on the merits, per tier:**

- **`verify` (Grok 4.3 via Hermes):** The point of cross-family verification is *family independence*. Prime's hosted models are Qwen / Llama / Nemotron / GPT-OSS — they share training-data and architectural lineage with each other and with DeepSeek (the model being verified). Routing `verify` to any of them collapses the independence the tier exists to provide.
- **`synthesis` (Claude Opus 4.7):** No hosted model on Prime is competitive with Opus 4.7 on long-form synthesis. This is not controversial.
- **`pro` / `flash` (DeepSeek V4):** DeepSeek V4 Flash via API is ~$0.07/M tokens. Prime hosted equivalents are 3–10× that at Antiek's volume. The dispatch router's whole design point is that tiers map to the *best* model at each price point; that's an active optimization, not a placeholder.

If a future Antiek-trained Qwen checkpoint exists and beats DeepSeek V4 Flash on the curated eval, *then* a Prime provider adapter is worth writing. Today the adapter has no model to serve.

**This rejection is reversible** the moment §A and §B produce a model that wins on §D's eval.

### G. Publishing Antiek environments to Prime Hub

**Rejection on the merits:**

- The Antiek envs that would be publishable (parameter_extractor, decomposer-quality) encode Antiek's research methodology. The methodology is the product. Open-sourcing the verifier teaches competitors how to evaluate Antiek-style systems without the substrate.
- Hub publishing is valuable when you want external rollouts against your env (free eval coverage, dataset curation contributions). Antiek's eval sets are *meant* to be curated, not crowdsourced — that's the diligence point.
- **Cost of reversal:** asymmetric. Unpublishing an env doesn't unpublish people's forks.

Revisit when (a) you've built ≥3 internal envs and (b) you have a strategic reason to invite external contribution. Neither is true today.

---

## 6. Goodhart and Honesty Risks

A defensible spec names its own failure modes:

1. **GEPA on a schema-conformance reward** will produce prompts that satisfy the schema while extracting wrong facts. Mitigation: §A's prerequisite that constraint-pass rate (not just schema validity) feeds the reward.
2. **`prime eval run` on a 50-example set** will produce noisy scores. Mitigation: §D requires stable baselines before any optimization. Don't celebrate score deltas smaller than baseline variance.
3. **Verifiers env existence ≠ training readiness.** Stubbing §B then auto-running `prime rl run` because "the env's right there" is the single likeliest way this spec gets misused. §B's hard rule exists to prevent that.
4. **Curated eval set drift:** If the same person who writes the eval also writes the prompt, the prompt overfits to the eval. Mitigation: write the eval set *before* iterating on the prompt for that role, and require a second pair of eyes on the eval before any GEPA run.
5. **The Researchmaxx RL plan might be wrong.** This spec assumes "on-policy RL via Prime Intellect" is the right long-term posture. If the actual unlock criterion (§E.4 — open-weight deployment justification) never becomes true, hosted RL never happens, and the §B stub becomes dead code. That's an acceptable outcome — building the env is cheap, deleting it is cheap.

---

## 7. Sequencing & DoD

**Sprint 10 (now):**
- [ ] §F: Trajectory compat test merged with passing assertion or documented adapter.
- [ ] §D: Adapter from Antiek rubric to verifiers Rubric; first 50-example curated eval set; `prime eval run` invocable against `parameter_extractor` via the dispatch router.
- [ ] §E: [loop_3_unlock_criteria.md](loop_3_unlock_criteria.md) exists with all checkboxes unchecked.

**Sprint 11–12 (after Sprint 10 ships):**
- [ ] §A: First GEPA run executed; evolved prompt versioned; production switch deferred to human decision.
- [ ] §B: `environments/parameter_extractor/` env scaffold lives; `prime eval run` against it produces non-trivial rollouts.

**Never (under current state):**
- `prime rl run` invoked from any Antiek workflow.
- Prime Intellect adapter added to `substrate/dispatch/providers/`.
- Any Antiek env published to the public Hub.

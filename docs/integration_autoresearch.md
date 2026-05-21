# Antiek × Karpathy `autoresearch` — Integration Spec

**Status**: Draft v1, 2026-05-18.
**Scope**: Decide which technical primitives, ideas, and architectural patterns
from `karpathy/autoresearch` (MIT-licensed, released 2026-03-07) integrate into
Antiek, which are deferred behind unlock criteria, and which are explicitly
rejected as category errors. Produce defensible verdicts, not consensus
hedging.
**Predecessor docs**: `architecture_notes.md` (substrate-level commitments),
`master-product-spec.md` (product vision), `integration_prime_intellect.md`
(the sibling verdict-matrix spec — mirror its discipline), `loop_3_unlock_criteria.md`
(any training-time integration gates here).
**Operator quality bar**: intellectual honesty, rigor, defensibility. Explicit
REJECT verdicts where warranted. No "let's add autoresearch because it's
popular" framings.

---

## Table of contents

1. [What `autoresearch` actually is](#1-what-autoresearch-actually-is)
2. [What `autoresearch` is NOT — the misreading to avoid](#2-what-autoresearch-is-not--the-misreading-to-avoid)
3. [Mapping autoresearch's primitives to Antiek's surfaces](#3-mapping-autoresearchs-primitives-to-antieks-surfaces)
4. [Verdict matrix](#4-verdict-matrix)
5. [Wedge 1 — Prompt autoresearch for individual roles](#5-wedge-1--prompt-autoresearch-for-individual-roles)
6. [Wedge 2 — Phase 8 skill-patch accept/reject gate](#6-wedge-2--phase-8-skill-patch-acceptreject-gate)
7. [Wedge 3 — Context-pack and dispatch config sweeps](#7-wedge-3--context-pack-and-dispatch-config-sweeps)
8. [Wedge 4 — Local SFT loop for Loop 3 (DEFERRED behind unlock criteria)](#8-wedge-4--local-sft-loop-for-loop-3-deferred-behind-unlock-criteria)
9. [Explicit rejections (don't re-litigate)](#9-explicit-rejections-dont-re-litigate)
10. [Risks and mitigations](#10-risks-and-mitigations)
11. [Unlock criteria for promoting wedges](#11-unlock-criteria-for-promoting-wedges)
12. [Sprint placement](#12-sprint-placement)
13. [Open questions (genuinely unresolved)](#13-open-questions-genuinely-unresolved)
14. [What to do now](#14-what-to-do-now)

---

## 1. What `autoresearch` actually is

Read carefully. Most secondary coverage of autoresearch generalizes the
mechanic past what the code actually does.

### 1.1 The repo, concretely

Three files, ~630 LOC total, MIT license:

- **`prepare.py`** — frozen. One-time data preparation (download corpus, train
  a BPE tokenizer), runtime utilities (dataloader, eval functions). The agent
  does NOT modify this file. This is the "substrate" of autoresearch.
- **`train.py`** — the single mutation target. Contains the full GPT model,
  the optimizer (Muon + AdamW), and the training loop. Architecture,
  hyperparameters, optimizer settings, batch size — all live here. The agent
  edits this file end-to-end on every iteration.
- **`program.md`** — a markdown file of human-written instructions. Tells
  the agent what to try, what to avoid, what hypotheses to chase. Karpathy
  describes it as "a super lightweight skill." Operator iterates on
  `program.md`, NOT on the Python files.

Dependencies: PyTorch plus small packages. No distributed training. No
complex configs. Single NVIDIA GPU (tested on H100).

### 1.2 The outer loop

A separate coding agent (Claude Code, Cursor, etc — not bundled with the
repo) runs the loop:

```
while operator hasn't stopped:
    read program.md                          # context + instructions
    propose a change to train.py              # the mutation
    git add + commit baseline                 # checkpoint before run
    run train.py for exactly 5 minutes        # the experiment
    measure val_bpb (validation bits per byte)
    if val_bpb improved over prior best:
        keep change (advance baseline)
    else:
        git reset --hard prior baseline       # rollback
    repeat
```

Concrete cadence: ~12 experiments/hour, ~100 experiments overnight,
~700 experiments in a 2-day extended run (Karpathy's published number).

### 1.3 The metric

**`val_bpb`** — validation bits per byte. Vocab-size-independent so
architectural changes are fairly compared. Lower is better. One number per
run. The decision gate is `val_bpb_new < val_bpb_best`.

The metric being **cheap, deterministic, single-scalar, and tight-signal**
is load-bearing. It's the only reason the loop converges. Generalize away
from that property and the whole mechanic stops working.

### 1.4 The reported results

Karpathy's own 2-day run: ~700 experiments, ~20 additive improvements
that stack and transfer to larger models. "Time to GPT-2" benchmark
dropped from 2.02h → 1.80h (11% efficiency gain). Discovered specifics:
QKnorm missing a scaler multiplier for attention sharpening, Value
Embeddings benefit from regularization, banded attention tuning, AdamW
beta gains, weight decay scheduling.

Tobi Lutke (Shopify): pointed it at Shopify's Liquid templating engine,
got 53% faster rendering after 93 automated commits. **The closest
non-ML analog and the most informative data point for Antiek's
purposes** — because Antiek is also a non-ML domain.

### 1.5 The philosophy that survives genericization

Two ideas in autoresearch are reusable beyond ML training:

1. **"The program is `program.md`, not the code."** The human iterates on
   instructions; the agent iterates on artifacts. This is the same idea
   as Antiek's voice-and-style-discipline doc + synthesizer prompt
   addendum.
2. **A propose → execute → measure → gate loop only works when the metric
   is cheap, deterministic, and tight-signal.** When you can't get those
   three properties, the loop diverges (reward hacking, judge bias, cost
   runaway). This is the constraint Antiek will brush up against in every
   integration wedge below.

---

## 2. What `autoresearch` is NOT — the misreading to avoid

The headline "AI agents conducting research autonomously" naturally
suggests integration with Antiek's research substrate. **This is a
category error.** Antiek and autoresearch use the word "research" to
mean different things.

### 2.1 Autoresearch researches CODE. Antiek researches KNOWLEDGE.

- Autoresearch's research artifact is `train.py` — a modifiable Python
  program whose behavior is reproducible from source.
- Antiek's research artifact is `MASTER.md` — a synthesis grounded in a
  knowledge graph populated from external sources whose ground truth is
  outside the system.

The two domains have opposite epistemic shapes. Autoresearch can verify
its hypotheses cheaply against a fixed dataset. Antiek cannot — the
external world is the dataset, and verifying a claim about Tesla's
gross margin requires source attribution to a 10-K, not a 5-minute
training run.

### 2.2 Autoresearch is single-process, single-file, single-metric

Antiek is multi-provider (Hermes/Grok primary, OpenRouter fallback,
Whisper for transcription), multi-role (12 roles), multi-loop (Loops 1,
2, 3), multi-surface (research workstation, document wrestle, creation
workstation, interview), with a typed event log spanning everything.
**Substituting autoresearch for Antiek's investigation loop is not a
refactor — it's a rewrite.** Worth being clear: the operator's
12-sprint substrate investment is what makes Antiek defensible; throwing
it out to adopt a 630-LOC research-toy architecture would discard the
moat.

### 2.3 Autoresearch's gate is `val_bpb`. Antiek's gates are LLM-judged rubrics

Autoresearch's metric is the cross-entropy of a held-out validation
set — a function the operating system can compute deterministically.

Antiek's quality metrics live in `compounding/verification/` (rubric
registry) and `middleware/backtest/` + `middleware/outcomes/`. They are:
- Partly LLM-judged (rubric scores produced by `verifier` tier dispatches)
- Multi-dimensional (multiple rubrics per investigation)
- Lagged (an investigation's "ground truth" outcome may take months to
  observe)
- Noisy (stochastic across the same input)

This is **the** load-bearing difference for every wedge below. Where
autoresearch's gate is "did the number go down," Antiek's gate is "did
N noisy judges' median move enough to overcome variance, and is the
movement explained by a real quality change vs. reward-hacking the
judges." Every wedge below has to answer that question explicitly or
it doesn't ship.

### 2.4 Autoresearch is inference-time exploration of a config space. RL training is gradient descent on weights

These look similar from a distance — both are "agents improving over
time." They are not the same thing. Autoresearch's loop never updates
model weights between iterations; the agent's improvement comes from
better-chosen configurations. RL post-training (the Loop 3 path in
`loop_3_unlock_criteria.md`) updates weights via gradient descent on a
reward signal.

Conflating these wastes sprint budget. The Loop 3 unlock plan stays
gated on its own criteria (trajectory volume, SFT readiness, validated
reward, open-weight justification, eval headroom). Autoresearch's loop
is orthogonal — Wedge 4 below addresses a narrow intersection but
honors the gate.

---

## 3. Mapping autoresearch's primitives to Antiek's surfaces

Before the verdicts, the structural mapping. This is what makes the
verdicts checkable rather than aesthetic.

| autoresearch primitive | Closest Antiek analog | Mapping cleanliness |
|---|---|---|
| `prepare.py` (frozen substrate) | `substrate/` (event log, graph, dispatch, schemas) | Strong analog — both are the "don't touch this" layer the mutating agent reads from but never edits |
| `train.py` (mutation target) | A role's `prompt.py`, a `SKILL.md`, `dispatch/config.yaml`, `context_pack/assembler.py` config | Weak analog — there are MANY mutation targets in Antiek, no single `train.py`. Each integration wedge picks one |
| `program.md` (instructions to the agent) | `docs/strategy/voice-and-style-discipline.md`, `program.md` per role (does not exist yet) | Strong analog — Antiek already operates by "the discipline is the doc, not the code" |
| The 5-minute training run | A role dispatch + scoring against golden traces / rubrics | Medium analog — Antiek runs are seconds-to-minutes per dispatch; depends on which evaluator |
| `val_bpb` (the metric) | Rubric scores from `compounding/verification/`, backtest scores from `middleware/backtest/`, golden-trace hash match from `tools/golden_traces/` | **Weak analog — the load-bearing weakness.** Antiek's metrics are LLM-judged, noisy, lagged, multi-dimensional |
| `git commit` per accepted change | `ANTIEK_PARAM_VERSION` bump + JSONL event log entry | Strong analog — Antiek already does versioned-artifact discipline; just needs autoresearch's accept/reject gate wired in front |
| The outer coding agent | Claude Code (currently used for Antiek dev) | Identical — same external tool |

The strongest analogs are the `prepare.py` / `program.md` / git-commit
sides. The weakest is the **metric** side. Every wedge below stands or
falls on whether its metric is tight enough to make the gate decisive.

---

## 4. Verdict matrix

| Wedge | What it is | Verdict | Why |
|---|---|---|---|
| **Wedge 1: Prompt autoresearch for individual roles** | Loop that mutates a role's `prompt.py`, replays existing golden traces from `tools/golden_traces/`, scores the rubric, keeps or reverts | **INTEGRATE — start in Sprint 19 as a parallel side-track, gated to operator's local machine** | Highest leverage. Closest structural analog to Lutke's Shopify result. Antiek already has golden traces (deterministic replay) AND rubric scorers (the metric). Zero substrate risk because mutation target is prompt files, not substrate code |
| **Wedge 2: Phase 8 skill-patch accept/reject gate** | Current Phase 8 auto-patches `SKILL.md` unconditionally. Wrap the patch in `propose → backtest → keep-or-reject` | **INTEGRATE PHASE 2 — Sprint 20+, after Wedge 1 calibrates the metric question** | Real defect to fix. Researchmaxx's `synthesis_to_master.py` was broken; Antiek fixed it; but the patch still has no gate. Risk: skill patches that hurt downstream investigations get committed silently |
| **Wedge 3: Context-pack and dispatch config sweeps** | Sweep truncation strategy, layer order, role→tier mapping, budget allocation. Measure against `outcomes` table | **DEFER — gated on real trajectory volume from the production VM** | The metric prerequisite is volume. Sweeping configs against an under-populated `outcomes` table over-fits to noise. Need ≥500 investigations of accumulated outcomes before this wedge produces signal |
| **Wedge 4: Local SFT loop for Loop 3 unlock** | Use autoresearch's 5-min budget shape to drive local SFT runs on operator's GPU, optimizing val_loss against a held-out trajectory set | **DEFER — gated behind `loop_3_unlock_criteria.md`, not on top of it** | The Loop 3 unlock gate already exists. Autoresearch's shape is one valid implementation of "the SFT runner" mentioned in the unlock criteria, but doesn't change the gate |
| **Adopt `program.md` discipline for the operator-facing prose roles** | Add a `program.md` to each role module mirroring autoresearch's pattern | **INTEGRATE NOW — Sprint 17 substrate-side hygiene work, ~half a day** | Free. Codifies what the operator is already doing manually for the synthesizer voice/style discipline. Becomes the mutation surface for Wedge 1 later |
| **Rewrite Antiek's investigation loop in autoresearch's shape** | Replace `orchestration/loop_one/orchestrator.py` with an autoresearch-style 5-min-budget propose-execute-measure loop | **REJECT** | Category error. Investigations are not 5-min metric optimizations |
| **Use autoresearch as a dispatch substrate** | Route Antiek's LLM calls through autoresearch's runtime | **REJECT** | Autoresearch has no multi-provider routing, no fallback chain, no typed events. The Hermes-primary posture would have to be unwound. Net loss |
| **Publish Antiek roles as Hub-style `train.py` files** | Mirror autoresearch's "the world copies one file" distribution model | **REJECT** | Antiek's IP is the substrate + the compounding graph, not the role prompts. Publishing prompts gives away the only thing competitors can copy in a quarter |

---

## 5. Wedge 1 — Prompt autoresearch for individual roles

The highest-leverage integration. Detailed because it's the wedge that
actually ships.

### 5.1 What it does

For a single chosen role (recommendation: **`synthesizer`** — highest-
stakes prose role, voice-and-style discipline lives here):

1. Coding agent reads `roles/synthesizer/program.md` (new file, Section
   §4 INTEGRATE NOW work)
2. Agent proposes a change to `roles/synthesizer/prompt.py`
3. New module `tools/prompt_autoresearch/runner.py` replays N golden
   traces from `tools/golden_traces/captured/` against the candidate
   prompt
4. Runner computes a composite score: rubric scores (LLM-judged) +
   voice-and-style mechanical checks (grep `—` count, padding-phrase
   detection, sector vocabulary overlap — all deterministic)
5. If composite score improves over baseline by ≥ε (configurable), keep
   the change. Else `git checkout -- roles/synthesizer/prompt.py`
6. Bump `ANTIEK_PARAM_VERSION` on accepted changes
7. Emit a new typed event `prompt_autoresearch.iteration_completed`
   carrying the candidate diff, baseline score, candidate score, accept
   or reject decision, judge invocation IDs

### 5.2 Why this wedge ships first

- **Mutation target is already isolated.** Role prompts are dedicated
  files. No substrate touched.
- **Golden traces already exist.** `tools/golden_traces/` was built in
  Sprint 4 as the dependency for orchestrate.py role extraction.
  Reusing for evaluation is essentially free.
- **The metric has deterministic components.** Voice-and-style checks
  are grep-based; rubric scoring is the only LLM-in-the-loop component.
  This caps the reward-hacking surface.
- **The operator is already doing it manually.** Synthesizer prompt
  addendum (master-product-spec §5.3) is hand-tuned. Autoresearch's
  loop is what the operator would do if they had unlimited time. The
  question is whether the loop produces gains the operator wouldn't
  produce in the same wall-clock time spent.

### 5.3 The metric design — the load-bearing decision

A composite score with deterministic floor:

```
composite_score(prompt, traces) =
    0.40 * mean(rubric_score(synthesizer_output, trace))           # LLM-judged
    + 0.30 * voice_style_score(synthesizer_output)                  # deterministic
    + 0.20 * sector_vocab_overlap(synthesizer_output, trace.corpus) # deterministic
    + 0.10 * grounding_preserved_rate(synthesizer_output, trace)    # deterministic
```

Three of four components are deterministic. The LLM-judged rubric carries
40% — large enough to matter, small enough that gaming it alone can't
move composite by more than 40%. Reward hacking against deterministic
components is structurally bounded (e.g., gaming sector-vocab-overlap
means inserting field terms, which is the goal anyway).

**Calibration step before ratification:** run the loop with a no-op
mutator (returns the baseline prompt unchanged) over 50 iterations.
Measure variance in composite score. ε for accept must exceed 2σ of
the no-op variance. Without this calibration, the loop accepts noise.

### 5.4 Cost model

Per iteration:
- 5 trace replays × 1 synthesizer dispatch each = 5 dispatches
- 1 rubric scoring dispatch (composite across all 5 traces)
- 6 total LLM calls per iteration

At Hermes-primary ($0 marginal — subscription-attributed) the cost is
zero in steady state. At OpenRouter fallback (DeepSeek-Pro or Claude
Opus 4.7), each iteration is ~$0.01–$0.30 depending on which fallback
fires. **Operator must hard-cap daily spend** (mirror the
`ANTIEK_DAEMON_HOURLY_BUDGET_USD` discipline from continuous-mode).

100 iterations overnight = $1–$30 worst case if Hermes is fully
unavailable. Acceptable. Multi-day extended runs (Karpathy-style 700
iterations) cap at $7–$210 worst case.

### 5.5 Surface: `tools/prompt_autoresearch/`

```
tools/prompt_autoresearch/
├── __init__.py
├── README.md            # operator workflow (mirror tools/golden_traces/README.md style)
├── runner.py            # the main loop
├── score.py             # composite score function + per-component helpers
├── mutator.py           # protocol for proposing changes (the coding agent's surface)
├── budget.py            # cost cap enforcement + iteration cap
└── tests/
    ├── test_score.py    # deterministic component unit tests
    ├── test_runner.py   # loop invariants (rollback fires, version bumps, events emit)
    └── test_calibration.py  # no-op mutator variance bound
```

Estimated LOC: ~600 Python + ~80 of role program.md files.

### 5.6 Operator workflow

1. Operator decides to optimize the synthesizer prompt
2. Operator edits `roles/synthesizer/program.md` with the hypothesis
   they want explored (e.g., "try removing all hedging modifiers in
   thesis-component prose")
3. Operator runs `python -m tools.prompt_autoresearch.runner --role synthesizer --traces 5 --budget-usd 5 --iterations 100`
4. Operator goes to sleep / does other work
5. Operator wakes up, reviews the JSONL event log + the final
   `roles/synthesizer/prompt.py` state, sanity-checks the accepted
   diffs, regression-tests against new traces

**Production VM execution is FORBIDDEN.** Wedge 1 runs only on
operator's local machine until Wedge 2 ratifies. Reason: prompt
mutations can break MASTER.md generation for the live workstation; the
local-only constraint preserves the operator's ability to serve
themselves while experimenting.

### 5.7 Acceptance criteria for wedge promotion

Wedge 1 is considered successful and ratified if:

- ≥1 accepted change produces a verified composite-score improvement
  over baseline that survives evaluation against a hold-out set of
  golden traces the loop did NOT see during the run
- Operator qualitatively endorses the accepted prompt as "this is a
  prompt I would have written if I had time, not a degenerate prompt
  that gamed the judge"
- The composite-score improvement transfers to at least 1 real
  investigation run on the production VM (operator-graded)

If Wedge 1 fails ratification: REJECT the entire integration. The
metric question — Antiek's quality is LLM-judged — was answered
negatively. Wedges 2-4 are unsalvageable in that case.

---

## 6. Wedge 2 — Phase 8 skill-patch accept/reject gate

### 6.1 The defect

Currently Phase 8 (compounding) runs `skill.auto_patch_applied` after
every investigation, unconditionally patching `<domain>/SKILL.md`.
There is no gate. A bad investigation can poison the skill, and the
next investigation that loads the skill inherits the poison.

Researchmaxx had this same defect in `synthesis_to_master.py` (wrote
MASTER.md but didn't patch SKILL.md); Antiek fixed the SKILL.md side
during migration. But the gate question — "should this patch actually
land?" — was never asked.

### 6.2 The autoresearch shape applied here

Currently:
```
synthesizer produces MASTER.md → skill_growth applies patch → done
```

Proposed:
```
synthesizer produces MASTER.md
  → skill_growth proposes patch (candidate diff)
  → replay last K investigations from cohort against patched skill
  → score backtest delta
  → if improved: apply patch (advance baseline)
  → else: discard patch, emit skill_patch_rejected event
```

### 6.3 Why this is Phase 2, not Phase 1

The metric here is the `middleware/backtest/` score across a cohort.
That requires:
- ≥50 investigations in the cohort (enough to make backtest move
  meaningfully)
- `outcomes` table populated with operator-graded outcomes for those
  investigations
- Variance characterized — no-op patches' backtest score variance must
  be bounded enough that ε ≫ noise

None of those preconditions are met at the production VM today (first
real-LLM run was Sprint 10; cumulative cohort is probably <20
investigations). **Wedge 2 cannot ship before the cohort accumulates.**

Sequencing: Wedge 1 ratifies → operator runs real investigations for 4-8
weeks → cohort accumulates → Wedge 2 becomes viable.

### 6.4 Failure mode unique to Wedge 2

Phase 8 is the **compounding** mechanism. Adding a gate that's too
strict means patches never land, and the compounding mechanism stalls.
A gate too loose means poisoned patches land, and the compounding
mechanism poisons itself.

**Required calibration before ratification:** run the gate in
shadow-mode for 10+ investigations — compute the accept/reject
decision but apply the patch regardless. Compare shadow decisions to
operator's manual review of those patches. Tune ε until shadow ≥80%
agrees with operator. THEN flip the gate to enforcing.

---

## 7. Wedge 3 — Context-pack and dispatch config sweeps

### 7.1 What it would do

Sweep:
- `substrate/context_pack/assembler.py` truncation strategies (`smart`
  vs `head` vs `tail`) per role
- Layer priority order (e.g., does `graph_evidence` before
  `long_term_skill` produce better syntheses than after?)
- Per-role tier mapping in `substrate/dispatch/config.yaml` (does
  routing `connector` to `pro` instead of `flash` improve outcomes
  enough to justify cost?)
- Budget allocation per role (does the synthesizer benefit from a 50%
  context budget increase, or does it cause hallucination?)

### 7.2 Why this is DEFER, not PHASE 2

The metric prerequisite is **real trajectory volume from the production
VM with operator-graded outcomes**. The sweep space here is large
(hundreds of config combinations); the signal-per-trajectory is low.

Honest math: with ~20 trajectories accumulated, even a config that
genuinely improves quality by 5% is statistically indistinguishable
from no-op variance. The sweep accepts noise.

Threshold for promoting Wedge 3 from DEFER to active integration:
- ≥500 graded outcomes in the cohort
- Wedge 2 ratified (the backtest scoring infrastructure has been
  proven against real patches)
- Operator explicitly requests the sweep (don't pre-build)

### 7.3 What this becomes long-term

Eventually this is the wedge that produces the largest gains because
the config space is large and human intuition about LLM behavior is
poor. But ordering matters: prompts first (Wedge 1, fast feedback,
single role), patches second (Wedge 2, slower feedback, compounding
mechanism), configs third (Wedge 3, slowest feedback, largest space).

---

## 8. Wedge 4 — Local SFT loop for Loop 3 (DEFERRED behind unlock criteria)

### 8.1 The narrow legitimate use

`loop_3_unlock_criteria.md` already gates RL training. One of the
implementation choices when the gate opens is "what does the local SFT
runner look like?"

Autoresearch's shape is one valid answer:
- `train.py` becomes the SFT trainer (LoRA fine-tune on a held-out
  trajectory subset)
- 5-minute budget per iteration on operator's GPU
- Metric: validation loss on a held-out trajectory subset
- Coding agent proposes hyperparameter changes (LR, batch size, LoRA
  rank, target modules)

### 8.2 Why this is DEFER, not REJECT

Not a category error. Same problem shape autoresearch was built for
(model training, single GPU, deterministic metric). The only reason
it's DEFER is the prerequisite gate (`loop_3_unlock_criteria.md`) is
not met — and won't be met for many sprints.

When the gate opens, revisit. Until then: do not pre-build.

### 8.3 What does NOT defer to Wedge 4

The trajectory harvesting pipeline (Sprint 15 in the RLM integration
spec) and the verifiers environment work (Wedge B in the Prime
Intellect integration spec) are NOT autoresearch dependencies. Build
those on their own schedule.

---

## 9. Explicit rejections (don't re-litigate)

Stated once. The verdicts are settled. Re-open only if the underlying
substrate changes.

### 9.1 REJECT: Rewriting Antiek's investigation loop in autoresearch's shape

The investigation loop is multi-phase, multi-role, multi-provider,
operator-graded over weeks or months. Reducing it to a 5-min train +
single-scalar metric throws away every property that makes Antiek
defensible. Stated in §2 above. Not negotiable.

### 9.2 REJECT: Using autoresearch as a dispatch substrate

Autoresearch's runtime is single-process. Antiek's dispatch is multi-
provider with fallback chain (Hermes primary, OpenRouter fallback,
Whisper for transcription). The Hermes-primary posture is locked
(`integration_hermes_bridge` memory). Routing through autoresearch
would require:
- Building multi-provider routing into autoresearch (rebuild what
  `substrate/dispatch/` already does)
- Wiring the verifier-fallback invariant (`tests/test_dispatch_fallback_chain.py`)
  through autoresearch (rebuild what's already chaos-tested)
- Maintaining two dispatch paths

Net loss. The Hermes bridge spec already governs how Antiek talks to
LLMs.

### 9.3 REJECT: Publishing Antiek role prompts as a `train.py`-style "one file the world copies"

Antiek's IP is the substrate plus the compounding graph plus the
voice-and-style discipline plus the accumulated golden traces. Role
prompts are the only piece a competitor could copy in a quarter.
Publishing them is asymmetric reversal — same logic as the Prime
Intellect Hub rejection (`integration_prime_intellect §5`).

### 9.4 REJECT: Treating autoresearch's "100 experiments overnight" cadence as the target

Autoresearch's cadence is set by a 5-min training run on a single GPU.
Antiek's iteration cost is N LLM dispatches per iteration. The
operator's budget tolerance is the binding constraint, not throughput.
The right target is "the maximum cadence that keeps the daily spend
under cap," not "match Karpathy's 100/night."

### 9.5 REJECT: Adopting autoresearch's git-commit-per-accepted-change pattern at the substrate level

Antiek already has `ANTIEK_PARAM_VERSION` discipline (master-product-spec
§3.1). Adding git commits per prompt mutation runs the risk of polluting
the substrate history with hundreds of low-value commits. Use the event
log + `ANTIEK_PARAM_VERSION` bumps as the version-of-record. Wedge 1's
runner can keep its own per-iteration git branches inside
`tools/prompt_autoresearch/` for operator review, but those don't merge
to substrate history.

---

## 10. Risks and mitigations

### 10.1 Reward hacking against LLM judges

**Risk:** the highest-impact failure mode. If the rubric scorer is
also an LLM, a prompt mutator can learn to game the judge —
producing outputs that score high but degrade real quality.

**Mitigations baked into the wedge designs:**
- Composite score (Wedge 1 §5.3): 60% of the score is deterministic.
  Reward hacking against deterministic components is bounded (and
  often aligned with the goal).
- Hold-out trace set (Wedge 1 §5.7): accepted prompts must improve on
  traces the loop didn't see.
- Operator qualitative endorsement (Wedge 1 §5.7): the operator reads
  the accepted prompt and rejects "degenerate prompts that gamed the
  judge."
- Shadow mode before enforcing (Wedge 2 §6.4).
- Multi-judge rubric (future): score the same output with 2-3
  different judge prompts; require agreement.

### 10.2 Cost runaway

**Risk:** same shape as the daemon chase mode in master-product-spec
§7.4.

**Mitigation:**
- Hard cap per iteration ($0.30 worst case)
- Hard cap per run ($5 default, configurable upward)
- Hermes-primary routing means most iterations are $0 marginal in steady
  state; OpenRouter fallback only fires on bridge outage
- Local-only execution for Wedge 1 (no production VM cost)

### 10.3 Compounding loop integrity

**Risk:** Antiek's Phase 8 already feeds back into skills. Wedge 1's
prompt mutation feeds back into role prompts. Wedge 2 adds a gate to
Phase 8 itself. Three feedback loops interacting.

**Mitigation:**
- Versioned artifacts (`ANTIEK_PARAM_VERSION`) make rollback always
  available
- Event log captures every accept/reject decision with the candidate
  diff and judge invocation IDs — full auditability
- Wedges sequence strictly: Wedge 1 ratifies before Wedge 2 starts;
  Wedge 2 ratifies before Wedge 3 starts
- Operator-graded outcomes remain the ground truth; LLM-judged
  metrics are intermediate signals, not authoritative

### 10.4 Calibration debt

**Risk:** the no-op variance bound (Wedge 1 §5.3) and the shadow-mode
threshold (Wedge 2 §6.4) are calibration steps that take real wall-clock
time. Skipping them lets the loops accept noise.

**Mitigation:** make calibration a hard prerequisite. Code refuses to
enter enforcing mode without a calibration run on file. Mirror the
discipline of `tools/golden_traces/` (the calibration run is itself a
golden trace).

### 10.5 Premature generalization

**Risk:** the operator (or a future agent) sees Wedge 1 working and
generalizes the loop to surfaces where the metric isn't tight. Wedges
2 and 3 both have this temptation.

**Mitigation:** wedge-specific unlock criteria (§11 below). Each wedge
has a metric-readiness gate that must close before promotion.

### 10.6 The Lutke gap

**Risk:** Lutke's Shopify success was on a deterministic metric (render
time). Antiek's metrics are LLM-judged. There is **no published evidence
yet** that autoresearch's mechanic survives the deterministic-to-judged
transition. Wedge 1 is essentially the first defensible test.

**Mitigation:** Wedge 1's acceptance criteria (§5.7) treat this as the
explicit ratification question. If Wedge 1 fails, the entire integration
falls — and that's the honest answer rather than salvaging by lowering
the bar.

---

## 11. Unlock criteria for promoting wedges

Each wedge has explicit gates. Crossing them is the ratification
event; the spec is amended when each unlocks.

### 11.1 Wedge 1 (prompt autoresearch) unlock criteria

- [ ] `roles/synthesizer/program.md` written and operator-reviewed
- [ ] `tools/prompt_autoresearch/` scaffolded (~600 LOC Python)
- [ ] No-op mutator calibration run on file; ε for accept > 2σ no-op variance
- [ ] ≥5 golden traces of synthesizer behavior captured (operator may
      need to capture more — current count is 1 synthetic)
- [ ] Cost cap of $5/run enforced in code
- [ ] Production VM execution forbidden in code (raises if
      `ANTIEK_ENV=production`)

Once all six closed: Wedge 1 promoted to active integration. Run the
first 100-iteration overnight loop on operator's local machine.

### 11.2 Wedge 2 (Phase 8 gate) unlock criteria

- [ ] Wedge 1 ratified (per §5.7 acceptance criteria)
- [ ] ≥50 investigations accumulated on the production VM
- [ ] `outcomes` table populated with operator-graded outcomes for
      those investigations
- [ ] Backtest score variance characterized on a no-op patch baseline
- [ ] Shadow-mode infrastructure shipped (compute decision but apply
      patch regardless, log both)

### 11.3 Wedge 3 (config sweeps) unlock criteria

- [ ] Wedge 2 ratified
- [ ] ≥500 graded outcomes in the cohort
- [ ] Operator explicitly requests the sweep — DO NOT pre-build

### 11.4 Wedge 4 (local SFT) unlock criteria

- [ ] `loop_3_unlock_criteria.md` fully satisfied (all five criteria
      checked off in that doc)
- [ ] At that point, autoresearch's shape considered vs alternatives
      (e.g., `prime rl run`, Verifiers env training)

---

## 12. Sprint placement

Aligning to the current sprint sequence (master-product-spec §14).

| Sprint | Theme | Autoresearch work |
|---|---|---|
| **17** | Interview voice mode | **INTEGRATE NOW item:** add `program.md` to each role module (half-day hygiene) |
| **18** | Publisher dashboard + Synquery | None — full slate |
| **19** | Multi-user accounts (start) | **Wedge 1 starts as parallel side-track** — scaffolding `tools/prompt_autoresearch/`, calibration run, first 100-iteration overnight |
| **20** | Multi-user / payouts | Wedge 1 ratifies or REJECTs the whole integration. If ratifies, **Wedge 2 shadow-mode starts** |
| **21-22** | Phase 4 ad inventory | Wedge 2 calibration completes; flip to enforcing mode |
| **23+** | Scale | **Wedge 3** if and only if §11.3 criteria met |
| **Whenever Loop 3 unlocks** | RL training | **Wedge 4** considered against alternatives |

**Critical: Wedge 1 runs as a parallel side-track, not on the main
sprint critical path.** The mainline build remains the operator's
priority (Sprints 17-18 are full; Sprint 19+ has multi-user as the
main work). Wedge 1 happens in spare cycles on operator's local
machine.

---

## 13. Open questions (genuinely unresolved)

These are the questions this spec does NOT settle. They become real at
the inflection points flagged.

### 13.1 Does autoresearch's mechanic survive the deterministic-to-LLM-judged transition?

The Lutke gap from §10.6. The answer determines whether Wedge 1
ratifies or REJECTs. There is no way to answer this in advance — the
Wedge 1 acceptance criteria ARE the test.

### 13.2 What is the right ε for each composite-score component?

The Wedge 1 design picks weights (0.40 / 0.30 / 0.20 / 0.10) by intuition.
The calibration run will tell whether those weights produce a discriminating
metric. May need rebalancing — e.g., if rubric scores are noisier than
expected, the LLM-judged weight may need to drop to 0.20.

### 13.3 Is `tools/prompt_autoresearch/` the right module location?

Alternative: `compounding/prompt_autoresearch/` (treating it as a
compounding mechanism alongside skill_growth). Argument for `tools/`:
it's an operator tool, not a runtime substrate component. Argument for
`compounding/`: when Wedge 2 ratifies, it IS a runtime compounding
mechanism.

**Recommended:** start in `tools/` for Wedge 1; move to
`compounding/prompt_autoresearch/` if Wedge 2 ratifies. The move is
cheap (it's pure Python with no other-module dependencies); the
distinction signals operator-tool vs substrate-mechanism.

### 13.4 Should the coding agent driving the outer loop be Claude Code (current dev tool) or a separate scriptable agent?

Karpathy's docs are agnostic — he uses Claude Code himself. For Antiek,
the question is: does the loop run as Claude Code launched by the
operator (interactive), or as a daemon Python process invoking an LLM
directly (autonomous)?

**Recommended (deferred decision):** start with Claude Code launched
by operator (Sprint 19 Wedge 1 starting form). If wedge ratifies and
operator wants overnight cadence, productionize as a daemon in a later
sprint. Don't over-engineer the runner before the metric question is
answered.

### 13.5 Is autoresearch's MIT license clean for Antiek's usage?

MIT is permissive — no copyleft, no patent grant restrictions. **No
license issue for the integration.** This is a non-blocker but worth
naming explicitly: the spec doesn't propose vendoring autoresearch
code into Antiek; it proposes adopting autoresearch's *architectural
patterns* (the propose-execute-measure-gate loop). No code copy
required, no attribution obligation triggered.

If a future implementation does vendor `prepare.py`/`train.py` style
scaffolding (Wedge 4 only), MIT permits it with attribution in the
header. Acceptable.

---

## 14. What to do now

**Nothing on the mainline sprint critical path through Sprint 18.**

The one ratifiable INTEGRATE NOW item: add `program.md` to each role
module during Sprint 17 substrate-side hygiene work. Half a day. Pure
upside — codifies what operator is already doing manually, becomes the
mutation surface when Wedge 1 starts.

When Sprint 19 starts and multi-user work is on the main path:
operator may run Wedge 1 as a parallel side-track on local machine.
Scaffolding `tools/prompt_autoresearch/` is ~600 LOC, calibration run
is overnight, first real run is overnight after that. By Sprint 20
there is a ratify-or-REJECT verdict on the whole integration.

If REJECT: the integration ends here. Wedges 2-4 fall. The Antiek
substrate continues unchanged. The operator absorbs the autoresearch
philosophical influence (`program.md` discipline already shipped from
Sprint 17) without the loop machinery.

If RATIFY: Wedges 2-4 sequence through their own unlock criteria.

This is the discipline: a one-day INTEGRATE NOW commitment, a clear
ratification gate two sprints out, four wedges each with their own
defensible gate. No commitment beyond Sprint 17 until the operator
sees a real metric movement on Wedge 1.

---

## Final note for the implementing agent

Precedence order when this spec conflicts with another:

1. `architecture_notes.md` — substrate-level commitments (load-bearing;
   never violate)
2. `loop_3_unlock_criteria.md` — Wedge 4 cannot fire before this gate
   passes
3. `master-product-spec.md` — product vision + sprint sequencing
4. This spec — autoresearch integration verdicts and wedge mechanics
5. `integration_prime_intellect.md`, `integration_autoresearch.md`,
   `daytona_integration_spec.md`, `rlm_integration_spec.md` — peer
   integration specs; conflicts resolved by operator review

If precedence (1) and this spec ever conflict, the substrate wins.
Autoresearch's whole point is that the substrate (`prepare.py`) is
frozen. Antiek's whole point is the substrate is the moat. Same
discipline; never substitute the substrate to fit the autoresearch
shape.

The wedges in §5-§8 are the integration. The rejections in §9 are the
guardrails. The unlock criteria in §11 are the ratchet. The verdict
on the whole integration lands by end of Sprint 20.

Until then: keep building Antiek. The autoresearch literature reads
well; the actual Antiek-level value is bounded by whether Wedge 1
moves a hold-out metric. Find out — don't presume.

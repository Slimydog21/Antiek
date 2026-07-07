# Groundedness eval — promote-to-gate criterion

**Status:** observability-only (NON-blocking). This document is the
written, dated, falsifiable condition under which the groundedness signal
flips to **merge-blocking**. The flip itself happens in a LATER sprint —
this sprint (Foundation v2 SPR-02) only ships the signal and the criterion.

**Authored:** 2026-05-29 (Foundation v2 SPR-02).
**Owner:** the eval substrate (`substrate/eval/groundedness/`).

---

## Why this exists (validate-before-gate)

You cannot build a trustworthy gate on top of an unvalidated metric, and
you cannot validate a metric whose signal you are silently throwing away.
SPR-02 stopped the swallow and built the truth-axis scorer; it ships the
scorer as a NON-blocking signal because, at authoring time, **zero
validated groundedness traces existed on disk**. Gating a brand-new,
unvalidated eval would be its own fake-green. So the gate is deferred
behind a concrete, mechanically-checkable bar.

The **rejected** alternative — "promote when it looks good" — is not
defensible and is explicitly out. The bar below is numeric and a reader
can decide it mechanically from harness output.

## The criterion

The groundedness signal flips from NON-blocking to **merge-blocking** when
ALL of the following hold, measured by
`python -m substrate.eval.groundedness.harness --labeled <set> --json`:

1. **Minimum labeled cases: N = 40** total hand-labeled claims, of which
   **at least N_hallucinated = 15 are genuine hallucinations** (and at
   least 15 faithful). The harness already refuses a set with zero
   negatives; this raises the floor so the separation statistic is not
   computed on a toy set.

2. **Separation threshold: rank-AUC ≥ 0.85** on that labeled set
   (`labeled.auc` in the harness JSON). Equivalently, the secondary
   guards must also hold: **mean_gap ≥ 0.30** (`labeled.mean_gap`) and
   **threshold_accuracy ≥ 0.85** (`labeled.threshold_accuracy`) at the
   scorer's `supported_threshold` (currently 0.50,
   `DEFAULT_SUPPORTED_THRESHOLD`).

3. **The labeled set is checked in** alongside the harness
   (`tests/fixtures/groundedness_labeled.jsonl`) and includes the
   densely-cited-hallucination class (a high-citation-density claim that
   fails entailment) — the case a citation_density gate would get wrong.

4. **The signal has run NON-blocking on real Phase-6 traces** for at
   least 2 weeks with the failure-event rate (`groundedness.failed`)
   below 1% of scored syntheses — i.e. the scorer is operationally stable
   on the live path, not just on fixtures.

When all four hold, a follow-up sprint may add the CI gate (e.g. a
`groundedness` check in `.github/`/`ci/` that fails a merge when
`labeled.auc < 0.85` or a regression set regresses). Until then, the
signal stays observability-only.

## How to mechanically check it

```
python -m substrate.eval.groundedness.harness \
    --labeled tests/fixtures/groundedness_labeled.jsonl --json
```

Read the `labeled` block of the JSON. The criterion is MET iff:

- `n_faithful + n_hallucinated >= 40` and `n_hallucinated >= 15`, AND
- `auc >= 0.85`, AND
- `mean_gap >= 0.30`, AND
- `threshold_accuracy >= 0.85`.

A reader can decide met/not-met from those four comparisons alone — no
judgment call, no "looks good".

## Current standing (2026-05-29, authoring set)

On the 10-case bootstrap set checked in this sprint
(`tests/fixtures/groundedness_labeled.jsonl`: 5 faithful / 5 hallucinated)
the harness reports `auc = 1.000`, `mean_gap ≈ 0.77`,
`threshold_accuracy = 1.000`. The **separation bar is already cleared on
this set**, but the **N bar is NOT** (N = 10 < 40, N_hallucinated = 5 < 15)
and **criterion 4 (live-trace stability) is unmet** — so the signal
correctly remains NON-blocking. Expanding the labeled set to N = 40 with
N_hallucinated ≥ 15 and accruing 2 weeks of live `groundedness.scored`
traces is the work that earns the gate.

## SPR-01 standing note (2026-07-05) — the lexical backend FAILS the bar on the hard set

The labeled set was expanded to **N = 43** (16 faithful / 27 hallucinated,
**12 of the densely-cited-hallucination class**) — criterions 1 and 3 are
now MET. The criterion-2 verdict, measured honestly on the default lexical
backend (post-adversarial-review numbers):

- `auc = 0.907` — **CLEARS** `0.85`
- `mean_gap = 0.351` — **CLEARS** `0.30`
- `threshold_accuracy = 0.674` — **FAILS** `0.85`

The lexical backend clears the *separation* statistics (auc, mean_gap) but
**fails the classification bar** once the densely-cited class is included:
**11 of 12 `hallu-dch-*` hallucinations score above threshold (0.57–0.80)**,
slipping past the gate as false positives. This is the precise blind spot
the criterion-3 class was designed to expose — a hallucination that keeps
the same polarity and asserts only numbers present in the evidence yet is
false via a subject-swap (mRNA/siRNA), causal lift (correlation→causation,
measurement-method→cause), unsupported superlative, unit-class confusion
(milli/micro), aggregation error (per-turbine vs combined), dropped
precondition/qualifier, or composition fallacy (cell→pack). Token-overlap
cannot see any of those; all are documented LLM synthesis failure modes.

**This is the load-bearing justification for SPR-02** (a CI-safe entailment
backend). The cheap lexical proxy is observability-grade, not gate-grade;
promoting it to merge-blocking on these numbers would be the exact fake-green
this document forbids. The bar-check test
(`tests/test_groundedness_promote_bar.py`) encodes this finding as a strict
`xfail` on the threshold_accuracy leg plus a regression guard that fails if
the gap closes without a real entailment backend landing.

The finding survived a heterogeneous adversarial review (separate judging
lineage, default-to-refuted, 8 claims checked against the machine):
**7 SOUND / 0 REFUTED / 1 UNCERTAIN (generalization strength, since
addressed)**. The reviewer's load-bearing observation: the threshold_accuracy
finding is robust to **7 simultaneous label-flips** before the bar would be
met — no single or small-cluster mislabel can manufacture the gap.

Criterion 4 (2 weeks of live `groundedness.failed` < 1%) remains unmet and
is unchanged by this sprint. The signal stays NON-blocking.

## SPR-02 standing note (2026-07-05) — the NLI backend CLEARS the bar lexical failed

A deterministic, CI-safe entailment backend landed:
`substrate/eval/groundedness/nli_backend.py::nli_entailment_score` — a
DeBERTa-v3-base NLI cross-encoder (`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`,
pinned) wrapped to match `EntailmentBackend`. It is selectable via
`backend=` / `--backend nli` and is exercised by the bar check.

Head-to-head on the SPR-01 hard set (N=43; 13 densely-cited-tagged cases:
the 12 `hallu-dch-*` expansion cases + the original `hallu-densely-cited-lie`):

| metric | lexical | NLI |
|---|---|---|
| auc | 0.907 | 0.905 |
| mean_gap | 0.351 | **0.754** |
| threshold_accuracy | 0.674 (FAIL) | **0.884 (PASS)** |
| densely-cited caught — `hallu-dch-*` subset (n=12) | 1/12 | **9/12** |
| densely-cited caught — all dense-tagged (n=13) | 2/13 | **10/13** |

(Catch counts reported under both subset definitions — an earlier "10/12"
framing conflated them; the advantage is real and large under either honest
recount.)

NLI **clears criterion 2** on the hard set (criterion 1 + 3 were already met
by SPR-01). The densely-cited blind spot — the class lexical is structurally
blind to — is closed for 9 of 12 `hallu-dch-*` cases. **Honest residual**:
NLI still misses 3 "true-but-misleading" cases (correlation→causation,
temporal-shift, conditional-flatten) whose surface claim is mostly entailed;
their falsehood is the dropped qualifier, not the surface tokens. Pinned by
`test_nli_backend_residual_misses_are_documented_not_hidden` so a change is
forced to acknowledge it.

**Determinism** is a tested property, not a hope: `test_nli_backend_deterministic`
asserts byte-identical `(score, rationale)` across two runs (fixed weights,
eval/no-grad, no sampling).

**CI-safety**: inference makes no outbound call (the model is a local HF
cache). The dependency (torch/transformers/sentence-transformers) is already
an Antiek optional extra (`embedding`), so no new heavyweight dep. The
NLI tests skip LOUDLY (named, not silent) when the model isn't cached, so
the default CI path stays green without the ML extra.

**Default-promotion decision (NOT promoted to the live scoring default).**
NLI clears the labeled-set bar but `DEFAULT_SCORER_ID` and the `backend=`
defaults in `score_claim`/`score_synthesis_groundedness` are KEPT on lexical.
Two reasons, both load-bearing:

1. **Criterion 4 is still unmet.** Flipping the production default would
   change live Phase-6 behavior (every synthesis would load a ~440MB model)
   before 2 weeks of live `groundedness.failed < 1%` evidence exists. That
   is the exact fake-green this document forbids. The live-default flip is
   SPR-03 territory, behind the activation flag + criterion 4.
2. **Two backends, two roles, nothing swappable-without-loss.** Lexical is
   the cheap, dependency-free, instant *observability* scorer (its job);
   NLI is the deterministic *gate-grade* scorer (its job). Promoting NLI to
   the default would couple the observability path to the ML stack for no
   gain until the gate actually flips.

The bar check now runs against BOTH backends:
`test_promote_bar_lexical_finds_the_gap` (lexical fails — the documented
gap) and `test_promote_bar_nli_clears_criterion2_threshold_accuracy` (NLI
clears). The relationship is locked in CI.

Criterion 4 (live-trace stability) remains the only unmet criterion. The
signal stays NON-blocking until it + the SPR-03 activation flag land.

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

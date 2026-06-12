# Egghead tribunal — Cycle 2 DRW execution thesis

**Date:** 2026-06-12  
**Thesis:** Ship → Parallel prod → 10 operator DRWs → engineer only where pain clusters.  
**Tribunal:** 3 blind lenses + self-refute (contract-injected).  
**Contract length:** ~1,700 chars (validated ≥500).

## Verdict

**`loop-full-cycle`** — **moderate confidence.**

Dogfood is the right *north star*, but the naive schedule (**ship → parallel prod → 10 sessions → then engineering**) **breaks** on base-rate and incentives. A **narrow engineering slice (SPR-DRL-09 + parent-terminal observability) must precede trusted prod dogfood**, while **operator gate work (G2 counsel) runs in parallel** — not after ten DRW rituals.

## Panel results

| Lens | Verdict | Confidence | Strongest break |
|------|---------|------------|-----------------|
| empirical/falsifiability | **dents-it** | moderate | Parent lacks `investigation.completed` while leaves terminal; swallowed synthesis-tail exceptions |
| base-rate/outside-view | **breaks-the-thesis** | moderate | Prod gather before sovereign dogfood → session 1–3 churn; pain never clusters |
| incentives/who-benefits | **breaks-the-thesis** | high | "10 DRWs" substitutes for G2 counsel; agents relabel engineering as "failure logging" |
| self-refute (lead counter) | **breaks-the-thesis** | moderate | SPR-DRL-09-before-dogfood veto **refuted** — P-16 operator column exists for live proof |

**Dissent:** empirical **dents** vs base-rate/incentives **break**; self-refute rejects sequencing veto but empirical demands instrumentation.

## Survivors (binding for Cycle 2)

1. **Path A substrate is real** — convergence tests, P-11..P-16 green, Parallel mock E2E shipped.
2. **Operator proof is mandatory** — hermetic CI cannot close Parallel index, legal gate, ingest latency.
3. **SPR-DRL-09 is not optional theater** — pack `doc-url-*` fidelity + HTTP cascade path must be gated before *trusting* prod outcomes (empirical + steelman alignment).
4. **Parent terminal ≠ leaf terminal** — dogfood checklist must verify `investigation.completed` on session parent; `_run_to_completion` swallow risk is real.
5. **10 DRWs ≠ activation** — G2 counsel dispatch is the binding calendar competitor; DRWs are subordinate experiments, not gate substitutes.
6. **PRcrouch is not done** — `bfed09d` local only; cycle-1 `done-no-ship` stands until merge.

## Rejected after tribunal

- Pure dogfood-first with zero pre-smoke engineering
- Pure engineering-first (more htmlspec waves) without operator sessions
- "10 sessions" as primary milestone before G2 + one instrumented smoke DRW

## Cycle 2 execution DAG

```
Tier A (engineering, ~1–2 days)
  SPR-DRL-09: HTTP/pack E2E — mocked Parallel + ingest → doc-url-* in pack
  Parent-terminal observability: synthesis-tail failure visible; operator checklist doc
  Refresh state.json / cycle-state (SPR-DRL-08 done, Parallel-first)

Tier B (ship, parallel)
  PRcrouch: bfed09d + Parallel + P-16 → main
  Prod: ANTIEK_DRW_GATHER=parallel, rotate PARALLEL_API_KEY

Tier C (operator, gated)
  G2: send counsel packet (parallel track, not blocked by DRW)
  Smoke DRW #1 with tribunal checklist (parent complete, pack doc ids, synthesis grade)
  If smoke green → sessions 2–10; else regression YAML before more sessions

Tier D (next cycle input)
  htmlspec-2 only if smoke surfaces clustered failure modes
```

## What would change the verdict

| Observation | Effect |
|-------------|--------|
| Smoke DRW #1 reaches parent `investigation.completed` with ≥1 `doc-url-*` chunk | Upgrade to `proceed-prcrouch` + accelerated dogfood |
| Smoke shows placeholder pack + silent synthesis fail | P0 — halt dogfood batch, fix observability + pack bridge |
| G2 closed + smoke green | `proceed-prcrouch` with memento |

## Residual uncertainty

| Claim | Confidence |
|-------|------------|
| Swallowed synthesis-tail is prod-visible today | moderate (code path exists; not operator-measured) |
| Parallel index fit for operator queries | low |
| 10-session cohort achievable before G7 | moderate |
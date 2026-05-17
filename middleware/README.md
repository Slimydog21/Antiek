# middleware/

Cross-cutting concerns that sit between roles and the substrate. Each
middleware module enforces a policy that's expensive to embed in every
role.

## Modules

- **`constraint_check/`** — Pre-flight + deterministic + LLM-qualitative
  checks. Pre-flight validates schema. Deterministic applies hard rules
  (date ranges, numeric bounds, required citations). LLM-qualitative
  applies judged rubrics. A constraint fail emits a `fail_constraint`
  event; downstream code reads the failure rather than retrying blindly.
- **`source_tier/`** — Rule-based tier assignment. The LLM may adjust
  DOWNWARD only — it can argue a source is *less* reliable than the
  rules say, never *more*. This asymmetry is by design; see
  architecture_notes §4.
- **`temporal/`** — Point-in-time queries, staleness, supersession.
  TTL per claim class lives in `constants.py`. Market data ages in
  days; biographical facts age in decades. When a claim's TTL expires,
  the temporal layer marks it stale and the synthesizer hedges
  accordingly.
- **`archive/`** — Synthesis archival with version stamping. Records
  the full skill-version triple (domain, process, verification) plus
  `ANTIEK_PARAM_VERSION` at the time of synthesis. Backtests against
  archived syntheses correlate parameter versions to outcomes.
- **`backtest/`** — Cohort evaluation against outcomes. Pulls archived
  syntheses produced under specific parameter and skill versions,
  joins them against realized outcomes (where known), produces the
  per-skill-version quality metric referenced in the hardware-decision
  criteria.

## Discipline

Middleware never mutates state silently. Every policy decision emits a
typed event so the audit layer can reconstruct what happened.

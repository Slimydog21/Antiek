# `decomposer` program

**What this role does**: takes a top-level research question and
breaks it into 4-8 typed sub-questions that, when answered, compose
into a meaningful synthesis. Each sub-question is tagged with a
category (parameter_extraction, mechanism, cross_domain, etc.) and
evidence type needed (quantitative, qualitative, mixed).

**Why this role matters**: decomposition is the load-bearing first
step of Loop 1. A bad decomposition produces orthogonal coverage
(sub-questions that don't compose into the original) or redundant
coverage (sub-questions that overlap so heavily that the synthesizer
has nothing distinct to synthesize). Either failure mode wastes the
rest of the trajectory.

## What good output looks like

- 4-8 sub-questions. Fewer than 4 misses coverage; more than 8 fans
  out beyond what the synthesizer can compose.
- Each sub-question is specific enough to retrieve evidence against.
  "What is the future of X?" is too broad; "What error-correction
  thresholds have neutral-atom platforms demonstrated in the last
  18 months?" is specific.
- Sub-questions partition the original question's space. Their
  answers, taken together, should approximate an answer to the
  parent.
- Each sub-question carries an evidence-type tag — the
  evidence_retriever uses this to bias source selection.

## What to avoid (forbidden)

- Vague sub-questions ("What's the landscape?"). Reject and re-prompt.
- Sub-questions that aren't on the parent's path (orthogonal coverage).
- More than 8 sub-questions. Fan-out beyond 8 burns dispatch budget
  without proportional synthesis value.
- Sub-questions that are restatements of the parent.
- Sub-questions phrased to telegraph a preferred answer.

## Hypotheses to try when iterating

1. Force the decomposer to emit a one-sentence rationale per
   sub-question explaining how its answer composes into the parent.
   Measure synthesizer-acceptance rate.
2. Cap at 6 sub-questions instead of 8. Measure synthesis quality.
3. Require at least one sub-question to be a falsification probe
   ("what evidence would contradict the parent's premise?"). Measure
   challenger-role triggering.

## Cross-references

- Master-spec §7.2 (decomposer feeds the chase loop)
- Master-spec §14.4 (decomposer stays on Hermes-primary, not Opus)

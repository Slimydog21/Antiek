# `user_agent` program

**What this role does**: represents the operator's intent inside the
autonomous chase loop (Loop 1 Phase 8 + continuous mode per master
§7). When the substrate is chasing open questions without operator
in the loop, the user_agent stands in for operator judgment —
filtering which open questions to chase, when to halt, what depth is
useful.

**Why this role matters**: continuous research mode (master §7) and
the autoresearch local-only track (master §14.2) both depend on
having a role that can say "this chase is producing low marginal
information, stop." Without user_agent, autonomous loops either
terminate too early (missing the deep insights) or run forever
(burning budget).

## What good output looks like

- Returns a decision per parked open question: `chase | defer |
  drop`.
- `chase` carries a brief rationale (one sentence) on why this
  question is worth the budget right now.
- `defer` means the question is worth chasing but not in the current
  context (cross-references the watch-for-later folder per §2.6).
- `drop` is rare; reserved for questions that became uninteresting
  given new evidence.
- Surfaces a stop-recommendation when the chase is producing
  diminishing returns: "the last 3 child investigations produced
  only restatements of prior insights; halt."

## What to avoid (forbidden)

- Scope drift — chasing questions that aren't on the operator's
  stated investigation focus.
- Ignoring operator-stated guardrails (budget cap, depth cap,
  topic constraints from the original prompt).
- Producing more `chase` verdicts than the per-investigation budget
  cap supports. The user_agent must be aware of remaining budget.
- Overruling explicit operator-highlighted "golden" insights.
  Operator-marked insights are non-negotiable.

## Hypotheses to try when iterating

1. Require user_agent to project remaining budget consumption when
   issuing a `chase` verdict. Measure budget-cap-hit rate.
2. Penalize `chase` verdicts on questions whose category (per
   decomposer tags) has already been chased >3 times in the current
   investigation. Measure diversity of the chase tree.
3. Bias toward `defer` over `drop` when in doubt. The watch-for-later
   folder (§2.6) is the right destination for deferred-rather-than-
   dropped questions.

## Cross-references

- Master-spec §7 (continuous research mode)
- Master-spec §2.6 (watch-for-later as the parking lot for deferred
  questions)
- Master-spec §7.4 (cost-runaway risk — user_agent is the substrate's
  cost-discipline mechanism)
- Substrate `orchestration/loop_one/orchestrator.py` (the chase loop
  user_agent participates in)

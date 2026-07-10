# Antiek-bench live measured wedge

**Status:** code implemented and locally verified; live smoke not yet operator-executed  
**Date:** 2026-07-10  
**Authority:** operator remains the only model/suite promotion authority

## Decision

Antiek may run a bounded, fallback-free comparison of exactly two explicitly
configured models over two items in each canonical task class. Results are
advisory evidence. The runner, weekly verdict, and NotDiamond shadow must never
install a driver, activate a suite rewrite, or alter production routing.

The current score is explicitly `keyword_proxy_quality`. It is useful for
validating measurement plumbing, availability, latency, cost, and replay. It is
not sufficient evidence for model promotion because keyword overlap is not
judged answer quality.

## Live smoke gate

The manual smoke remains disabled unless all of these are true:

1. `ANTIEK_BENCH_LIVE_SMOKE=1` and `CI` is false.
2. Exactly two distinct provider/model pairs have verified positive prices.
3. Worst-case reservations fit an explicitly approved cap no greater than
   `$0.10`; each call is bounded to at most 30 seconds and 128 output tokens.
4. The append-only journal path is retained with the resulting receipt IDs.

No scheduler is installed. The smoke must be initiated by the operator.

## NotDiamond reconsider-if

NotDiamond remains shadow-only. Custom routing or promotion may be reconsidered
only after all of the following hold:

- At least two consecutive operator-ratified complete benchmark weeks.
- At least 30 successful, judged outcomes per candidate and task class.
- A versioned quality judge has replaced keyword overlap, with visible verifier
  disagreement and no truncated class winners.
- The shadow recommendation improves cost per acceptable answer by at least 10%
  while maintaining at least 95% availability in both `research_question` and
  `reading_highlight`-equivalent task cohorts.
- Recommendation disagreement is audited and at most 20% on the promotion set.
- The operator explicitly unlocks G8 and approves the candidate/suite change.

Agreement is not correctness, and disagreement is not failure. These thresholds
only permit reconsideration; they do not trigger an automatic change.

## Rejected

- Normal router fallback during measurement: contaminates model attribution.
- Automatic suite/model promotion: removes the operator stopping condition.
- NotDiamond-owned execution: violates Antiek's dispatch authority boundary.
- Treating the manual smoke as quality evidence: it proves wiring only.

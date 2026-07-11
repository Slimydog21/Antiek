# SPR-04 frozen-file wiring

SPR-04 is additive inside `substrate/citation_binding/`. No production call
site is changed here. Adoption owners should make these changes together so a
report cannot be marked done on one path while bypassing the gate on another.

## `orchestration/loop_one/orchestrator.py` — `_run_phase_6`

Have synthesis emit report text plus an explicit mapping from segmented claim
offsets to the exact `ExtractiveSpan` objects supplied by SPR-03. Call
`bind_report`, retain its `AnnotatedReport`, then call `gate_report` before the
phase can publish a done outcome. A blocked result must preserve `reason` and
`unsupported_claims` in the trajectory. Project the accepted object with
`citation_binding.project_to_html` for the human view.

## `orchestration/cascade_session.py` — `CascadeSession.run_synthesis_tail`

Pass the SPR-03 spans and synthesis binding plan through the cascade tail and
apply the same bind → gate → project sequence. Do not reconstruct spans from
rendered context or URLs: binding depends on exact span identity and verbatim
text.

## unattended / Midnight Oil completion owner

At the call site that changes an unattended investigation to done, invoke
`gate_report(..., unattended=True)` with the W0-pinned judge. Never expose or
set `enforce=False`; the API refuses that bypass. Persist typed `Blocked`
outcomes rather than converting them to successful completion.

## Policy and deferred work

- The 0.90 support threshold is a doctrine/FACT hypothesis. Performance on at
  least 20 real reports is **NOT MEASURED**; W0 owns calibration and the pinned
  independent judge.
- Post-hoc CitationAgent binding is deferred to doctrine L5. It can produce the
  same explicit offset-to-`ExtractiveSpan` plan consumed by `bind_report`.
- Assembly-time binding costs the writer offset bookkeeping, but makes wrong or
  guessed provenance unrepresentable. Post-hoc binding could improve prose and
  decouple bookkeeping at scale; adopt it only after the planned A/B shows it
  preserves exact-span support.

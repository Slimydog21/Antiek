# G5 follow-up — what the verdict surfaced (2026-05-23)

The Sprint-17 dispatch tier-differentiation measurement gate
(§14.4) was supposed to compare Opus-on-synthesis vs Grok-on-
synthesis verifier pass rates and produce a flip-back-or-stay
decision by Sprint 20.

The analyzer ran against the production event log on 2026-05-23
and returned `insufficient_data`. See
`docs/decisions/dispatch-tier-verdict.md` for the raw report. The
table:

| Provider | Model | Synthesis calls | Verified | Passed |
|---|---|---|---|---|
| hermes-grok | grok-4.3 | 14 | 0 | 0 |
| openrouter | anthropic/claude-opus-4.7 | 2 | 0 | 0 |

## What this actually tells us

Two findings, in order of importance:

### 1. The Opus-primary measurement window never produced enough volume

The spec's measurement protocol assumed two weeks of live traffic
under Opus-primary would accumulate ≥10 verified syntheses per
provider. Production data shows the operator has run only **16
synthesis-tier calls total** in the entire event log history
(2026-05-17 onward), and **14 of those went to Hermes**, not to
Opus.

The Opus-primary dispatch flip either (a) never actually took
effect in production traffic, or (b) the operator hasn't run
enough investigations in the measurement window for the flip to
matter. Without the operator using Antiek as their primary
research surface, the measurement protocol cannot produce data.

### 2. The verifier-rubric chain isn't linking to syntheses

More important than (1): **zero verified syntheses for either
provider.** Even the 14 Hermes calls have no associated
`rubric.scored` events that the analyzer can correlate back to
them via `investigation_id`.

This means even if the operator ran 100 syntheses tomorrow, the
analyzer would still return `insufficient_data` — because the
verifier-tier substrate isn't producing rubric scores against the
synthesis outputs in the way §14.4 assumes.

This is a deeper finding than the measurement window itself.
The spec implicitly assumed every synthesis triggers a verifier
pass that emits a `rubric.scored` event. Either the verifier
isn't running on synthesis outputs in production, or it's
running but not emitting `rubric.scored` (it emits a different
event type that the analyzer doesn't know about).

## Recommended close-out

**G5 is provisionally CLOSED** with the `insufficient_data`
verdict on file. Two follow-on actions:

1. **Sprint 21 substrate audit:** confirm whether the verifier
   tier emits `rubric.scored` events on synthesis outputs in
   production traffic. If yes, why aren't they being linked?
   If no, what event type is being emitted instead? The
   analyzer's investigation-id linking heuristic may need
   widening.

2. **Operator usage expectation:** the §14.4 measurement
   protocol needs ~50+ investigations to produce a signal.
   If operator usage stays at the current ~16/month rate, the
   measurement window will never close cleanly. The gate's
   re-opening criterion is "≥20 verified syntheses per
   provider," not a calendar date.

## What this does NOT block

The verdict is `insufficient_data`, not `keep_opus_primary` and
not `flip_to_hermes_primary`. The dispatch config stays as-is
(`substrate/dispatch/config.yaml`). Sprint 20+ work that depended
on the verdict landing can proceed with the operator's discretion
on synthesis tier; the substrate itself has no opinion.

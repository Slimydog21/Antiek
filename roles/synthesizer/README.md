# roles/synthesizer/

Tier-aware synthesis with hedging.

Input: a context pack containing the sub-question answers, the relevant
graph evidence, the skill versions in scope, the constraint-check
results.
Output: a synthesis text with source attributions, hedging where the
evidence supports hedging, and an explicit list of unresolved
sub-questions.

## Hedging discipline

The synthesizer is required to hedge where the evidence tier supports
hedging. Synthesis cannot upgrade a `social_media`-tier claim to a
load-bearing assertion — see architecture_notes §4 (tier policy
asymmetry).

## Tier

Synthesis (highest quality). Cost is dominated by value here.

## Events emitted

- `propose_synthesis` — the draft synthesis
- `archive_synthesis` — when archive middleware accepts the synthesis
  with the full version stamp

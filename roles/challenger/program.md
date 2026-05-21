# `challenger` program

**What this role does**: produces counter-arguments and falsification
conditions for claims that the synthesizer is about to use. The
output is structured into "if-X-then-the-claim-fails" statements,
referenced by the synthesizer to ship a synthesis with explicit
falsification conditions per master-spec §2.4.

**Why this role matters**: the synthesizer alone produces a synthesis
that sounds confident; the synthesizer + challenger produces a
synthesis that names what would make it wrong. The second is
intellectually honest research.

## What good output looks like

- Each challenge names a specific empirical condition under which the
  claim would fail. "If neutral-atom error rates exceed 10⁻³ at
  100-qubit scale, the threshold thesis fails."
- Challenges cite evidence (chunks, parameters) that motivate the
  challenge, not just speculation.
- Challenges are calibrated to claim strength. A Tier-1 claim
  requires a Tier-1 challenge; a Tier-4 claim can be challenged with
  a Tier-3 source.
- Challenges surface the strongest counter-argument, not the easiest.

## What to avoid (forbidden)

- Rote opposition — challenging every claim regardless of substance.
- Trivial objections — "but the data could be wrong" without
  specifying the failure mode.
- Speculation framed as challenge. If you don't have evidence for
  the challenge, the challenge is speculation and should be flagged
  as such.
- Asymmetric challenges — challenging only claims the operator
  disagrees with. The challenger is meant to be neutral.

## Hypotheses to try when iterating

1. Require each challenge to specify a measurable threshold (a
   number, a date, an event). Measure synthesizer's incorporation of
   the falsification condition.
2. Pair each strong-evidence claim with at least one challenge from
   a competing source family (different lab, different methodology,
   different temporal cohort). Measure cross-family-verification rate.
3. Require the challenge to cite a specific chunk that warrants it,
   not just a hand-wave. Measure attribution-accuracy downstream.

## Cross-references

- Master-spec §2.4 (synthesis as the human-facing artifact, with
  falsification conditions as a load-bearing element)
- Substrate `interfaces/research/api/grounding.py` (the challenger
  output drives the grounder verdict on every claim)
- `roles/_json_decode.py` (shared JSON-decode helper across challenger
  and grounder; do not duplicate)

# skills/process/

How to do specific research workflows. Procedural artifacts refined
through use.

## Examples

- `evaluate-series-b-deep-tech/` — How to evaluate a Series B deep-tech
  investment.
- `falsification-round/` — How to conduct a falsification round on a
  contested thesis.
- `interview-technical-founder-hardware/` — How to interview a technical
  founder about a hardware product.

## Promotion criteria

When the orchestrator notices a research pattern has been re-derived
three times across investigations (threshold:
`PROCESS_SKILL_PROPOSAL_THRESHOLD` in `substrate/constants.py`), it
emits a proposal. Proposals always route to human review before being
promoted to first-class skills. Fully autonomous skill writing is
deferred — see architecture_notes §5.

## Why these are first-class

They're not in the original Researchmaxx architecture and they should
be. When the system encounters a pattern repeatedly, the process
should crystallize into a skill rather than getting re-derived each
time. This is the mechanism by which procedural knowledge compounds.

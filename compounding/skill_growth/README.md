# compounding/skill_growth/

Programmatic skill update on Phase 8 completion.

## What it does

1. Receives a skill-update proposal from `compounding/extraction/`.
2. Applies the proposal to the relevant domain skill file (with diff
   captured before and after).
3. Records the diff result in the event log.
4. Triggers `compounding/verification/` to confirm growth happened.
5. On verified growth, marks `phase_log[8].verified = True`.

`replay.py` hosts the candidate-side Phase-8 seam: copy the baseline
skills tree into a temporary overlay and apply the candidate patch there
without emitting production auto-patch events. Later replay slices run
held-out investigations against that overlay before the gate can enforce.

## Process skill codification (deferred)

Also hosts the system-proposed process-skill codification
infrastructure. When the orchestrator notices a research pattern has
been re-derived `PROCESS_SKILL_PROPOSAL_THRESHOLD` times (see
`substrate/constants.py`), it emits a `propose_process_skill` event.
Proposals route to human review; fully autonomous skill writing is
gated. See architecture_notes §5.

# orchestration/phase_runner/

State machine for the 9-phase autonomous research protocol.

## Phases

Defined in `substrate/constants.py:PHASES`:

```
phase_0_intake
phase_1_decompose
phase_2_retrieve
phase_3_extract
phase_4_connect
phase_5_synthesize
phase_6_verify
phase_7_archive
phase_8_compound
```

## Discipline

Phase transitions are explicit function calls, not implicit model
behavior. The Researchmaxx audit identified prose-enforced phase
orchestration as "the single biggest gap in the architecture"; this
module is the fix. See architecture_notes §2.2.

## Phase 8 verification

Phase 8 (graph merge into compounding-domain skills) cannot be marked
complete unless `phase_log[8]["verified"] == True`, based on a real
diff of the skill files showing growth. Mechanical, not rhetorical.

## Events emitted

- `enter_phase`, `exit_phase` — per phase transition
- `verify_phase` — for phases requiring verification (notably 8)

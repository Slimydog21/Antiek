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
skills tree into a temporary overlay, apply the candidate patch there
without emitting production auto-patch events, and run held-out candidate
backtests through an injected runner that receives the overlay skill root.
Replay outputs can be evaluated against baseline reports through the
existing backtest cohort comparator. The production investigation rerun
implementation remains a later slice.

Runtime Phase-8 can discover configured held-out replay IDs through
`ANTIEK_PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS`. Until the production rerunner
exists, that path returns explicit `runner_unavailable` gate evidence instead
of silently pretending candidate replay succeeded.

## Phase-8 replay operator contract

Candidate replay is intentionally opt-in. The default path is fail-closed:
when held-out replay ids are configured but no runner is enabled, Phase 8
materializes the candidate skill overlay in an isolated workspace and records
`runner_unavailable` evidence in the gate notes. It does not spend on model
dispatch or mutate production research state.

Environment knobs:

- `ANTIEK_PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS`: comma/newline-separated
  archived synthesis ids to use as the held-out replay cohort. Empty means no
  replay evidence is attempted.
- `ANTIEK_DUCKDB_PATH`: baseline graph DB. When set, replay copies this DB into
  the replay workspace and loads baseline `BacktestReport` objects from the
  copy, not from the live file.
- `ANTIEK_PHASE8_REPLAY_OVERLAY_PARENT`: optional parent directory for replay
  workspaces. If omitted, temp dirs are used.
- `ANTIEK_PHASE8_REPLAY_RUNNER`: runner selector. Empty is the safe default.
  `loop1` / `loop_one` opts into the Loop-1 candidate held-out adapter.
  Unknown values fail closed and appear in replay notes.

The replay workspace redirects all known mutable sinks:
`ANTIEK_DUCKDB_PATH`, `ANTIEK_HOME`, `ANTIEK_RESEARCH_EVENTS_DIR`,
`ANTIEK_RESEARCH_PHASE_LOG_DIR`, `ANTIEK_RESEARCH_DIR`,
`ANTIEK_RESEARCH_ARTIFACTS_DIR`, and `ANTIEK_KNOWLEDGE_SKILLS_DIR`. The
candidate skill patch is applied only under that overlay. The adapter also
suppresses recursive `ANTIEK_PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS` while the
held-out replay investigation runs, so replay does not recursively replay
itself.

Operational bar before enabling `ANTIEK_PHASE8_REPLAY_RUNNER=loop1` on a real
run:

1. Use a bounded held-out cohort whose archived syntheses have recorded
   outcomes; otherwise the gate will correctly report underpowered evidence.
2. Set `ANTIEK_PHASE8_REPLAY_OVERLAY_PARENT` to a disposable directory and
   inspect it after the run if a candidate replay fails.
3. Keep `ANTIEK_PHASE8_MODE=shadow` for first runs. Enforcing mode should only
   be used after calibration and after the replay notes show complete candidate
   evidence.
4. Expect normal Loop-1 dispatch cost when the `loop1` runner is enabled. The
   default path exists specifically to avoid accidental spend.

Before enabling the runner against real held-outs, run the no-dispatch smoke
harness:

```bash
./.venv/bin/python tools/phase8_replay_smoke.py
```

The smoke harness seeds a temporary baseline DB, enables the `loop1` opt-in,
stubs the held-out runner, and verifies that candidate replay reports reach the
gate evaluation without touching the operator graph or dispatching models.

## Process skill codification (deferred)

Also hosts the system-proposed process-skill codification
infrastructure. When the orchestrator notices a research pattern has
been re-derived `PROCESS_SKILL_PROPOSAL_THRESHOLD` times (see
`substrate/constants.py`), it emits a `propose_process_skill` event.
Proposals route to human review; fully autonomous skill writing is
gated. See architecture_notes §5.

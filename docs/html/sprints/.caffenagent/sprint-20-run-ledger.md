# caffenagent run - SPRINT-20

- **Spec file:** `docs/html/sprints/sprint-20.html`
- **Source spec section:** `docs/sprint-breakdown.html#sprint-20`
- **Target branch:** `reader/integration`
- **Status:** operator-gated
- **Verified code SHA:** commit containing this record
- **Recorded:** `2026-07-01T20:26:27Z`
- **Run mode:** status reconciliation over Sprint 20 acceptance criteria

## Fresh Gates

- `cd apps/reading && npm test -- TrajectoryReplay --run`
  - Passed: 1 file / 8 tests.
- `.venv/bin/python -m pytest tests/test_dispatch_tier_verdict.py tests/test_prompt_autoresearch_verdict.py tests/test_phase8_gate.py tests/test_phase8_calibration_status.py tests/test_gepa_phase8_bridge.py tests/test_gepa_phase8_applier_e2e.py -q`
  - Passed: 81 tests.

## Acceptance Mapping

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Trajectory replay works against a real multi-step investigation | component verified / real-investigation proof still needed | `apps/reading/src/components/TrajectoryReplay.tsx`; `apps/reading/src/components/TrajectoryReplay.test.tsx`; Storybook story exists |
| Dispatch verdict is on paper | provisional / fresh-traffic re-run still needed | `docs/decisions/dispatch-tier-verdict.md`; `docs/decisions/g5-dispatch-tier-verdict-followup.md`; dispatch verdict tests passed |
| Autoresearch Wedge 1 verdict is on paper | operator-gated | prompt-autoresearch verdict tests passed; no Sprint 20 operator ratification document found |
| Antiek-produced artifact is in the wild | operator-gated | external publication cannot be completed locally |
| Phase 8 gate shadow-mode after ratification | substrate verified / conditional gate pending | `compounding/skill_growth/gate.py`; Phase 8 and GEPA bridge/applier tests passed |

## Remaining Operator Actions

- Publish at least one substantive Antiek-produced artifact outside Antiek.
- Run enough fresh investigations to produce verified synthesis traffic and re-run `tools.dispatch_tier_verdict`.
- Record the final Sprint 20 dispatch posture decision.
- Read the Sprint 19 prompt-autoresearch mutation report and record the Wedge 1 ratify-or-reject verdict.
- If Wedge 1 ratifies, run Phase 8 gate in shadow mode against real patch traffic for calibration.

No autonomous local-only pass can honestly close the external publication, dispatch event-log, or ratification verdict gates.

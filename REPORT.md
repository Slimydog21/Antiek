# Cascade owner-model binding — REPORT (codex child + parent verification)

## What shipped (uncommitted worktree edits → now committed by parent)
- interfaces/research/api/cascade_routes.py: LaunchRequest.owner_model_choices (per-role UserModelChoice, exact PAID_LOOP_ONE_ROLES set, owner-scoped, 422 owner_model_unknown on validation/authority failure); stable launch digest (root/plan-version/leaves/budget/choices); durable owner-launch claim via claim_owner_launch (idempotent replays return the same session; OwnerLaunchConflict -> 409 owner_model_operation_conflict; claim-store infra errors -> 500 owner_launch_claim_failed, retryable); ResearchOwnerManifest installed as contextvar for the cascade run (synthesis tail + paid dispatch via dispatch_loop_one when choices present); no manifest when choices absent (byte-identical legacy path); claim state machine advanced on broadcast.
- apps/reading/src/api/research.ts: launchPlan accepts owner_model_choices (six-role Record) + owner_operation_id.
- apps/reading/src/modes/DeepResearchWorkspace/index.tsx: the ModelPicker choice is now BOUND — submitted as owner route authority for all six paid roles; note text honestly says "Bound ... Launch fails closed" vs "Auto route — no owner manifest".

## Verification (parent re-ran)
- tests/test_cascade_api.py (original main suite): 37 passed.
- tests/test_start_research_owner_api.py + test_start_research_owner_dispatch.py + test_research_provider_gateway.py: 51 passed.
- ruff clean; frontend tsc -b clean; vitest DeepResearchWorkspace: 67 passed (11 files).

## Honest gaps
1. The codex child wrote dedicated owner-scoped cascade tests (replay idempotency, cross-owner rejection, unknown-model 422, crash-before-claim retry, manifest install) but they were UNCOMMITTED and lost when the parent reset the test file during debugging. They must be re-written (brief in the session memory); the implementation paths they covered are partially exercised by the existing suites.
2. The synthesis-tail test harness question (tail runner observation under TestClient for non-hard-ceiling launches) was left unresolved — the wiring exists in _run_to_completion; the next test-writing pass should cover it.

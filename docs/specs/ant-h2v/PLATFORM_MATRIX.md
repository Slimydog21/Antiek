# Platform matrix — decompose entry points (ANT-H2V SPR-08)

Bounded closure. Do not claim “engine fine across platform” without a filled row.

| Entry point | File:line | Hermetic test | Live LLM | Status |
|-------------|-----------|---------------|----------|--------|
| Cascade auto `POST /research/plans` (no `sub_questions`) | `cascade_routes.py:257` → `DispatchDecomposer` | `tests/test_cascade_create_plan_light.py`; `test_dispatch_decomposer_maps_stub_response` | SPR-07 operator card | **tested** (hermetic) |
| Cascade manual `sub_questions` | `cascade_routes.py:251-255` | `test_create_plan_returns_editable_tree` | N/A | **tested** |
| Event bus `DECOMPOSE_QUESTION_REQUESTED` | `decomposer.py:170` | `test_roles_decomposer_extraction.py` | optional | **tested** (bridge) |
| Loop1 orchestrator start → phase-1 decompose → full phase chain | `orchestration/loop_one/orchestrator.py:393-428` | `tests/test_loop_one_orchestrator.py` (stubbed full phase chain; phase-1 and phase-6 failure guards) | yes for live-provider E2E | **tested** (hermetic stubs; live providers not proved) |
| `plan_from_gap` / `plan_from_note` | `planner.py:141-166` | `test_cascade_planner.py`, `test_gap_detection.py` | uses injected decomposer | **tested** (fake only) |

## Closure sentence (allowed)

Cascade **auto-decompose** contract bugs are fixed and covered by hermetic tests; event-bus decomposer was already keyword-correct. Loop1 has hermetic full-phase-chain coverage with stubbed providers. Live provider health for auto-decompose and Loop1 requires operator verification.

## Not proved by this spec

- Full `POST /investigations` → decompose → phase-2 with live providers and no stubs.
- Paraphrase-regen parity between cascade and event bus.
- Reading UI always omits `sub_questions` on auto flow (verify `apps/reading/src/api/research.ts`).

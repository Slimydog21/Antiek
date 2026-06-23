# Platform execution matrix (ANT-EXEC-H2V SPR-10)

**Status:** Active closure matrix — every platform-wide claim must cite a row here or an equivalent handoff `### Scope Map`.

**Protocol:** `docs/agent-execution/HARD_TO_VARY.md` Phase B/E · **Gates:** `scripts/canonical_verify.sh`

| ID | Surface | Entry point | Hermetic gate (command) | Operator gate | Default `### Not proved` |
|----|---------|-------------|-------------------------|---------------|--------------------------|
| P-01 | Cascade auto-decompose | `POST /research/plans` omit `sub_questions` | `./scripts/canonical_verify.sh cascade` | `docs/agent-execution/OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` | Live LLM decompose on operator keys |
| P-02 | DispatchDecomposer adapter | `roles/cascade_planner/planner.py` | `pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response -q` | same as P-01 | Event-bus decomposer parity |
| P-03 | Cascade HTTP light route | `tests/test_cascade_create_plan_light.py` | included in `canonical_verify.sh cascade` | — | Full `test_cascade_api.py` collection |
| P-04 | Decomposer call sites | `scripts/audit_decomposer_call_sites.sh` | included in `canonical_verify.sh cascade` | — | Runtime-only branches |
| P-05 | Agent handoff schema | `tools/agent/verify_handoff.ts` | `./scripts/canonical_verify.sh handoff <md>` | — | Narrative quality / intent |
| P-06 | Session theater grep | `scripts/audit_agent_session.sh` | paired with handoff subcommand | — | Claims outside markdown packet |
| P-07 | AMS spec ref-lint | `scripts/agent_ams_ref_lint.sh` | `bash scripts/agent_ams_ref_lint.sh <sprint.html>` | — | Playwright mountain shell |
| P-08 | Reading substrate pytest | `.github/workflows/ci.yml` `pytest` job | CI on `main` (full suite) | — | Local hardware parity |
| P-09 | Werner mascot / hop | `apps/reading` Werner paths per Werner htmlspec | `canonical_verify.sh agent-gates` + case study §5 | Werner operator card (htmlspec) | Measured p95 / fps without artifact |
| P-10 | Serve / rights / legal | production deploy surfaces | **No** informational CI job alone (F7) | operator deploy checklist | Jurisdiction-specific legal review |
| P-11 | Loop 1 E2E (DeepResearchComplete) | `orchestration/loop_one/orchestrator.py` | `pytest tests/test_loop_one_orchestrator.py::test_loop_one_happy_path_emits_completed -q` | — | Live LLM on all 5 roles |
| P-12 | DeepResearchComplete negative | `orchestration/invariants/deep_research_complete.py` | `pytest tests/test_deep_research_complete.py::test_drw_only_trajectory_fails_without_synthesis -q` | — | Production DRW with Exa adapter |
| P-13 | Cascade session reconstruct | `orchestration/cascade_session.py` | `pytest tests/test_cascade_session.py -q` | — | SSE transport reconnect E2E |
| P-14 | PromotionFunnel serialize | `runtime/research_runner/promotion_funnel.py` | `pytest tests/test_research_runner.py::test_promotion_funnel_serialized_no_lock_timeout -q` | — | Remote-exec fan-out under load |
| P-15 | knowledge.reused flywheel | `runtime/research_runner/host_local.py` start path | `pytest tests/test_flywheel_reuse.py::test_two_run_contract_gather_emits_knowledge_reused_on_second_start -q` | — | Live dispatch cost delta > 0 on reuse-consuming loop |
| P-16 | Exa gather mock E2E | `runtime/research_runner/host_local.py make_exa_gather_loop` | `pytest tests/test_exa_gather_loop.py -q` | — | Live EXA_API_KEY discover→ingest cost |
| P-17 | Parent-terminal observability | `interfaces/research/api/cascade_routes.py _run_to_completion + session_status` | `pytest tests/test_drw_parent_terminal.py -q` | `docs/decisions/deep-research-smoke-checklist.md` | Real session-parent DeepResearchComplete on smoke DRW #1 |

**Profile:** `./scripts/canonical_verify.sh deep-research` runs P-11..P-17 hermetic gates (ANT-DRL SPR-DRL-02, SPR-DRL-08, SPR-DRL-09).

## How to use

1. **Phase B:** Copy relevant rows into handoff `### Scope Map` with `tested: yes|no` and log path.
2. **Phase D:** Run hermetic column; paste exit codes into `### Gate results`.
3. **Phase E:** Anything still in “Default Not proved” must appear under handoff `### Not proved` before `### Status`.

## Anti-fiction

- Do not add a row without a falsifiable command or named CI job.
- “Platform OK” without row IDs is **F3** (`THEATER_TAXONOMY.md` T-03).
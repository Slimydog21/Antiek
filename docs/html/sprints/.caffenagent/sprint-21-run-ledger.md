# caffenagent run - SPRINT-21

- **Spec file:** `docs/html/sprints/sprint-21.html`
- **Source spec section:** `docs/sprint-breakdown.html#sprint-21`
- **Target branch:** `reader/integration`
- **Status:** operator-gated
- **Verified code SHA:** commit containing this record
- **Recorded:** `2026-07-01T21:06:56Z`
- **Run mode:** status reconciliation over Sprint 21 acceptance criteria

## Fresh Gates

- `.venv/bin/python -m pytest tests/test_synquery.py tests/test_api_sprint17_21_endpoints.py tests/test_phase8_gate.py tests/test_phase8_calibration_status.py tests/test_gepa_phase8_bridge.py tests/test_gepa_phase8_applier_e2e.py tests/test_ai_actions.py tests/test_api_ai_undo.py tests/test_billing_pipeline.py -q`
  - Passed: 65 tests, 1 warning.
- `.venv/bin/python -m pytest tests/test_synquery.py -q`
  - Passed: 15 tests.
  - Added contract-equivalent completed transcript coverage: persists `expert_interview_transcript` as `source_tier=2`, stamps Synquery provenance metadata, chunks the transcript, and treats repeated webhook delivery as idempotent.
  - Added contract-equivalent spend-cap coverage: rejects operator budgets above the $5,000 hard cap and blocks bookings whose duration-adjusted expert-rate estimate exceeds the effective cap.
- `cd apps/reading && npm test -- AISidecar CommandPalette WorkspaceStore --run`
  - Passed: 2 files / 28 tests.
- `cd apps/reading && npm test -- AppShell.hotkeys AISidecar CommandPalette WorkspaceStore --run`
  - Passed: 3 files / 31 tests.

## Acceptance Mapping

| Criterion | Status | Evidence |
|-----------|--------|----------|
| PMF gate passed before Synquery activation | operator-gated | no PMF gate verdict found |
| Expert call booked and completed via Synquery | substrate present / external workflow gated | `tools/synquery`; `tests/test_synquery.py`; real API not exercised |
| Synquery transcript ingested | contract-equivalent substrate verified / live callback gated | `tools/synquery/adapter.py`; `tests/test_synquery.py`; completed transcript payload persists a tier-2 document + chunks; real Synquery webhook not exercised |
| Phase 8 enforcing in production with a correct rejection | blocked by G6 | `docs/operator_gate_actions.md` keeps G6 open; Phase 8 tests passed locally |
| Ubiquitous AI sidecar reaches every surface | shell shortcut verified / browser route audit still optional | AppShell global shortcut opens AISidecar as a docked-right workspace panel; AISidecar, CommandPalette, WorkspaceStore frontend tests passed; PostHog Wedge 4 verdict accepted current structured action surface |
| Expert-call cost discipline holds | contract-equivalent cap verified / live booking gated | Synquery budget filtering, hard-cap rejection, estimated booking-cost rejection, and billing pipeline tests passed; live paid booking not exercised |

## Tool Notes

- A bounded Grok read-only audit was attempted with `--agent general-purpose --no-subagents`.
- It failed with a `read_file` tool_output_error and is not acceptance evidence.

## Remaining Operator Actions

- Record the creation-surface PMF gate verdict.
- Enable Synquery only after that gate passes.
- Book and complete at least one real expert call through Synquery.
- Route the returned live transcript through the verified tier-2 ingest contract.
- Close G6 autoresearch Wedge 1 ratify-or-reject.
- If G6 ratifies, activate Phase 8 enforcing and record at least one correct rejection.
- Prove the expert-call hard cap on a live paid booking path.

No autonomous local-only pass can honestly close the PMF, external Synquery booking/payment/webhook, G6, or production-enforcing gates. The local substrate now has deterministic coverage for the transcript ingestion contract and booking spend-cap contract those live workflows should call.

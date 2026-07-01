# caffenagent run - SPRINT-18

- **Spec file:** `docs/html/sprints/sprint-18.html`
- **Target branch:** `reader/integration`
- **Status:** operator-gated
- **Verified code SHA:** `61945576`
- **Recorded:** `2026-07-01T20:21:11Z`
- **Run mode:** status reconciliation over Sprint 18 acceptance criteria

## Fresh Gates

- `.venv/bin/python -m pytest tests/test_retrieval_time_gate.py tests/test_clis_exa_and_legal_gate.py tests/test_ip_holders.py tests/test_stripe_connect.py tests/test_api_sprint18_19_endpoints.py tests/test_event_payloads_v6_exa_browserbase_precursor.py tests/test_passage_dialogue.py -q`
  - Passed: 112 tests.
  - Warning: one Starlette/httpx deprecation warning from FastAPI TestClient.
- `npm test -- ThoughtPartnerPanel WatchForLaterFolder ParkedQuestion --run`
  - Passed: 1 file / 9 tests.

## Acceptance Mapping

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Retrieval-time legal gate in production | substrate verified / production operator-gated | `tests/test_retrieval_time_gate.py`, `tests/test_clis_exa_and_legal_gate.py`; production deployment still external |
| Publisher dashboard architecture | substrate verified / activation gated | `tests/test_ip_holders.py`, `tests/test_stripe_connect.py`, `tests/test_api_sprint18_19_endpoints.py`; G2/G3 still block real payout/email activation |
| Brainstorming Workstation feature-complete | verified at scoped test level | `tests/test_passage_dialogue.py`; `apps/reading/src/modes/BrainstormStation/ThoughtPartnerPanel.test.tsx` |
| Substrate-only precursor for Wedges 1 + 2 | verified | `tests/test_event_payloads_v6_exa_browserbase_precursor.py`; generated frontend types exist in `apps/reading/src/generated/types.ts` |
| Full test suite green | not re-proven in this pass | S18 scoped gates passed; earlier UI reconciliation ran full reading Vitest and build checks |

## Remaining Operator Actions

- Verify live production deploy of the legal gate.
- Run the manual registry edit plus banned-URL `ingest_url(...)` REPL proof and confirm `rejected_by_legal_gate` in JSONL.
- Close G2 counsel review.
- Close G3 first publisher opt-in.

No autonomous code-only pass can honestly close those external proofs.

## Grok Harness Note

`grok` itself is usable: smoke prompts and a bounded read of this sprint passed
with `--agent general-purpose --no-subagents`. A richer read-only audit through
the custom caffenagent path failed on a stale `glob_file_search` tool name, so
future worker calls should either pin `general-purpose` for bounded audits or
repair the custom agent/tool compatibility before using it for autonomous
caffenagent cycles.

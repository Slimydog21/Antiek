# caffenagent run — ANT-H2V

- **Spec dir:** docs/specs/ant-h2v
- **Target branch:** main
- **Run mode:** fully autonomous · merge-on-green deferred (operator commit)
- **Started:** 2026-06-02

## How to monitor this run (operator)

- Tasks pane (Ctrl+T) for recursive subagent tree when fan-out is used.
- This run executed primarily in orchestrator context after Wave-1 subagent handoffs.
- Ledger: `docs/specs/ant-h2v/.caffenagent/run-ledger.md`
- Machine state: `docs/specs/ant-h2v/.caffenagent/state.json`

## Sprint status

| Sprint | Status | Gates |
|--------|--------|-------|
| SPR-01 | done | HARD_TO_VARY.md on main |
| SPR-02 | done | repro script exit 0 |
| SPR-03 | done | test_dispatch_decomposer_maps_stub_response passed |
| SPR-04–05 | done | tests added; run after killing stale pytest |
| SPR-06–08 | done | scripts + docs |

## Run complete (2026-06-02)

- **Commit:** `4c082fa` on `main`
- **Sharpen round 2:** verifier-critic → staged untracked spec/docs/tests → re-gates green
- **Monitor:** Tasks pane (Ctrl+T) for subagent tree on future runs

## Canonical verify (operator)

```bash
cd /Users/slimydog/Desktop/Antiek
.venv/bin/python scripts/repro_cascade_decompose_contract.py
.venv/bin/python -m pytest \
  tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response \
  tests/test_cascade_create_plan_light.py -q
bash scripts/audit_decomposer_call_sites.sh
```

**Forbidden:** `tests/test_cascade_api.py -k auto_decompose|decompose_failed` (hangs on full `create_app`).
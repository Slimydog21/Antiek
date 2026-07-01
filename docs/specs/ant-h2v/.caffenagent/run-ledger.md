# caffenagent run — ANT-H2V (product sprints)

- **Spec dir:** `docs/specs/ant-h2v`
- **Platform program:** `docs/htmlspec/antiek-hard-to-vary-execution/` (SPR-01–10 gates)
- **Consolidated PR:** #52 + platform stack → `prcrouch/ant-exec-platform`
- **PR state:** merged (`https://github.com/Slimydog21/Antiek/pull/52`)
- **Reverified:** `2026-07-01T20:09:18Z` on `reader/integration` at `c9e020c3`

## Sprint status (product)

| Sprint | Status | Gates |
|--------|--------|-------|
| SPR-01–08 | done | repro, adapter test, light route, audit script |

## 2026-07-01 Reverification

- `./scripts/canonical_verify.sh profile` passed: `CANONICAL_VERIFY_OK: profile`.
- `./scripts/canonical_verify.sh cascade` passed: repro contract, dispatch-decomposer regression, light create-plan route, and decomposer call-site audit.
- `./scripts/canonical_verify.sh agent-gates` passed: handoff Vitest gate (15 tests) plus audit/canonical pytest gates (6 tests).
- `.venv/bin/python -m pytest tests/test_loop_one_orchestrator.py -q --tb=no` passed: 5 tests.

PR #52 is merged. GitHub reported the merge checks green: `agent-execution-gates`,
`pytest`, `mypy --strict + ruff (declared scope, baselined)`, `keystone`, `tsc`,
Cloudflare Pages, and Strix Security Review.

### Fix landed during reverification

`tests/test_loop_one_orchestrator.py` now seeds the isolated DuckDB graph with a
real Tier-1 `chunk-1` before the happy-path canned role outputs cite it. This
keeps the stronger provenance validation honest: the Loop1 happy path no longer
passes by citing a chunk absent from the canonical retrieved context.

## Canonical verify (operator)

```bash
./scripts/canonical_verify.sh cascade
./scripts/canonical_verify.sh agent-gates
```

**Forbidden:** full `test_cascade_api.py` auto_decompose collection (hang hazard).

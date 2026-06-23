# caffenagent run — ANT-H2V (product sprints)

- **Spec dir:** `docs/specs/ant-h2v`
- **Platform program:** `docs/htmlspec/antiek-hard-to-vary-execution/` (SPR-01–10 gates)
- **Consolidated PR:** #52 + platform stack → `prcrouch/ant-exec-platform`

## Sprint status (product)

| Sprint | Status | Gates |
|--------|--------|-------|
| SPR-01–08 | done | repro, adapter test, light route, audit script |

## Canonical verify (operator)

```bash
./scripts/canonical_verify.sh cascade
./scripts/canonical_verify.sh agent-gates
```

**Forbidden:** full `test_cascade_api.py` auto_decompose collection (hang hazard).
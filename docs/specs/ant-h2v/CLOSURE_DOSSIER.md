# ANT-H2V closure dossier

**Date:** 2026-06-02  
**Spec:** `docs/specs/ant-h2v/index.html`

## What shipped

- `docs/agent-execution/HARD_TO_VARY.md` + `TEMPLATES.md` (SPR-01)
- `scripts/repro_cascade_decompose_contract.py` + `FAILURE_DOSSIER.md` (SPR-02)
- `test_dispatch_decomposer_maps_stub_response` (SPR-03)
- `test_create_plan_auto_decompose_without_sub_questions` (SPR-04)
- `create_plan` → HTTP 502 `decompose_failed` boundary (SPR-05)
- `scripts/audit_decomposer_call_sites.sh` (SPR-06)
- `OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` (SPR-07)
- `PLATFORM_MATRIX.md` (SPR-08)

## Root cause (verified)

Pre-network `TypeError` in `DispatchDecomposer.decompose` from keyword-only API drift. Not provider outage.

## Canonical verify

```bash
cd /Users/slimydog/Desktop/Antiek
.venv/bin/python scripts/repro_cascade_decompose_contract.py
.venv/bin/python -m pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response -q
.venv/bin/python -m pytest tests/test_cascade_create_plan_light.py -q
bash scripts/audit_decomposer_call_sites.sh
test -f docs/agent-execution/HARD_TO_VARY.md
```
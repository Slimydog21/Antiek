# Grok execution brief — ANT-H2V

Generated 2026-06-02. Open master spec: `file:///Users/slimydog/Desktop/Antiek/docs/specs/ant-h2v/index.html`

## Operator vision

Execute with **technical precision** (file:line, exception types), **exhaustive scope** (entry-point matrix), **craftsmanship hard to vary** (remove any gate → "done" claim collapses).

## todo_write skeleton

```
- SPR-01 protocol docs [wave 1]
- SPR-02 repro script [wave 1]
- SPR-03 DispatchDecomposer test [wave 2, after 02]
- SPR-04 HTTP auto-decompose test [wave 2, after 02]
- SPR-05 API error boundary [wave 3]
- SPR-06 audit script [wave 3]
- SPR-07 operator verify card [wave 4]
- SPR-08 platform matrix [wave 4]
```

## Wave execution order

1. Parallel: SPR-01 + SPR-02
2. Parallel: SPR-03 + SPR-04
3. Parallel: SPR-05 + SPR-06
4. Sequential: SPR-07 → SPR-08

## Canonical verify (after code sprints)

```bash
cd /Users/slimydog/Desktop/Antiek
# Env card — paste in every handoff
pwd
.venv/bin/python -V

.venv/bin/python scripts/repro_cascade_decompose_contract.py
.venv/bin/python -m pytest \
  tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response \
  tests/test_cascade_create_plan_light.py -q --tb=short
bash scripts/audit_decomposer_call_sites.sh
```

**Forbidden:** `pytest ... 2>&1 | tail -N` as sole sign-off; system `python` (3.9) instead of `.venv`; claiming "platform OK" without PLATFORM_MATRIX.md; **`tests/test_cascade_api.py -k auto_decompose|decompose_failed`** (full `create_app` — hangs; use `test_cascade_create_plan_light.py`).

**Note:** `interfaces/research/api/__init__.py` uses lazy exports so `cascade_routes` import does not load `app.py`. Kill stale `pytest` before gates if collection stalls (`pgrep -fl pytest`).

## Recommended invocation

```
/implement Execute ANT-H2V spec at docs/specs/ant-h2v/ — waves 1→4, merge-bar on every PR.
```

Or caffenagent with one subagent per sprint, worktree per wave-2 pair.

## Subagent patterns

| Sprint | Persona | Isolation |
|--------|---------|-----------|
| SPR-01–02 | generalPurpose | main branch |
| SPR-03–04 | implementer | parallel worktrees OK |
| SPR-05–06 | implementer + code-reviewer | same PR stack |
| SPR-07–08 | generalPurpose | docs only |

## Source brief

Egghead critique of Antiek sub-questions session + verified codebase state (2026-06-02).

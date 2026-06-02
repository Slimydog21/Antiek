# Operator verification — cascade auto-decompose (ANT-H2V SPR-07)

Manual sign-off when CI hermetic tests are green but you need provider proof.

## Env card (paste into handoff)

```
cwd: /Users/slimydog/Desktop/Antiek
python: .venv/bin/python
python -V: (paste output)
ANTIEK_DUCKDB_PATH: (if set)
commit: git rev-parse --short HEAD
```

## Preconditions

- `.venv` installed; research API can start locally.
- Provider keys configured for `decomposer` role (same as other Research roles).
- Hermetic gates already green:

```bash
.venv/bin/python scripts/repro_cascade_decompose_contract.py
.venv/bin/python -m pytest tests/test_cascade_planner.py -k dispatch_decomposer -q
.venv/bin/python -m pytest tests/test_cascade_create_plan_light.py -q
```

## Steps

1. Start the research API (your usual dev command).
2. `POST /research/plans` with **only** `problem` — omit `sub_questions`:

```bash
curl -sS -X POST "http://127.0.0.1:8000/research/plans" \
  -H "Content-Type: application/json" \
  -d '{"problem": "What are the main risks in grid-scale battery storage?"}' | jq .
```

3. Expect HTTP **200** and `tree.root.children` non-empty (or documented empty if model returns atomic).
4. On failure: HTTP **502** with `decompose_failed:` prefix — paste full JSON `detail` in handoff.
5. Record **LLM contacted: yes** and provider/model from dispatch logs if available.

## Pass / fail

| Check | Pass |
|-------|------|
| Status 200 | |
| children.length ≥ 1 | |
| No raw 500 without detail | |

Footer: operator name · date · commit SHA
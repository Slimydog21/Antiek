# FAILURE_DOSSIER — Cascade auto-decompose (ANT-H2V SPR-02)

**Date:** 2026-06-02  
**Symptom:** Research UI “no result” when submitting a problem without manual `sub_questions`.  
**LLM contacted:** **No** — failure is a pre-network Python `TypeError`, not provider outage.

## Numbered failure chain

1. **POST `/research/plans`** — Operator omits `sub_questions`; API takes the auto-decompose branch (`interfaces/research/api/cascade_routes.py` ~247–257).
2. **`_decompose(problem, max_depth)`** — Calls `build_plan(..., decomposer=DispatchDecomposer(), ...)` (`cascade_routes.py` ~108–112).
3. **`DispatchDecomposer.decompose`** — Production adapter builds prompt and dispatches (`roles/cascade_planner/planner.py` ~54–69).
4. **`TypeError` (pre-fix)** — Two contract violations before any HTTP provider call:
   - **`render_full_prompt(question)`** (positional) — `render_full_prompt` at `roles/decomposer/prompt.py` **123–128** declares keyword-only parameters (`*`, then `investigation_id`, `question`, `context`, …). A single positional argument does not bind; Python raises `TypeError`.
   - **`dispatch(prompt, role="decomposer")` without `investigation_id`** — `dispatch` at `substrate/dispatch/router.py` **330–334** requires `investigation_id` as a keyword-only argument after `*`. Omitting it raises `TypeError` even if prompt assembly had succeeded.
5. **HTTP 500** — Uncaught `TypeError` propagates out of `create_plan`; FastAPI returns 500 to the Reading/Research client.
6. **UI: no plan tree** — Client sees empty/error state (“no result”); no `root_node_id`, no persisted tree.

## Fix (present in tree; verified by SPR-02 repro)

`DispatchDecomposer.decompose` (`planner.py` **63–69**):

```python
prompt = render_full_prompt(
    investigation_id=investigation_id,
    question=question,
    context=context,
)
result = dispatch(prompt, role="decomposer", investigation_id=investigation_id)
```

Keyword calls match `render_full_prompt` (**123–140**, `roles/decomposer/prompt.py`) and `dispatch` (**330–334**, `substrate/dispatch/router.py`).

## Why “engine down” was the wrong diagnosis

| Claim | Falsifier |
|-------|-----------|
| Provider/API broken | `TypeError` fires before `dispatch` opens a socket (repro: `scripts/repro_cascade_decompose_contract.py`). |
| Decomposer model bad | No model response is parsed — failure is at call-site arity. |
| Tree planner broken | `FakeDecomposer` / manual `sub_questions` path never hits `DispatchDecomposer`. |

## Parallel path (not this bug)

`POST /investigations` → `DECOMPOSE_QUESTION_REQUESTED` → `make_decomposer_handler` (`interfaces/research/api/decomposer.py`) already used keyword `render_full_prompt(...)` and `dispatch(..., investigation_id=...)`. Only the cascade **auto-decompose** branch was wrong.

## Hermetic verification

```bash
cd /Users/slimydog/Desktop/Antiek
.venv/bin/python scripts/repro_cascade_decompose_contract.py
```

Expected: exit **0**, lines containing `REPRO_OK` for both old patterns.
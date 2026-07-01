# tools/prompt_autoresearch/

Local-only prompt mutation support for Autoresearch Wedge 1. This
package helps the operator run the Lutke-gap test for one role prompt,
starting with `synthesizer`, without touching the production VM.

The package does not decide whether G6 closes. It provides the runner
types, budget caps, deterministic score components, no-op calibration,
JSON outcome export, and verdict rendering. The operator still owns the
mutation cohort, qualitative review, and final decision artifact.

## Files

- `runner.py` — local-only `PromptAutoresearchRunner`, `PromptMutation`,
  and `PromptMutationOutcome`.
- `score.py` — composite score and deterministic sub-scores:
  voice/style, sector vocabulary, and grounding preservation.
- `budget.py` — per-iteration and total budget caps.
- `outcomes_io.py` — stable JSON export/import for mutation outcomes.
- `calibration.py` / `calibration_cli.py` — no-op variance calibration
  for acceptance epsilon.
- `verdict.py` / `verdict_cli.py` — G6/OA-005 ratify/reject markdown
  generation from mutation outcomes.
- `readiness.py` / `readiness_cli.py` — read-only audit of the Wedge 1
  unlock checklist.

## Invariants

- Run only on the operator's local machine. `runner.py` refuses
  `ANTIEK_ENV=production`.
- Do not mutate substrate code, dispatch config, or production prompts
  from this package.
- Calibrate epsilon from no-op variance before running the mutation
  cohort. The acceptance epsilon must be at least `max(0.05, 2σ)`.
- Treat `insufficient_data` as a real outcome, not a soft pass.
- Do not start Wedge 2, Wedge 3, or Wedge 4 from this package. Their
  gates live in `docs/integration_autoresearch.md` and
  `docs/engineering_deferrals.md`.

## Operator workflow

### 0. Audit current readiness

```bash
./.venv/bin/python -m tools.prompt_autoresearch.readiness_cli --repo-root .
```

This command is read-only. It reports which unlock criteria are
mechanically satisfied and which remain operator-bound.

### 1. Run the no-op calibration cohort

Wire a local script that creates a `PromptAutoresearchRunner`, runs a
no-op mutator against the chosen role's golden traces, and leaves the
results in `runner.iterations`. At the end of that script, export the
outcomes:

```python
from pathlib import Path
from tools.prompt_autoresearch import write_outcomes_json

write_outcomes_json(
    Path("reports/autoresearch/synthesizer-noop-outcomes.json"),
    role="synthesizer",
    outcomes=runner.iterations,
)
```

Then render the calibration note:

```bash
./.venv/bin/python -m tools.prompt_autoresearch.calibration_cli \
  --role synthesizer \
  --outcomes reports/autoresearch/synthesizer-noop-outcomes.json \
  --output reports/autoresearch/synthesizer-calibration.md
```

Use the reported recommended epsilon for the mutation cohort.

### 2. Run the mutation cohort

Run the local mutation script with epsilon set at or above the
calibration recommendation. After the cohort completes, export the
mutation outcomes:

```python
from pathlib import Path
from tools.prompt_autoresearch import write_outcomes_json

write_outcomes_json(
    Path("reports/autoresearch/synthesizer-outcomes.json"),
    role="synthesizer",
    outcomes=runner.iterations,
)
```

### 3. Render the G6 verdict artifact

```bash
./.venv/bin/python -m tools.prompt_autoresearch.verdict_cli \
  --role synthesizer \
  --outcomes reports/autoresearch/synthesizer-outcomes.json \
  --output docs/decisions/autoresearch-wedge-1-verdict.md
```

The verdict module enforces the mechanical Lutke-gap criteria:

- at least 20 mutations
- acceptance rate at least 40%
- mean delta at least 0.05
- no accepted mutation with grounding below 0.80
- no accepted mutation where sector vocabulary badly trails rubric score

## What this does not prove

The generated verdict markdown does not prove operator qualitative
endorsement, hold-out trace transfer, or production-investigation
transfer by itself. Those remain part of the G6/OA-005 operator review
described in `docs/operator_gate_actions.md` and
`docs/integration_autoresearch.md`.

## Verification

Focused gate:

```bash
./.venv/bin/python -m pytest \
  tests/test_prompt_autoresearch.py \
  tests/test_prompt_autoresearch_verdict.py \
  tests/test_prompt_autoresearch_calibration.py \
  tests/test_prompt_autoresearch_docs.py \
  tests/test_prompt_autoresearch_readiness.py \
  tests/test_phase8_gate.py \
  -q --tb=short
```

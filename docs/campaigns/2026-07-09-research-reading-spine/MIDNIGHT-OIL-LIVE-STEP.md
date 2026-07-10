# Midnight Oil live step injector (residual bs)

## Default (safe)

- Offline stub steps only (`offline_goal_step_fn`).
- No network / multi-provider calls.

## Enabling live steps (operator-gated)

Both required — neither alone is enough:

1. Env: `ANTIEK_MIDNIGHT_OIL_LIVE_STEP=1` (or any truthy value; default off)
2. Process inject: `configure_midnight_oil_live_step(step_fn, project_fn)`
   at app boot

```python
from substrate.midnight_oil import configure_midnight_oil_live_step

def my_live_step(job):
    ...  # call dispatch / swarm; return WorkerStepResult

def my_live_projection(job):
    ...  # projected MAX USD the next step may spend (finite, >= worst case)

configure_midnight_oil_live_step(my_live_step, my_live_projection)
```

## Reserve-before-spend (budget safety)

The approved price ceiling is a pre-commitment, not an accounting line:

- Before each step the worker reserves `project_fn(job)` against the
  ceiling and persists the reservation (`reserved_usd` on the job row).
  A step whose projection does not fit is **never executed**
  (`budget_halted`, note `budget_halt_preflight`).
- A step that spends more than it projected fails the job with note
  `reservation_overrun` — and the true spend is recorded, never discarded.
- A crash between reserve and settle leaves `reserved_usd` on the row;
  the next iteration fails closed (`unsettled_reservation`) for operator
  reconciliation against provider billing.
- Installing a live `step_fn` without a `project_fn` raises: live money
  requires a declared per-step maximum.

## Honesty

- API `run_job_offline` reports `offline` / `live_step` flags.
- `force_offline=True` always uses stubs (tests / kill switch).
- Deposit path unchanged — land HTML twins after run.

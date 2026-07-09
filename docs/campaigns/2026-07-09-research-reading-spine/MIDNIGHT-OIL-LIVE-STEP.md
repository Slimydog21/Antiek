# Midnight Oil live step injector (residual bs)

## Default (safe)

- Offline stub steps only (`offline_goal_step_fn`).
- No network / multi-provider calls.

## Enabling live steps (operator-gated)

Both required — neither alone is enough:

1. Env: `ANTIEK_MIDNIGHT_OIL_LIVE_STEP=1` (or any truthy value; default off)
2. Process inject: `configure_midnight_oil_live_step(step_fn)` at app boot

```python
from substrate.midnight_oil import configure_midnight_oil_live_step

def my_live_step(job):
    ...  # call dispatch / swarm; return WorkerStepResult

configure_midnight_oil_live_step(my_live_step)
```

## Honesty

- API `run_job_offline` reports `offline` / `live_step` flags.
- `force_offline=True` always uses stubs (tests / kill switch).
- Deposit path unchanged — land HTML twins after run.

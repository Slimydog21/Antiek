# `runtime/notdiamond` — NotDiamond advisory adapter (ANT-ND SPR-01)

A thin, lazily-imported adapter around the [NotDiamond](https://notdiamond.ai)
model router. NotDiamond is an **advisory** measured wedge scoped to the Deep
Research Workspace's research-runner role calls — it *recommends* a model;
dispatch decides; the `cd602c9` verify-tier fallback owns failure. See the
master spec at `~/specs/antiek-notdiamond/index.html`.

## What this package does

```python
from runtime.notdiamond import select_model

rec = select_model(
    messages=[{"role": "user", "content": "…"}],
    candidates=["openai/gpt-4o-mini", "anthropic/claude-3-5-haiku-20241022"],
    tradeoff="cost",        # "quality" | "cost" | "latency" | "ct_N"
    timeout_ms=500,
)
rec.provider, rec.model, rec.session_id, rec.decision_latency_ms
```

- Returns a frozen `Recommendation`.
- Imports the `notdiamond` SDK **lazily inside the call** — importing this
  package (or dispatch) never requires the SDK.
- Every failure is a `NotDiamondError` subclass (`NotDiamondNotInstalled`,
  `NotDiamondAuthError`, `NotDiamondTimeout`, `NotDiamondAPIError`) so callers
  can catch the base and fall through to dispatch's own routing.

## What this package does **not** do

- **No dispatch integration** — that is **SPR-03**. Nothing here calls, imports,
  or is imported by `substrate/dispatch/`.
- No event-log writes (that is SPR-02's `record_nd_decision`), no per-role
  candidate sets (SPR-04), no kill switch / shadow mode (SPR-06), no training
  (SPR-07/08).

## Environment

| Var | Required | Notes |
|-----|----------|-------|
| `NOTDIAMOND_API_KEY` | for live calls | Resolved lazily at first call, fail-loud, never logged. Listed in `infrastructure/ansible/templates/secrets.env.j2`. |

Install the optional SDK only when enabling ND:

```bash
pip install 'antiek[notdiamond]'      # pins notdiamond==1.7.0
```

## Tests

- `pytest runtime/notdiamond/test_adapter.py` — CI-runnable; fakes the selector,
  needs neither the SDK nor a key. Covers lazy import, fail-loud auth, timeout
  and exception mapping, recommendation shape, and no-key-in-logs.
- `NOTDIAMOND_API_KEY=… pytest runtime/notdiamond/test_smoke.py -v -s` — live
  cross-provider round-trip; **skips cleanly** when the key is unset.

# runtime/notdiamond

Thin adapter around the optional NotDiamond SDK. ND is advisory only: it can
recommend a provider/model, but dispatch remains authoritative and owns all
fallback behavior.

```python
from runtime.notdiamond import select_model

rec = select_model(
    messages=[{"role": "user", "content": "..."}],
    candidates=["openai/gpt-4o-mini", "anthropic/claude-3-5-haiku-20241022"],
    tradeoff="cost",
)
```

Environment:

- `NOTDIAMOND_API_KEY`: required only for live calls; resolved at first call and
  never logged.
- `ANTIEK_NOTDIAMOND_MODE=shadow`: explicitly enables DRW shadow evaluation;
  unset or `disabled` performs no NotDiamond call and never changes routing.
- `ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE=true`: separate required consent
  for sending the assembled DRW prompt to NotDiamond. Shadow mode without this
  flag records `prompt_disclosure_not_approved` and performs no external call.

Install:

```bash
pip install 'antiek[notdiamond]'
```

Tests:

- `pytest runtime/notdiamond/test_adapter.py`
- `NOTDIAMOND_API_KEY=... pytest runtime/notdiamond/test_smoke.py -v -s`

Dispatch integration is shadow-only, disabled by default, and specified in
`docs/htmlspec/notdiamond-shadow-measurement.html`. It records recommendations
without changing the authoritative provider order.

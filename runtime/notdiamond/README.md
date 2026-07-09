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

Install:

```bash
pip install 'antiek[notdiamond]'
```

Tests:

- `pytest runtime/notdiamond/test_adapter.py`
- `NOTDIAMOND_API_KEY=... pytest runtime/notdiamond/test_smoke.py -v -s`

No dispatch integration — see SPR-03. Spec:
`/Users/slimydog/specs/antiek-notdiamond/index.html`.

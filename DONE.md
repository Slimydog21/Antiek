# DONE — BYOT usage/balance HTTP endpoints

## Files created / modified

| File | What |
|---|---|
| `interfaces/research/api/byot_usage_routes.py` | **NEW** — 3 owner-scoped endpoints + adapter dispatch + Pydantic models |
| `interfaces/research/api/settings_budget.py` | **MODIFIED** — registered `byot_usage_routes` in `register_settings_budget_routes` |
| `tests/byot/test_byot_usage_routes.py` | **NEW** — 13 TestClient tests, adapters mocked, no live net |

## Endpoints

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/settings/usage` | Returns per-key usage snapshot (used_cents, limit_cents, remaining_cents) for the session user. Empty list if no keys tracked. |
| `POST` | `/settings/usage/{api_key_id}/limit` | Sets (or clears with `null`) a key's spend cap. 404 if key doesn't belong to session user. |
| `GET` | `/settings/balance/{api_key_id}` | Dispatches to the native balance adapter (DeepSeek/Kimi) or falls back to spend-history. Returns `kind="unavailable"` on adapter degrade. 404 on cross-user key. |

## Test results

```
13 passed, 1 warning in 0.50s
```

Full command: `~/Antiek/platform/.venv/bin/python -m pytest tests/byot/test_byot_usage_routes.py -v`

Tests cover:
- Empty usage snapshot for fresh user
- Ledger snapshot with used/limit/remaining
- Owner-scoped isolation (other user's keys invisible)
- Set limit creates row + reflects in snapshot
- Set limit clear (null)
- Cross-user set_limit → 404
- Unknown key set_limit → 404
- Native balance adapter (mocked DeepSeek)
- Adapter degrade → `kind=unavailable`
- Cross-user balance → 404
- Unknown key balance → 404
- Spend-history fallback for providers without native adapter
- Credential load failure → `kind=unavailable`

## Lint / type

- `ruff check` — clean (0 errors)
- `mypy --strict` on `byot_usage_routes.py` — clean (0 errors in new code; pre-existing errors in other files)

## Honest gaps

- **No frontend/React.** Per non-goal.
- **No wiring into settle path.** The `record_settlement` hook stays unit-tested; the live settle integration is a separate lane.
- **No new balance adapters.** Only DeepSeek (native), Kimi (native), and spend-history (generic fallback) exist. Other providers (Anthropic, xAI, Zhipu, MiMo) fall back to spend-history or `unavailable`.
- **Balance endpoint creates a fresh `httpx.Client` per request.** Production should pool/reuse; acceptable for v1.
- **`_load_registry` is a private import from `settings_models_admin`.** Follows the existing codebase pattern (same-package private imports are used elsewhere), but a public helper would be cleaner.

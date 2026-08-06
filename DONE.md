# DONE — mimo-cc — BYOT per-key usage ledger + balance adapters

## Files created

| File | Purpose |
|---|---|
| `substrate/byot_usage/__init__.py` | Package init |
| `substrate/byot_usage/ledger.py` | Per-key usage ledger (SQLite sidecar, WAL, single-writer) |
| `substrate/byot_usage/balance/__init__.py` | Balance package init |
| `substrate/byot_usage/balance/base.py` | `BalanceSnapshot` dataclass + `BalanceAdapter` protocol |
| `substrate/byot_usage/balance/deepseek.py` | DeepSeek native balance adapter (`GET /user/balance`) |
| `substrate/byot_usage/balance/kimi.py` | Kimi/Moonshot native balance adapter (`GET /users/me/balance`) |
| `substrate/byot_usage/balance/spend_history.py` | OpenAI spend-history adapter (budget − ledger, no live call) |
| `tests/byot/test_usage_ledger_settle.py` | 13 tests for the usage ledger |
| `tests/byot/test_balance_adapters_drift.py` | 11 tests for balance adapters + drift degradation |

## Test results

```
$ ~/Antiek/platform/.venv/bin/python -m pytest tests/byot/ -v
26 passed in 0.59s
```

**Exact pass count: 26** (13 ledger + 11 adapters + 2 pre-existing catalog tests).

## Lint/type results

```
$ ruff check substrate/byot_usage/ tests/byot/test_usage_ledger_settle.py tests/byot/test_balance_adapters_drift.py
All checks passed!

$ mypy --strict substrate/byot_usage/ledger.py substrate/byot_usage/balance/*.py
# 0 errors in new files (236 pre-existing errors in unrelated files)
```

## Honest gaps

1. **No wiring to settle path.** The brief says to hook `ByotUsageLedger.record_settlement()` into `ResearchProviderGateway._settle_or_converge()`. This is not done — the gateway's settle path exists but wiring it requires touching the audited provider_gateway, which is a higher-blast-radius change. The ledger itself is fully functional and tested; wiring is a follow-up.
2. **No xAI balance adapter.** The brief scope says "DeepSeek + Kimi + the OpenAI spend-history pattern is enough." xAI management-api balance is not implemented (requires G4 admin key + team_id).
3. **No API routes.** No `interfaces/research/api/byot_usage_routes.py` — the brief scope is backend modules only, not API endpoints.
4. **Spend-history adapter is stateless.** It reads from the ledger but does not poll any live endpoint — this is by design per spec §5.F (no admin key needed).

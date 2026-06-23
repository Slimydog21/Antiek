# DRW failure smoke runbook

Manual verification for honest decompose failures (`POST /research/plans`).
Use `--workers 1` on every uvicorn start (DuckDB single-writer invariant).

## State A — no provider

```bash
cd /path/to/Antiek
# Do NOT source .env
./.venv/bin/python -m uvicorn interfaces.research.api.app:app --workers 1 --port 8000
```

Expect:

- Startup log contains: `0 providers registered — LLM features will fail`
- `curl -s http://127.0.0.1:8000/health | jq .providers_ready` → `false`
- DRW propose UI: **No model provider is configured. Set a provider key and restart.**

## State B — backend down

Stop uvicorn. Point the reading app at the API base (dev proxy or `VITE_API_BASE_URL`).
Open DRW propose.

Expect: **The research engine isn't running. Start the backend, then retry.**

## State C — healthy decompose

```bash
source .env   # OPENROUTER_API_KEY etc.
./.venv/bin/python -m uvicorn interfaces.research.api.app:app --workers 1 --port 8000
```

Expect:

- No zero-provider WARNING
- `curl -s http://127.0.0.1:8000/health | jq .providers_ready` → `true`
- Propose succeeds (decomposer may use OpenRouter fallback when Hermes absent)

## State D — upstream error (best-effort)

If reproducible (e.g. invalid `OPENROUTER_API_KEY`), expect:
**The model provider returned an error. Retry, or check your key's quota.**

Otherwise: covered by `tests/integration/test_decompose_failure_e2e.py` (not manually reproduced).
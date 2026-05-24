# Runbook · dispatch fallback chain

**Owner:** dispatch
**Last verified:** 2026-05-24

## Symptom

A dispatch call to a primary tier (Hermes / xAI / Grok via the bridge)
fails, and the fallback chain DID NOT fire. Either:

- The error propagates to the caller as a `ProviderError` despite a
  fallback being configured in `substrate/dispatch/config.yaml`.
- Logs show `fallback_chain_index=0` (no fallback attempted) when the
  primary tier raised.

Adjacent symptom: an OAuth-refresh-failure 503 from the Hermes bridge
turned into a permanent error instead of falling through to the next
chain member.

## Likely cause

The fallback chain only fires on `ProviderError(retryable=True)`. The
adapter raised with `retryable=False` (or didn't set the flag at all
and Python's default-false took effect).

The Hermes bridge specifically returns HTTP 503 when its underlying
OAuth refresh fails — and the I-DISPATCH-4 contract in
`docs/decisions/dispatch_idempotency_contract.md` REQUIRES that 503 be
translated to `retryable=True`.

## Quick diagnostics

```bash
# What does the failed DispatchCall event say?
.venv/bin/python -c "
from substrate.event_log import recent
for e in recent(action_type='DISPATCH_CALL', limit=5):
    print(e.event_id, e.payload.get('provider'), e.payload.get('fallback_chain_index'))
"

# Is the chain configured for this tier?
yq '.tiers' substrate/dispatch/config.yaml
```

If `fallback_chain_index=0` on a failed call: the adapter raised
non-retryable.

If `fallback_chain_index >= 1` but the final call still failed: the
chain itself exhausted (every tier failed). That's a wider outage; see
the providers' status pages.

## Root-cause path

The chaos test at `tests/test_dispatch_fallback_chain.py` (commit
cd602c9) verifies the fallback chain end-to-end against the production
`config.yaml`. If the chain fails in production but the chaos test
passes, the failure is at the ADAPTER, not the router:

1. The adapter mapped a transient error to `retryable=False`.
2. The most common case: a 5xx response that the adapter treated as a
   permanent server error rather than transient.
3. The next common case: an exception path that re-raised an upstream
   `requests`/`httpx` error directly rather than wrapping it in
   `ProviderError(retryable=True, ...)`.

For the Hermes-bridge 503-on-OAuth-refresh case specifically: this is
I-DISPATCH-4. The Hermes adapter MUST translate 503 → `retryable=True`.
The contract is checked by
`tests/test_dispatch_idempotency_contract.py::test_oauth_refresh_503_maps_to_retryable`.

## Mitigation

1. Identify the failing adapter (provider name in the DispatchCall event).
2. Open `substrate/dispatch/providers/<provider>.py`.
3. Confirm every `raise ProviderError(...)` sets `retryable=True | False`
   intentionally — no defaults, no missing flags.
4. For the Hermes case specifically: confirm the 503 branch sets
   `retryable=True` AND includes "503" in the message for diagnostics.
5. Add or update a test in
   `tests/test_dispatch_idempotency_contract.py` that pins the
   classification for this failure mode.

The stewardship boundary matters here: **the Hermes bridge itself is
owned by Hermes Agent, not Antiek** (see memory
`project_antiek_hermes_bridge.md`). If the bridge starts returning a
different HTTP code for OAuth refresh failures, the Antiek-side
adapter's translation rule changes — but the rule itself lives in
this repo per I-DISPATCH-4.

## Reference

- Contract: `docs/decisions/dispatch_idempotency_contract.md`
- Boundary: `docs/decisions/substrate_dispatch_boundary.md`
- Chaos test (cd602c9): `tests/test_dispatch_fallback_chain.py`
- Idempotency tests: `tests/test_dispatch_idempotency_contract.py`
- Router: `substrate/dispatch/router.py:301` (`dispatch()`)
- Config: `substrate/dispatch/config.yaml`
- Memory: `project_antiek_hermes_bridge.md`

## Worked example

```
2026-05-24T14:22:00Z ERROR ProviderError: HTTP 503 — OAuth refresh failed at bridge
                            provider=hermes model=grok-4.3 latency_ms=147 retryable=False
```

Trace:

1. `retryable=False` is the bug. I-DISPATCH-4 requires `retryable=True`
   for the 503-on-OAuth-refresh case.
2. The router saw `retryable=False`, declined to retry, and propagated
   to the caller. The OpenRouter fallback never fired.
3. Open `substrate/dispatch/providers/hermes.py`; find the 503 branch;
   change `retryable=False` to `retryable=True`.
4. Add a regression test in
   `tests/test_dispatch_idempotency_contract.py`.
5. Run `.venv/bin/python -m pytest tests/test_dispatch_fallback_chain.py`
   to confirm the cd602c9 chaos test still passes.

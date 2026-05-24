# Runbook · provider usage normalization

**Owner:** dispatch
**Last verified:** 2026-05-24

## Symptom

Burn-rate reports show zero cached input tokens for Anthropic /
OpenAI-compat providers despite the provider's API response clearly
returning `cache_read_input_tokens` / `prompt_tokens_details.cached_tokens`.

Or: tier-cost totals look wrong by an exact factor (10x, 100x) —
usually a unit mismatch between adapter and pricing config.

## Likely cause

Each provider returns usage in its own shape; adapters normalize into
`NormalizedUsage(input_tokens, output_tokens, cached_input_tokens)`.
A wrong normalization means EVERY downstream cost report is wrong
forever. From the `substrate/dispatch/base.py` module docstring:

> If the normalization is wrong, every downstream cost report is wrong forever.

Most common normalization bugs:

1. Reading the wrong field (e.g., Anthropic's `cache_read_input_tokens`
   is at the top level; OpenAI's `cached_tokens` is nested in
   `prompt_tokens_details`).
2. Forgetting that `cached_input_tokens` is a SUBSET of `input_tokens`,
   not additional.
3. Mixing per-million and per-1000 token rate scales between the rate
   table and the adapter's cost compute (which the contract says
   adapters MUST NOT do — I-DISPATCH-6).

## Quick diagnostics

```bash
# What raw_usage shape did the adapter receive?
.venv/bin/python -c "
from substrate.event_log import recent
for e in recent(action_type='DISPATCH_CALL', limit=3):
    print(e.payload.get('provider'), e.payload.get('input_tokens'), e.payload.get('cached_input_tokens'))
"

# Pin one provider, run its adapter directly with a known prompt.
# (Provider-specific; see substrate/dispatch/providers/<name>.py
# for testable entry points.)
```

## Root-cause path

`NormalizedUsage` has exactly three fields:
`input_tokens`, `output_tokens`, `cached_input_tokens`. The provider's
raw shape must map cleanly:

- **Anthropic** returns `usage.input_tokens`, `usage.output_tokens`,
  `usage.cache_read_input_tokens`. The adapter must add
  `cache_read_input_tokens` as `cached_input_tokens` AND leave
  `input_tokens` as the TOTAL (cached + non-cached). The contract
  comment in `base.py` is explicit.
- **OpenAI-compat** returns `usage.prompt_tokens`, `usage.completion_tokens`,
  and optionally `usage.prompt_tokens_details.cached_tokens`. The
  adapter must map `prompt_tokens` → `input_tokens`,
  `completion_tokens` → `output_tokens`, and the nested cached count
  to `cached_input_tokens`.

Cost is computed downstream in the router from
`NormalizedUsage + TierConfig.pricing`. Adapters that try to compute
cost themselves break I-DISPATCH-6 and produce duplicated logic.

## Mitigation

1. Open the relevant adapter at `substrate/dispatch/providers/<name>.py`.
2. Inspect its `normalize_usage` method.
3. Compare against a raw response captured from the provider (use the
   diagnostic snippet above to fetch a recent event's `raw_usage`).
4. Add a unit test in `tests/test_dispatch.py` that pins the
   normalization for a representative response shape.
5. Re-run the burn report; the new normalization will apply to NEW
   calls only (existing event_log rows preserve the historical bug —
   we don't rewrite history).

## Reference

- Contract: `substrate/dispatch/base.py` (module docstring +
  `NormalizedUsage` dataclass)
- Decision record: `docs/decisions/dispatch_idempotency_contract.md`
  (I-DISPATCH-6 specifically)
- Tests: `tests/test_dispatch.py`, `tests/test_dispatch_idempotency_contract.py`
- Adapter modules: `substrate/dispatch/providers/`

## Worked example

```
Burn report 2026-05-24:
  anthropic/claude-opus-4.7: 12.4M input, 0 cached, 1.2M output → $58.20
```

Trace:

1. Anthropic should be returning `cache_read_input_tokens > 0` for
   any cached prompt — the operator's known to use prompt caching.
2. Open `substrate/dispatch/providers/anthropic.py`'s `normalize_usage`.
3. The bug: reading `raw_usage.get("cached_tokens", 0)` instead of
   `raw_usage.get("cache_read_input_tokens", 0)`. Anthropic returns
   the latter; `cached_tokens` is OpenAI's name.
4. Fix: read the right key. Add a unit test against a captured
   anthropic response.

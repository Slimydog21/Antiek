# DONE — wire the usage ledger into the live settle path

## Files changed

| File | What |
|---|---|
| `runtime/research_runner/provider_gateway.py` | Added optional `ByotUsageLedger` to `ResearchProviderGateway.__init__`; added `_hold_key_map` (hold_id → (api_key_id, owner_user_id)) parallel map; added `register_hold_key()` public method; added `_record_byot_usage()` defensive helper; wired call into `_settle_or_converge()` after successful settle. |
| `tests/byot/test_settle_byot_usage_wiring.py` | 6 tests covering the three acceptance cases + evidence SHA256 computation. |

## What was done

At the existing settle site (`_settle_or_converge`, where `ResearchSpendLedger.settle()` is called with authoritative `actual_cents`), the gateway now calls `ByotUsageLedger.record_settlement()` for any hold that has a registered key mapping.

**Resolution mechanism:** A parallel `hold_id → (api_key_id, owner_user_id)` map (`_hold_key_map`) is populated by callers via `register_hold_key()` at dispatch time. If no mapping exists (operator-owned routes, or callers that don't register), the settle path silently skips the BYOT recording. This keeps the audited core schema untouched (spec §5.E recommended approach).

**Defensive isolation:** `_record_byot_usage` is wrapped in `try/except Exception` that logs at DEBUG and swallows — the settle path never breaks. Mirrors the best-effort audit hook pattern used elsewhere in the codebase.

## Test results

```
tests/byot/          33 passed  (6 new wiring tests + 27 existing)
tests/test_research_provider_gateway.py   32 passed
tests/test_research_spend_ledger.py       78 passed
─────────────────────────────────────────────────────
TOTAL               143 passed, 0 failed
```

### Acceptance tests (all pass):

1. **`test_settle_with_registered_key_records_usage`** — fake settle with a resolvable key → `used_cents` incremented in the ledger.
2. **`test_settle_without_mapping_skips_gracefully`** — settle with NO registered key mapping → ledger untouched, no crash.
3. **`test_settle_without_byot_ledger_skips_gracefully`** — settle with no `ByotUsageLedger` configured → no crash.
4. **`test_settle_with_broken_ledger_does_not_break_settle`** — ledger-write exception is swallowed, settle path still completes.
5. **`test_record_byot_usage_computes_evidence_sha256`** — evidence SHA256 is computed correctly.
6. **`test_settle_via_dispatch_paid_populates_usage`** — recovery/convergence path doesn't double-count.

## Lint/type results

- `ruff check` — clean on both files.
- `mypy --strict runtime/research_runner/provider_gateway.py` — 0 errors in the gateway file (226 pre-existing errors in transitive dependencies, none in the changed file).

## Honest gaps

1. **`api_key_id` is not yet threaded from the production dispatch layer.** The `register_hold_key()` mechanism exists but no production caller invokes it yet. In the current codebase, `api_key_id` does not appear in `RunBinding`, `PaidHoldIntent`, or `PaidHoldSnapshot` (confirmed by grep on main). The cascade routes or BYOT adapter layer need to call `register_hold_key()` before dispatch to populate the mapping. This is the next wiring step (the spec §5.E "parallel-map" approach is implemented; the "write" side is missing).

2. **Convergence (idempotent replay) does not re-record BYOT usage.** If a settle is replayed (same hold, same amount), the BYOT usage was already recorded on the first settle. This is correct — no double-counting — but means that if the first settle's BYOT recording failed silently, the replay won't retry it.

3. **No `owner_user_id` resolution from the dispatch context yet.** The `register_hold_key()` call requires the caller to provide `owner_user_id`. In production, this would come from `RunBinding.owner_id`. The mapping is caller-provided, not auto-resolved.

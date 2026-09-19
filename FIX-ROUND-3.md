# FIX ROUND 3 — budget_ledger.py (post-ship review findings on PR #720)

Two findings from the live PR review. H1 is high-severity and violates the module's own
fail-closed doctrine. Implement exactly; keep all 20 tests green; gates must stay exit 0.

## H1 (HIGH) — unknown call outcome must NOT release the hold
Today `guarded_call` releases the full hold whenever `call()` raises. That is only safe when
the dispatch provably never happened. A timeout / lost response / parse failure AFTER the
provider accepted the request means money may be spent — yet the ledger records zero and
re-arms the budget. Reproduced by the reviewer: ceiling 100¢, two calls that each bill 100¢
externally then raise TimeoutError → external spend 200¢, ledger 0¢.

Fix (typed-outcome semantics, fail closed by default):
1. Export `class CallNotDispatched(Exception)` — the ONLY exception that releases the hold.
   Callers raise/wrap it when the failure is provably pre-dispatch (e.g. connection refused
   before the request was sent, local validation error). Docstring must state the burden of
   proof sits with the caller.
2. `guarded_call`:
   - `except CallNotDispatched`: release the hold (current `_release_hold` path, 'halted'
     event), re-raise.
   - `except Exception` (unknown outcome): DO NOT release. Transition the hold row
     open → 'unknown' (conditional UPDATE, same arbiter pattern), keep run-level
     `held_cents` and role `held_cents` in place (the band stays unavailable — fail closed),
     append event `unknown_outcome` (amount = projected_max), re-raise the original.
3. New reconciliation API `resolve_unknown(hold_id: str, actual_cents: int) -> RemainingBalance`:
   loads the hold row (state must be 'unknown', conditional-transition to 'settled'),
   then applies the settle math (held -= projected, spent += actual, role spent += actual,
   freed reconciliation per H2, overshoot honesty) and appends `reconciled`. `actual_cents=0`
   is the "proven never billed" case. Second resolve → RuntimeError.
4. `release(run_id)` already refuses while `held_cents > 0`, which now also covers unknown
   holds — keep that, and extend `release_role` to refuse while the role has 'open' OR
   'unknown' holds.

Tests:
21. **Reviewer's repro, defeated:** ceiling 100¢; `call()` bills an external counter 100¢
    then raises TimeoutError via guarded_call(projected=100). Assert: exception propagates,
    hold state 'unknown', held_cents==100, remaining==0; a second guarded_call(projected=100)
    raises BudgetCeilingExceeded BEFORE its call fires (spy: 0 invocations) → external spend
    can never exceed the ceiling even under repeated unknown failures.
22. **CallNotDispatched releases:** call raises CallNotDispatched → hold released, spent 0,
    held 0, 'halted' event (existing test 10 updated to use CallNotDispatched; add an
    explicit assertion that a PLAIN RuntimeError does NOT release).
23. **resolve_unknown:** after test-21 state, resolve_unknown(hold, 60) → held 0, spent 60,
    remaining 40, events include 'reconciled'; resolve again → RuntimeError;
    resolve_unknown on an 'open' hold → RuntimeError.
24. **release blocked by unknown:** release(run) with an unknown hold outstanding → raises;
    after resolve_unknown → succeeds.

## H2 (LOW, residual from round-2 review) — exact freed-pool conservation
Freed is drawn at hold time on PROJECTED excess but never reconciled at settle. Invariant to
enforce: **freed consumed == Σ actual excess over each draw's role allocation — never more,
never less, never double.**
1. Add `freed_drawn_cents BIGINT NOT NULL DEFAULT 0` to `midnight_oil_call_holds`;
   `_check_role_budget` returns the freed amount it consumed and `reserve_call` persists it.
2. In `settle` (and `resolve_unknown`): with `role_part = projected_max - freed_drawn`,
   compute `actual_excess = max(0, actual - role_part)`, `delta = actual_excess - freed_drawn`.
   - `delta < 0`: refund `-delta` to `freed_cents` (same txn), event `freed_refund`.
   - `delta > 0` (overshoot beyond projection): best-effort conditional consume
     `min(delta, freed_available)` — never raise (the money is already spent); include the
     unconsumed shortfall in the `overshoot` event's honesty (it's role-budget overshoot).
3. Plain `debit` path is already exact (consumes on actual) — do not change it.

Tests:
25. **Refund:** role budget 100¢, freed 60¢ (from a released sibling): hold projected 160
    (draws 60 freed), settle actual 100 → freed back to 60 (full refund), events show
    `freed_refund` 60.
26. **Partial:** same setup, settle actual 130 → actual excess 30, refund 30, freed==30.
27. **Overshoot draw:** hold projected 100 (role_part 100, no freed drawn), settle actual
    140 with freed 20 available → freed consumed 20 (best-effort), overshoot event present,
    freed==0, run spent==140.

## Gates & wrap-up
- pytest full file (now ~27 tests) · declared_bar ruff + mypy exit 0 (commands in FIX-ROUND-1
  history: `python -m tools.lints.declared_bar enforce ruff|mypy --baseline-file
  tools/lints/baselines/declared_{ruff,mypy}.json`).
- Update docs/decisions/midnight-oil-budget-ledger-red-proof.md: neuter the `except
  CallNotDispatched`→`except Exception` distinction (make generic exceptions release again)
  → test 21 goes red → restore → green. Record verbatim.
- Do NOT git commit. Report per-finding with verbatim gate tails.

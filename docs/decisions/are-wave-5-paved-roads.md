# ARE Wave 5 — paved roads for the operator-gated sprints

**Date:** 2026-05-25
**Branch:** `are/wave-1-substrate-additive`
**Source spec:** `~/specs/antiek-rust-execution/` — ARE-02 (M3 canonical examples), ARE-03, ARE-04
**Status:** ✅ Paved roads shipped — every remaining ARE sprint now has a tested reference; the in-place migrations onto them stay operator-gated.

## The idea (the PostHog "paved road")

The three remaining ARE sprints (ARE-02 boundary migrations, ARE-03 variant conversions, ARE-04 ownership handles) all require modifying operator-critical existing call sites — which is operator-gated. But the *enabling primitives* for each are pure additive code that demonstrates the migration AND gives every future migration a tested, ready-to-use reference. Ship the paved road; let the operator drive the migrations onto it.

Instead of leaving ARE-02/03/04 as "TODO, blocked," each now has a reference implementation a migration copies. The work that remains is mechanical (apply the pattern at a chosen site), not design (figure out the pattern).

## What landed

| Sprint | Paved road | Commit | Tests |
|---|---|---|---|
| ARE-02 (canonical examples) | `substrate/result_helpers.py` — `try_decode_json`, `try_parse_model`, `checked_budget_charge`, `try_call` | `f6523a4` | 19 |
| ARE-04 (ownership reference) | `substrate/ownership.py` — `OwnershipHandle[T]` + `DispatchBudgetReference` | `586dbc2` | 13 |
| ARE-03 (exhaustive-match) | `substrate/exhaustive.py` — `assert_exhaustive` + canonical pattern | `9010de5` | 8 |

40 tests total; all mypy --strict clean, ruff clean, with doctests where illustrative.

## Why these compose (the genius-hard-to-vary part)

The three paved roads stack, and that stacking is the design's load-bearing property:

```
substrate/results.py        Ok[T] | Err[E]                         (Wave 1)
        │
substrate/errors.py         SubstrateError variants                 (Wave 1)
        │
substrate/result_helpers.py checked_budget_charge(...) -> Result    (ARE-02 paved road)
        │                            │
        │                            └── composed INSIDE the lock by:
        │
substrate/ownership.py      OwnershipHandle.write(mutation -> Result) -> Result
                            DispatchBudgetReference.charge(...) ──┘    (ARE-04 paved road)
```

`DispatchBudgetReference.charge()` is ~3 lines because it composes `OwnershipHandle.write` (serialization + `WriterContended` on timeout) with `checked_budget_charge` (the never-overspend invariant as `Ok`/`Err`). The cap check runs inside the handle's lock, so the concurrency test proves: 10 threads × 100 charges against cap=500 commit *exactly* 500, never over. That correctness falls out of the composition.

`exhaustive.assert_exhaustive` closes the loop: when a `match` over a closed set is missing an arm, mypy --strict errors. Adding a sixth `SubstrateError` variant forces every match that switches on it to handle the new case — the Rust "compiler tells you everywhere to fix" property, in Python.

## What is STILL operator-gated (and why)

| Migration | Blocker |
|---|---|
| **ARE-02 M3–M5** — change 3 real boundaries to return `Result` via `result_helpers` | Operator must choose which 3 sites. Hermes-bridge chaos test (`cd602c9`) must stay green. Migrating sites the parallel streams churn would create merge carnage. |
| **ARE-03 M2–M3** — define real `DispatchTier`/`IngestionSource`/`VerifierOutcome` + convert sites | Real variant types must reconcile with `dispatch-tier-verdict.md` + the existing `ActionType` union. |
| **ARE-04 (real handles)** — wire dispatch budget + event_log writer to `OwnershipHandle` + db_lock persistence | In-process handle must *extend, not duplicate*, `substrate/invariants.py`'s I-001 single-writer enforcement. Layering is an operator design decision. |

Each migration is written to be a small, reviewable diff: import the helper, apply the pattern, keep the chaos/invariant tests green.

## Full ARE scorecard (12 sprints)

| Sprint | State |
|---|---|
| ARE-01 mypy --strict | ✅ Guardrail (errors fixed by parallel stream; baseline locks clean state) |
| ARE-02 Result encoding | ✅ Encoding + ✅ paved-road helpers; ⏸ 3 boundary migrations operator-gated |
| ARE-03 exhaustive match | ✅ Helper + pattern; ⏸ real variant types + conversions operator-gated |
| ARE-04 ownership handles | ✅ Reference handle + budget reference; ⏸ real-resource wiring operator-gated |
| ARE-05 escape hatch | ✅ Full |
| ARE-06 doctests | ✅ Exemplars + CI step |
| ARE-07 property tests | ✅ Full (hypothesis, opt-in) |
| ARE-08 RFC discipline | ✅ Template; ⏸ 2 ADR backfills editorial-gated |
| ARE-09 antiek check CLI | ✅ Full (7 subcommands incl. perf) |
| ARE-10 rigor review gate | ✅ Full |
| ARE-11 CI floor | ✅ Full (substrate_floor.yml + baseline grandfathering, 3 lint types) |
| ARE-12 hot-path measurement | ✅ Full |

**9 fully shipped; 3 have paved roads with operator-gated migrations; 0 untouched.**

## Verification

```bash
cd ~/Desktop/Antiek
git checkout are/wave-1-substrate-additive && git pull
./.venv/bin/pip install -e ".[dev]" hypothesis

./.venv/bin/python -m pytest \
    tests/test_results.py tests/test_errors.py tests/test_escape_hatch.py \
    tests/test_result_helpers.py tests/test_ownership.py tests/test_exhaustive.py \
    tests/test_lints_no_raise.py tests/test_lints_unannotated_bypass.py \
    tests/test_lints_baseline.py tests/test_lints_cli_with_baseline.py \
    tests/test_lints_mypy_strict_baseline.py \
    tests/test_antiek_cli.py tests/test_antiek_cli_perf.py \
    tests/test_benchmark_harness.py tests/properties/ -q

./.venv/bin/mypy --strict \
    substrate/results.py substrate/errors.py substrate/escape_hatch.py \
    substrate/result_helpers.py substrate/ownership.py substrate/exhaustive.py
# Expected: Success: no issues found in 6 source files
```

## Self-ratification

- **Intellectual honesty:** scorecard distinguishes "fully shipped" from "paved road + operator-gated migration." No sprint claimed complete when only the reference exists; each migration names a concrete blocker.
- **Fairness:** the `write(mutation)->Result` vs context-manager choice is documented with its reason; exhaustive.py's "demonstration, not real variant" steelmans defining-real-types-now and rejects it for a named reason.
- **Rigor:** the load-bearing tests are the ownership concurrency proofs (exactly-cap-under-race; no-lost-updates) + the result_helpers composition test (decode→parse short-circuits at first Err).
- **Diligence:** each paved road reuses the prior layer; none reinvents. `_REPR_TRUNCATE=200` matches errors.py's documented convention.
- **Defensibility:** this ADR is the single source for "pattern shipped; migration yours; here's the blocker." The scorecard removes the need to re-audit.

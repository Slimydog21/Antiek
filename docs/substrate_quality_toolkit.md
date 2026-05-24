# Substrate quality toolkit

The reliability discipline from the Pragmatic Engineer × Alice Ryhl (Rust / Tokio) interview, shipped as Python idioms for the Antiek substrate. This is the **one page** to read before writing substrate-boundary code — it shows how the pieces fit and which paved road to take.

Source spec: `~/specs/antiek-rust-execution/`. Per-decision rationale: `docs/decisions/are-*.md`.

## TL;DR — which tool when

| You are… | Reach for | Module |
|---|---|---|
| Returning success-or-failure from a substrate boundary | `Ok(value=...)` / `Err(error=...)` | `substrate/results` |
| Naming a failure mode | a `SubstrateError` variant | `substrate/errors` |
| Wrapping a raise-on-failure call (json, pydantic, an SDK) | `try_decode_json` / `try_parse_model` / `try_call` | `substrate/result_helpers` |
| Enforcing a pure invariant (never overspend) | `checked_budget_charge` (or write your own `… -> Result`) | `substrate/result_helpers` |
| Serializing writes to a shared mutable resource | `OwnershipHandle` | `substrate/ownership` |
| Dispatching on a closed set of variants | `match` + `assert_exhaustive` | `substrate/exhaustive` |
| Bypassing a substrate invariant on purpose | `@escape_hatch(reason=...)` | `substrate/escape_hatch` |
| Verifying your change | `antiek check` | `tools/antiek_cli` |

## The error model — values, not exceptions

Substrate boundaries return `Result[T, SubstrateError]` instead of raising. The caller handles both arms with `match`; there is no silent error path.

```python
from substrate.results import Ok, Err, Result
from substrate.errors import SubstrateError, BudgetExceeded

def charge(amount: int, budget: int) -> Result[int, SubstrateError]:
    if amount > budget:
        return Err(error=BudgetExceeded(cap=budget, attempted=amount))
    return Ok(value=budget - amount)

match charge(150, 100):
    case Ok(value=remaining):
        ...                      # remaining is int
    case Err(error=BudgetExceeded(cap=cap)):
        ...                      # narrow on the variant directly
```

**When to return Result vs raise** (the error-channel rule):

- **Return `Result`**: substrate writes, dispatch adapter calls, verifier outcomes — anything where failure is a normal, expected branch the caller must handle.
- **Raise**: genuine system failure (`OSError`, `MemoryError`), shutdown signals (`KeyboardInterrupt`, `SystemExit`), and programmer-error invariants (`AssertionError`, `NotImplementedError`). These aren't recoverable branches; let them propagate.

`.unwrap()` on an `Err` raises `ResultUnwrapError` — it's for sites you've *proven* can't fail, not for skipping the failure arm. Use `.unwrap_or(default)` or `match` otherwise.

The `no_raise_in_substrate_writers` lint enforces this: a `raise` of a non-system exception in a protected path is flagged (see "Enforcement" below).

## The SubstrateError variants

Five seed variants in `substrate/errors.py`, alphabetical by `kind` (so parallel sessions don't merge-conflict adding variants):

| Variant | When |
|---|---|
| `BudgetExceeded(cap, attempted, units)` | a spend would exceed a budget cap |
| `SchemaMismatch(field, expected_type, actual_repr, schema_version)` | input doesn't match the expected schema |
| `UpstreamUnavailable(upstream, status_code?, reason?)` | an external API/source is unreachable |
| `VerifierTimeout(verifier, elapsed_s, timeout_s)` | a verifier missed its deadline |
| `WriterContended(resource, holder_pid?, timeout_s)` | a writer couldn't acquire the lock in time |

Add a variant: define a Pydantic model with `kind: Literal["new_kind"]`, add it to the `SubstrateError` union. Every `match` over `SubstrateError` that uses `assert_exhaustive` will then fail `mypy --strict` until it handles the new arm — the "compiler tells you everywhere to fix" property.

## The paved-road helpers — adopt Result without boilerplate

Don't hand-roll try/except→Err. Use `substrate/result_helpers`:

```python
from substrate.result_helpers import (
    try_decode_json, try_parse_model, checked_budget_charge, try_call,
)

# stdlib raise-on-failure → Result
match try_decode_json(raw_llm_output):
    case Ok(value=data): ...
    case Err(error=e): ...           # SchemaMismatch with the bad input

# Pydantic validation → Result
result = try_parse_model(MyModel, data)   # Err(SchemaMismatch) names the bad field

# pure invariant → Result
checked_budget_charge(current_spend=50, amount=30, cap=100)   # Ok(80)
checked_budget_charge(current_spend=80, amount=30, cap=100)   # Err(BudgetExceeded)

# bespoke SDK call → Result
try_call(lambda: third_party.fetch(), on_error=lambda exc:
         UpstreamUnavailable(upstream="thirdparty", reason=str(exc)))
```

They **compose** — chain with `.and_then`, short-circuiting at the first `Err`:

```python
result = try_decode_json(raw).and_then(lambda d: try_parse_model(MyModel, d))
# Ok(model) on success; the first Err (decode OR parse) otherwise.
```

## Ownership handles — one writer per shared resource

Generalizes `runtime/db_lock.py`'s single-writer discipline. Every shared mutable resource gets one `OwnershipHandle`; pass the handle, never the raw value.

```python
from substrate.ownership import OwnershipHandle, DispatchBudgetReference
from substrate.results import Ok

h: OwnershipHandle[int] = OwnershipHandle(0, name="my_resource")

h.read()                                   # lock-free snapshot
h.write(lambda v: Ok(value=v + 1))         # serialized; returns Result
# on lock-acquire timeout → Err(WriterContended)
# if the mutation returns Err → state unchanged, Err propagated
```

The mutation callback returns a `Result`, so a domain invariant composes *inside* the lock. `DispatchBudgetReference` is the reference: `charge()` runs `checked_budget_charge` under the handle's lock, so concurrent charges can't race past the cap (proven by property test over arbitrary cap/thread shapes).

```python
budget = DispatchBudgetReference(cap=1000)
budget.charge(250)        # Ok(250)
budget.spent             # 250
budget.remaining         # 750
```

## Exhaustive match — the compiler tells you everywhere to fix

For a **closed set** of variants (a fixed list where adding one is a deliberate, reviewable event), use `match` + `assert_exhaustive`:

```python
from typing import Literal
from substrate.exhaustive import assert_exhaustive

Tier = Literal["standard", "verify", "fallback"]

def route(tier: Tier) -> str:
    match tier:
        case "standard": return "..."
        case "verify":   return "..."
        case "fallback": return "..."
        case _:          assert_exhaustive(tier, context="route")
```

Add `"premium"` to `Tier` and `mypy --strict` errors on `route` until you handle it. **Closed-set only** — open-set plug-in dispatches (adapter registries) use a `dict` registry and intentionally don't get this treatment.

## Audited escape hatches — the bounded `unsafe`

Sometimes you must bypass a substrate invariant (a maintenance script writing outside the coordinator, a benchmark skipping the retry budget). Mark it:

```python
from substrate.escape_hatch import escape_hatch
import duckdb

with escape_hatch(reason="weekly-compaction-needs-raw-duckdb-write"):
    con = duckdb.connect(path)
    con.execute("VACUUM")

# or as a decorator
@escape_hatch(reason="benchmark-bypasses-retry-budget-for-timing")
def measure() -> float: ...
```

First hit per reason logs a WARNING (greppable in prod logs); the `unannotated_bypass` lint flags any `duckdb.connect` / `requests.*` / `urllib.request.urlopen` *not* inside an escape hatch.

## Verifying your change — `antiek check`

One CLI wraps the whole verification surface (the Cargo-equivalent):

```bash
python -m tools.antiek_cli check --help          # list subcommands
python -m tools.antiek_cli check types --scope substrate/foo.py --strict
python -m tools.antiek_cli check tests --scope tests/test_foo.py
python -m tools.antiek_cli check lint  --scope substrate/foo.py
python -m tools.antiek_cli check doctest --scope substrate/foo.py
python -m tools.antiek_cli check props           # hypothesis property tests
python -m tools.antiek_cli check perf            # ARE-12 benchmark harness
python -m tools.antiek_cli check all --scope substrate/   # everything, one report
```

## Enforcement — the substrate floor

`.github/workflows/substrate_floor.yml` runs the floor on every PR touching substrate-quality paths: ruff, `mypy --strict`, the baseline-enforced lints, the unit + property + doctest suites, and the invariants check.

The lints use **baseline grandfathering** — `tools/lints/baselines/*.json` capture today's tolerated violations; CI fails only on *new* ones. To extend a lint to a new path:

```bash
# capture today's violations as grandfathered
python -m tools.lints.cli_with_baseline capture no_raise \
    --paths substrate/newpkg/ --baseline-file tools/lints/baselines/no_raise.json
# CI then fails only on NEW violations in substrate/newpkg/
```

The `mypy_strict_baseline` does the same for type errors — substrate core (`db_lock` + `event_log`) is at **zero** grandfathered errors, so any new strict error there fails CI.

## Property-based testing — invariants over the input space

The strong tests are properties, not examples. `tests/properties/` (hypothesis, opt-in: `pip install hypothesis`) proves invariants hold for *all* inputs:

- `checked_budget_charge` never commits over cap (200 examples).
- `OwnershipHandle` has no lost updates under arbitrary concurrency.
- `DispatchBudgetReference` never exceeds cap under arbitrary cap/thread shapes.
- `try_decode_json` round-trips any serializable value and is total over any string.

When you add a substrate invariant, add a property — that's the antithesis/Hegel discipline the Rust interview argued complements the type checker.

## Governance — when a change needs an RFC

Non-trivial changes (touching a substrate invariant, a new package, a public API, a new integration, a new dependency) use the RFC template at `docs/RFC_TEMPLATE.md` (9 sections + a 5-value ratification block). The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) asks one calibrated question per rigor value; the operator review checklist (`docs/operator_review_checklist.md`) is the merge-side companion.

## Module map

| Module | Purpose | ADR |
|---|---|---|
| `substrate/results.py` | `Ok`/`Err`/`Result` | `are-wave-1-substrate-additive.md` |
| `substrate/errors.py` | `SubstrateError` variants | `are-wave-1-substrate-additive.md` |
| `substrate/escape_hatch.py` | audited bypass marker | `are-wave-1-substrate-additive.md` |
| `substrate/result_helpers.py` | paved-road adapters | `are-wave-5-paved-roads.md` |
| `substrate/ownership.py` | ownership handles | `are-wave-5-paved-roads.md` |
| `substrate/exhaustive.py` | exhaustive-match helper | `are-wave-5-paved-roads.md` |
| `tools/lints/` | no_raise, bypass, baseline, mypy_strict | `are-wave-2-tooling-additive.md`, `are-01-mypy-strict-guardrail.md` |
| `tools/antiek_cli/` | `antiek check` CLI | `are-wave-2-tooling-additive.md` |
| `tools/benchmarks/hot_paths/` | perf harness | `are-12` in `hot_path_language.md` |
| `.github/workflows/substrate_floor.yml` | CI floor | `are-wave-4-ci-floor-and-baselines.md` |

## What's deliberately NOT done (operator-gated)

The *patterns* above are shipped + tested. The *migrations of existing code* onto them are operator-gated — they modify operator-critical files (`runtime/db_lock.py`, dispatch adapters, verifiers) and need site selection + invariant/chaos-test review. See `are-wave-5-paved-roads.md` for the per-migration blocker. To migrate a boundary: import the helper, apply the pattern, keep the relevant invariant + chaos tests green.

# ARE Wave 1 — substrate-additive Rust-discipline modules

**Date:** 2026-05-24
**Branch:** `are/wave-1-substrate-additive`
**Source spec:** `~/specs/antiek-rust-execution/` (Antiek Rust-Execution Spec; sibling-execution to `~/specs/antiek-tech-philosophy/`)
**Status:** ✅ Wave 1 partial-landing — three additive modules + ADR. Remaining ARE work deferred.

## Summary

This commit (and the two preceding it on the same branch) lands the **additive, low-risk portion** of ARE-02 (Result encoding) and ARE-05 (escape-hatch convention) from the Antiek Rust-Execution Spec. No existing substrate file was modified. No invariant was touched. The single-writer invariant (critical invariant #1 in `CLAUDE.md`) is intact, and `python -m substrate.invariants` reports `6 invariants checked, 0 violation(s)` against this branch.

## Motivation

The Pragmatic Engineer interview with Alice Ryhl (Tokio / Rust language-team adviser) surfaced two design-discipline patterns that Antiek's substrate could ship as Python idioms without language migration:

1. **Errors as values** — explicit `Result<T, E>` return at substrate boundaries; callers handle the failure arm by destructure, not by `try/except` that may or may not exist.
2. **Audited escape hatches** — Rust's `unsafe` doesn't disable type checking, it just permits a few extra operations the caller must audit. Antiek's substrate has analogous bypass sites (direct DuckDB writes outside the coordinator, raw HTTP outside the gateway, unverified LLM consumption) that today are scattered and unmarked.

Both pattern adoptions ship as **net-new modules** in `substrate/` with full test coverage. The harder follow-on work — refactoring existing call sites to return `Result` and annotating known bypass sites with `@escape_hatch` — is intentionally **deferred** to dedicated follow-on sessions so the operator can review the diff at each boundary before it lands.

## What landed

| File | Lines | Tests | Purpose |
|---|---|---|---|
| `substrate/results.py` | 197 | 24 | `Ok[T]` / `Err[E]` Pydantic discriminated union + `ResultUnwrapError` + combinators |
| `substrate/errors.py` | 117 | 13 | `SubstrateError` union: 5 variants (BudgetExceeded, SchemaMismatch, UpstreamUnavailable, VerifierTimeout, WriterContended) |
| `substrate/escape_hatch.py` | 175 | 15 | `escape_hatch(reason=...)` as both decorator and context manager (`ContextDecorator`); per-reason single-warning + thread-safe counter |
| `tests/test_results.py` | 273 | — | Construction, predicates, extractors, combinators, match-case, JSON round-trip, frozen invariant, realistic boundary example |
| `tests/test_errors.py` | 173 | — | Each variant constructs + serializes; union resolves on `kind` discriminator |
| `tests/test_escape_hatch.py` | 211 | — | Context + decorator forms; warn-once; validation; exception propagation; thread-safety smoke |

**Test result:** 52/52 new tests pass. `mypy --strict` clean on all three modules. Substrate invariants suite: 6/6 pass, 0 violations.

## Guide-level explanation (Rust-RFC style)

### Returning a Result

```python
from substrate.results import Ok, Err, Result
from substrate.errors import SubstrateError, BudgetExceeded

def charge(amount: int, budget: int) -> Result[int, SubstrateError]:
    if amount > budget:
        return Err(error=BudgetExceeded(cap=budget, attempted=amount))
    return Ok(value=budget - amount)

match charge(150, 100):
    case Ok(value=remaining):
        ...  # remaining is int
    case Err(error=BudgetExceeded(cap=cap, attempted=att)):
        ...  # narrow on the variant directly
```

### Marking an audited bypass

```python
from substrate.escape_hatch import escape_hatch
import duckdb

# context form
def maintenance_compaction(db_path: str) -> None:
    with escape_hatch(
        reason="weekly-compaction-needs-raw-duckdb-write-outside-coordinator"
    ):
        con = duckdb.connect(db_path, read_only=False)
        con.execute("VACUUM")
        con.close()

# decorator form
@escape_hatch(reason="benchmark-harness-bypasses-retry-budget-for-timing")
def measure_raw_latency(url: str) -> float:
    ...
```

## Reference-level explanation

### Result encoding choice — Pydantic discriminated union, not `returns` library

The spec's ARE-02 milestone 1 called for picking the encoding. The candidates were (a) the `returns` library, (b) a custom frozen `dataclass` pair, (c) a Pydantic discriminated union over `Ok` / `Err` classes. We picked (c).

**Why Pydantic over `returns`:** Pydantic serialization is already the wire format on every cross-module hand-off in the substrate (event_log rows, dispatch envelopes, verifier outcomes all use Pydantic). Introducing a parallel encoder for the `returns` types would have multiplied the round-trip surface without buying anything mypy didn't already give us. The cost was approximately 200 lines of `Ok` / `Err` definitions, plus a few combinators — much less than the integration cost of a parallel encoder.

**Why discriminated union over a single `Result` class with internal tag:** Two separate classes (`Ok`, `Err`) give Pydantic the auto-generated `__match_args__` that `case Ok(value=v):` needs. A single-class encoding would need manual `__match_args__` plus explicit field-extraction predicates. The discriminated-union shape also mirrors `substrate.event_log`'s `ActionType`-discriminated `Event`, so the codebase has one idiom to learn.

**`unwrap()` semantics:** Calling `.unwrap()` on `Err` raises `ResultUnwrapError` — a **programmer-error** signal, not a runtime-error path. The discipline is that `.unwrap()` is for sites the caller has proven (by prior `if result.is_ok():` or by domain knowledge) cannot fail. Reaching `.unwrap()` on `Err` is a logic bug, not a recoverable condition. The exception preserves the inner error on `.inner` so debuggers don't lose context.

### SubstrateError variant catalog

Five variants seed the union; each is a Pydantic model discriminated on a literal `kind` field. The seed set covers the failure modes that already exist somewhere in the codebase as hand-rolled exception types or ad-hoc `(value, error)` tuples:

- `BudgetExceeded(cap, attempted, units)` — dispatch budget overflow
- `SchemaMismatch(field, expected_type, actual_repr, schema_version)` — writer-side schema drift
- `UpstreamUnavailable(upstream, status_code?, reason?)` — external API failure
- `VerifierTimeout(verifier, elapsed_s, timeout_s)` — verifier missed deadline
- `WriterContended(resource, holder_pid?, timeout_s)` — coordinator lock acquire timeout

Adding a new variant is cheap: define a Pydantic model with `kind: Literal["new_kind"]` and add it to the `SubstrateError = Union[...]` line. Variants are alphabetical by `kind` to make merges from parallel sessions trivial — the Schelling-point ordering eliminates conflicts.

### Escape-hatch — `ContextDecorator`, not two separate names

The spec called for `@escape_hatch(reason=...)` decorator and `escape_hatch(reason=...)` context manager. The Pythonic answer to "I want both" is `contextlib.ContextDecorator`. Subclassing it lets a single instance work as both, no name duplication, no third-party dep.

The decorator-form `__call__` semantics (inherited from `ContextDecorator`) wrap the function such that each invocation enters and exits the context — every call records one hit. A function decorated with `@escape_hatch(reason="x")` that's called 1000 times has 1000 hits and one warning. This is the right semantics: counts reflect actual bypass activity, warnings don't spam.

### Why single-warning-per-reason-per-process

The marker exists for two purposes: an audit-doc reconciliation signal (operator greps logs for `escape_hatch first hit` strings) and a CI lint anchor. Both purposes are served by the first hit. Subsequent hits are recorded in the counter for observability dashboards but don't re-warn — that would drown out signal.

The thread-safety story: `_state_lock` is a `threading.Lock` protecting the `_seen` set and `_counts` dict. The lock granularity is coarse (entire `_record` call) because the operations are O(1) and not on a hot path. The actual logging call happens *outside* the lock — handlers can be slow / I/O-bound, and serializing hatches across threads on logger latency would be wrong.

## Drawbacks

1. **Two parallel Result types could emerge.** A future session might add a third Result-shaped encoding under `substrate/` without seeing this one. Mitigation: this ADR is now the authoritative source; ARE-09 (`antiek check` CLI, deferred) is intended to grep for parallel encodings as a lint.
2. **Pydantic's frozen=True raises ValidationError on assignment.** Tests use `pytest.raises(Exception)` for portability across Pydantic minor versions. If Pydantic ever changes the raised type, the test still passes but the assertion narrows; this is acceptable.
3. **The escape-hatch marker is light-touch by design.** It does not prevent the bypass at runtime; it logs and counts. At single-operator scale this is the right trade-off (per the spec's analysis). The verdict flips to strict enforcement when a second engineer joins.
4. **`SubstrateError` is closed at the union site.** Adding a variant requires editing `substrate/errors.py`. This is intentional — the closed shape is what gives `match` exhaustiveness — but means downstream packages can't add their own variants without amending the union.

## Rationale and alternatives

| Alternative considered | Why rejected | Reconsider if |
|---|---|---|
| `returns` library | Parallel serialization surface; ecosystem split with Pydantic | mypy's narrowing of generic Pydantic Results turns out to be worse than `returns`'s mypy plugin in practice |
| Frozen dataclass pair | No free Pydantic serialization; cross-module hand-off would need a custom encoder | The substrate stops carrying Result types across Pydantic boundaries |
| Single `Result` class with internal tag | Lose `__match_args__`-driven destructure; needs manual extraction | Match ergonomics turn out to be unimportant in practice |
| Two separate names (`escape_hatch` + `escape_hatch_decorator`) | Less ergonomic; users have to remember which form | A `ContextDecorator`-shaped class confuses readers |
| Runtime enforcement of escape-hatch | Wrong for single-operator scale; would require a privileged-flag system | A second engineer joins; the convention starts being violated silently |

## Prior art

- `runtime/db_lock.py` — already exemplary; the single-writer invariant is enforced via `flock` + sidecar lock file. This branch did not modify it.
- `substrate/schemas/events.py` — already uses Pydantic discriminated union over `ActionType`. The `Ok` / `Err` encoding mirrors this shape so the codebase has one idiom.
- `substrate/invariants.py` (SPR-E1 of `~/specs/antiek-hashimoto-engineering/`, landed 2026-05-24 from a parallel session) — the 6 invariants enforced mechanically. Compatible with this branch; ran on this commit, 0 violations.

## Unresolved questions

1. **Should the existing `WriteLockTimeout` / `WriteCoordinatorTimeout` exception in `runtime/db_lock.py` be translated to a `WriterContended` `Result.Err` at the coordinator boundary?** Probably yes, but that is the deferred ARE-02 refactor work — it touches existing call sites and needs operator review of which sites flip to Result-return.
2. **Should `substrate/escape_hatch.py` integrate with `substrate/invariants.py` so that bypass hits show up in the invariants report?** Possible follow-on; would be a small extension.
3. **Should the AST lint (`tools/lints/unannotated_bypass.py`) be shipped in the same wave?** The spec scheduled it inside ARE-05 milestone 5. It was held out of this commit because it requires careful audit-doc design and would have made the commit too big to review. Deferred to a follow-on session.

## Future possibilities

- **`?` operator** via a `try_` decorator that destructures and short-circuits on `Err`, mirroring Rust's `?`. Cost is one decorator, benefit is shorter chain prose; weigh after first 10 boundary sites adopt the Result type.
- **`Result[..., SubstrateError]` as the substrate-public-API return convention.** When ARE-02's deferred refactor runs, every substrate-boundary function's return type bumps to `Result[T, SubstrateError]` and the existing exception-raising paths translate to `Err(error=...)`.
- **Stateful escape-hatch observability** — counter snapshots surfaced in `runtime/weekly_report.py` so operators see bypass trends without grepping logs.

## Ratification (per RFC discipline)

Self-ratification against the 5-value rigor rubric:

- **Intellectual honesty:** This branch ships ~700 lines (3 modules + 3 test files + 1 ADR). It does NOT ship the deferred refactor work — that is explicit and called out above. The handoff does not claim "Result types adopted across substrate"; it claims "Result encoding exists, three callers and the audit doc are deferred." Mypy strict baseline reveals 35 errors in existing substrate-core code; that is documented as a separate finding, not silently fixed.
- **Fairness:** The `returns`-library steelman is in the rationale section; the verdict to use Pydantic is defended specifically (substrate already on Pydantic) rather than by momentum. The light-touch escape-hatch verdict is similarly defended against the strict-enforcement alternative.
- **Rigor:** 52/52 tests pass. mypy --strict clean on all 3 new modules. Invariants suite (6/6) green. Thread-safety smoke test exercises 400 concurrent hatch entries. Frozen invariants tested. Pydantic JSON round-trip tested per variant.
- **Diligence:** Read `runtime/db_lock.py` (570 lines) and `substrate/event_log/__init__.py` before designing — discovered they already use Pydantic-discriminated unions. Read existing 8 ADRs in `docs/decisions/`. Read CLAUDE.md including the new `<!-- BEGIN: invariants-pointer -->` block. Did not invent a parallel pattern.
- **Defensibility:** The drawbacks + rationale + rejected alternatives sections record the decisions a future maintainer would want to second-guess. The deferral list is explicit so the next session knows what's left. Invariants suite ran before this ADR was written.

**Ratified:** ✅ pending operator review of branch `are/wave-1-substrate-additive`.

## Out of scope for this branch (deferred to follow-on sessions)

The following ARE spec items are NOT landed here and need separate sessions for operator-reviewed PRs:

- **ARE-01:** Fix the 35 `mypy --strict` errors in `substrate/event_log/events.py` + `runtime/db_lock.py`. Strict is configured globally in `pyproject.toml` but mypy was not installed in the venv prior to this session, so strict has never been enforced. The fixes are mostly missing return-type annotations (`-> None`) and a few real type-narrowing issues; one site (`runtime/db_lock.py:510`) appears to pass an `Optional[str]` to `open()` and should be reviewed by the operator before touching `runtime/db_lock.py` (critical invariant #1).
- **ARE-02 milestones 3–5:** Refactor one substrate writer + one dispatch adapter + one verifier to return `Result[T, SubstrateError]`. Requires operator selection of which three sites are canonical (the Hermes-bridge chaos test at commit `cd602c9` MUST still pass).
- **ARE-02 milestone 7:** AST lint (`tools/lints/no_raise_in_substrate_writers.py`) — needs the writer migration above first or it has nothing to enforce.
- **ARE-03:** Inventory + convert variant-typed dispatches (dispatch tier, ingestion source, verifier outcome) to `match` + `assert_never`. Some of this is already done (the existing `ActionType` discriminated union); needs an audit pass.
- **ARE-04 — ARE-12:** All Wave 2–5 sprints. See `~/specs/antiek-rust-execution/index.html` for the full plan.

## Reproducibility

```bash
# Run new tests
./.venv/bin/python -m pytest tests/test_results.py tests/test_errors.py tests/test_escape_hatch.py -v

# Verify mypy --strict clean on new modules
./.venv/bin/mypy --strict substrate/results.py substrate/errors.py substrate/escape_hatch.py

# Verify substrate invariants intact
./.venv/bin/python -m substrate.invariants
./.venv/bin/python -m pytest tests/test_invariants.py -v
```

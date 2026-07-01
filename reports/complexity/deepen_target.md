# Deepen target — Ousterhout Ch. 8 "pull complexity downward" (AOD SPR-04)

**Date:** 2026-07-01. Target chosen from SPR-01 `top_unfenced`.

## Selection

`top_unfenced[0]` = `substrate/graph/ops.py` — shallow (ratio 0.333, the shallowest
unfenced load-bearing module), hot (churn 3), 14 public `insert_*` functions. It
IS a genuine deepening target (its callers repeat the same ceremony), NOT a
correctly-small module, so no substitution is needed.

**Scope of this deepening — the interview sub-family.** The full insert-family
has ~57 production call sites; migrating all of them + removing 14 public
functions in one test-locked pass would gamble the ~5000-test suite (a craft-bar
violation). Instead I deepen the module's most **cohesive, self-contained**
sub-interface: the interview lifecycle (`insert_interview_project`,
`insert_interview`, `append_interview_turn`, `complete_interview`) — 4 public
functions whose callers are all interview-specific (18 call sites across
`interfaces/research/api/app.py`, `substrate/speak/project.py`, and the interview
test files + the `substrate.graph` re-export). This reduces graph/ops's public
symbol count while keeping the migration bounded and verifiable.

## The caller ceremony being pulled down

Each of the four free functions repeats:
1. `_assert_write_locked(con)` — the caller threads a `LockedConnection` into
   every call and the lock is re-asserted on each one.
2. `id = supplied or new_random_id(prefix)` — id derivation re-done per call.
3. `_maybe_json(...)` JSON coercion (the SPR-02-flagged leaked helper).

A caller running an interview does the whole `project → interview → turn →
complete` lifecycle, threading `con` and re-deriving ids at every step.

## The deepening

Introduce **`InterviewWriter`** (SPR-06's chosen GraphWriter facade, scoped to
interviews), bound to a locked connection:
- `__init__(con)` asserts the write lock ONCE (not per call).
- `.project(...) / .interview(...) / .turn(...) / .complete(...)` — the lifecycle
  as cohesive methods; `con` is held, not re-passed; ids + JSON coercion absorbed.

The four free functions are removed; every call site migrates to
`InterviewWriter(con).<step>(...)`.

## Mechanical success (SPR-01 metric)

Before: 4 top-level functions (4 symbols) + 19 params → `interface_surface` ≈
4 + 19×0.5 = **13.5** contribution.
After: 1 class (1 symbol) + 4 methods (4×0.5) + 16 params (`con` dropped from each
signature) → ≈ 1 + 2 + 8 = **11**.
Net `interface_surface` DOWN; ratio holds/deepens (never regresses — verified by
`--check-regression`, which only fails on SHALLOWER).

## Call-site list (migrated in M4)

- `interfaces/research/api/app.py:3223,3343,3420,3457` (the interview API flow)
- `substrate/speak/project.py:66` (Speak project wraps `insert_interview_project`)
- `substrate/graph/__init__.py` re-export (imports + `__all__`)
- tests: `test_async_interview.py`, `test_speak_fk_regression.py`,
  `test_speak_consent.py`, `test_sprint16_interviews.py` (+ any transitive)

## Behavior preservation

The method bodies are byte-identical SQL to the free functions (only `con` →
`self._con`, lock asserted at construction). Green-before: 56 interview tests
pass on unchanged code. Green-after: same suite + full suite.

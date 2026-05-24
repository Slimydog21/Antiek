# ARE Wave 3 — measurement harness + PR review gate

**Date:** 2026-05-24
**Branch:** `are/wave-1-substrate-additive` (commits chained on the Wave 1+2 branch — operator may rebase at merge time)
**Source spec:** `~/specs/antiek-rust-execution/` — ARE-12 + ARE-10
**Status:** ✅ Wave 3 landed — benchmark harness + verdict doc + PR template + operator review checklist

## Summary

This wave closes two more ARE sprints:

| Sprint | What landed | Files |
|---|---|---|
| ARE-12 hot-path measurement | Benchmark harness + 5 sub-benchmarks + verdict doc with quantitative triggers | 11 new files; 1 modified (Wave 1 module) |
| ARE-10 PR template + rigor review gate | `.github/PULL_REQUEST_TEMPLATE.md` + `docs/operator_review_checklist.md` with worked example | 2 new files |

Cumulative across Waves 1+2+3 on the branch: 7 ARE sprints landed (ARE-02 Result encoding partial, ARE-05 escape_hatch convention, ARE-06 doctest exemplars on Wave-1 modules, ARE-07 hypothesis property tests, ARE-08 RFC template, ARE-09 antiek check CLI, ARE-10 PR template + checklist, ARE-12 hot-path harness). 5 ARE sprints deferred (ARE-01 db_lock + event_log mypy fixes, ARE-02 M3–M5 boundary refactors, ARE-03 variant conversions, ARE-04 ownership handles, ARE-11 substrate_floor.yml).

## What landed (commits on this branch, oldest→newest, mine marked ★)

```
056fa95 feat(research-bridge): substrate package — stake-down       (mixed: includes ARE-10 + test fix)
0ba2cde docs(adr): ARE-12 hot-path verdicts + benchmark harness smoke test  ★
b19a6b6 feat(benchmarks): ARE-12 hot-path measurement harness       ★
6a80e25 eng(e3): integrations.toml registry + tier-check CI         (parallel stream)
2a067c8 docs(adr): ARE Wave 2 tooling-additive — wave summary       ★
cffb29f fix(substrate): ruff UP-rule modernizations + doctest exemplars  ★
63f857c feat(substrate-tooling): ARE Wave 2 — lints + antiek check CLI  ★
56bb1ba eng(e7): craft signature = inline-rubric p95                 (parallel stream)
f8062df docs(adr): ARE Wave 1 substrate-additive — wave summary     ★
cbe1ed3 feat(substrate): @escape_hatch audited bypass marker        ★
eeed22c feat(substrate): Result[T, E] discriminated union + variants ★
```

### About commit `056fa95`

During this session, the operator's parallel-stream tooling was active and a second Claude Code agent was working on the unrelated `~/specs/antiek-deep-research-bridge/` spec. That agent (running on what it believed to be its own branch) ran a broad `git add` and committed under the operator's identity — and the commit landed on `are/wave-1-substrate-additive` because the parallel-stream tooling had auto-switched the working-tree branch label during the second agent's session.

The commit's stat line:

```
.github/PULL_REQUEST_TEMPLATE.md                  | 108 ++++  ← MINE (ARE-10)
docs/operator_review_checklist.md                 |  92 +++  ← MINE (ARE-10)
tests/test_benchmark_harness.py                   |  11 +-   ← MINE (ARE-12 test fix)
<...50+ other files...>                                       ← other agent's research-bridge work
```

**Operator action at merge time:** if you want to keep my ARE-10 + ARE-12-test-fix attribution clean, split commit `056fa95` with `git rebase -i` and a `e` (edit) on that line, then `git reset HEAD~` and re-commit in two halves. If you don't care about attribution, the work is correct and present — leave it.

## ARE-12 (hot-path measurement) — what's measured

`tools/benchmarks/hot_paths/` is the harness; first-pass measurements from this session's run (Darwin/arm64, Python 3.14.5, Pydantic 2.7+):

| Bench | median | p99 |
|---|---:|---:|
| `result.Ok_int_construct` | 583 ns | 708 ns |
| `result.Err_substrate_construct` | 1.29 µs | 1.58 µs |
| `result.Ok_round_trip_json` | 2.25 µs | 2.42 µs |
| `errors.union_dump_5_variants` | 6.21 µs | 8.13 µs |
| `errors.union_validate_5_variants` | 21.0 µs | 28.0 µs |
| `errors.union_round_trip_5_variants` | 28.4 µs | 36.1 µs |
| `baseline.noop_call` | 42 ns | 125 ns |
| `escape_hatch.noop_under_with_block` | 625 ns | 750 ns |
| `dispatch.match_per_call` (1000 dispatches) | 75.6 µs (~76 ns/call) | 88.7 µs |
| `dispatch.dict_per_call` (1000 dispatches) | 49.2 µs (~49 ns/call) | 58.5 µs |
| `dispatch.if_elif_per_call` (1000 dispatches) | 71.5 µs (~72 ns/call) | 83.9 µs |
| `doctest.parse_and_run_3_examples` | 52.5 µs | 62.8 µs |

Verdicts + quantitative triggers documented in `docs/decisions/hot_path_language.md`. Summary: every Wave-1-substrate path stays in Python; dispatch is per-use-case (match for closed-set exhaustiveness, dict for plug-in extension); operator-production hot paths (verifier env, dispatch fan-out, Parquet read, JSON repair, RL training data prep) are TODO — the harness shape they slot into is ready.

Reproducibility: `./.venv/bin/python -m tools.benchmarks.hot_paths --save` writes per-run JSON to `tools/benchmarks/hot_paths/results/<YYYY-MM-DDTHHMMSSZ>.json` for cross-run diffing.

## ARE-10 (PR template + operator review checklist) — what landed

`.github/PULL_REQUEST_TEMPLATE.md` populates on every new PR. Five rigor sections (one per value); each asks a SPECIFIC question calibrated to resist generic "yes, considered" answers. Test plan section delegates to the `antiek check` CLI from Wave 2. Substrate invariant impact section delegates to the `substrate.invariants` suite added by the parallel Hashimoto stream's SPR-E1.

`docs/operator_review_checklist.md` is what the operator reads before approving. 2–3 anti-pattern-catching questions per value. Includes a worked example: applying the rubric retroactively to my Wave 1 commits (`eeed22c`/`cbe1ed3`/`f8062df`) produces a real finding for every value, confirming the rubric is calibrated tightly enough to be useful.

What ARE-10 did NOT do:
- Wire a GitHub-action that REQUIRES rigor sections to be filled. Automation here would be theater — the discipline is "operator refuses to merge a PR with empty rigor sections." If discipline lapses, automate; until then, light-touch wins.
- Extend `~/.claude/skills/htmlspec/templates/sprint.html` (the spec called for it). That's user-config space; touching it from a project session collides with cross-project htmlspec use.

## Verification

All commits pushed to `origin/are/wave-1-substrate-additive`. PR creation URL:

```
https://github.com/Slimydog21/Antiek/pull/new/are/wave-1-substrate-additive
```

Per-stage gauntlet (from clean clone):

```bash
cd ~/Desktop/Antiek
git fetch origin
git checkout are/wave-1-substrate-additive
./.venv/bin/pip install -e ".[dev]" hypothesis  # hypothesis opt-in

# Wave 1 + 2 + 3 substrate-quality tests
./.venv/bin/python -m pytest \
    tests/test_results.py tests/test_errors.py tests/test_escape_hatch.py \
    tests/test_lints_no_raise.py tests/test_lints_unannotated_bypass.py \
    tests/test_antiek_cli.py tests/test_benchmark_harness.py \
    tests/properties/ -q
# Expected: 125 passed (52 + 30 + 22 + 8 + 13 prop) (skip 13 without hypothesis)

# mypy --strict on all new modules
./.venv/bin/mypy --strict substrate/results.py substrate/errors.py \
    substrate/escape_hatch.py
# Expected: Success: no issues found in 3 source files

# Doctests
./.venv/bin/pytest --doctest-modules \
    substrate/results.py substrate/errors.py substrate/escape_hatch.py -q
# Expected: 3 passed

# Bench harness end-to-end
./.venv/bin/python -m tools.benchmarks.hot_paths --save
# Expected: 12 benchmarks complete + JSON written

# antiek check CLI end-to-end
./.venv/bin/python -m tools.antiek_cli check --help
./.venv/bin/python -m tools.antiek_cli check types \
    --scope substrate/results.py --strict
# Expected: PASS

# Substrate invariants (from parallel Hashimoto stream — should pass)
./.venv/bin/python -m substrate.invariants
# Expected: 6 invariants checked, 0 violation(s)
```

## Out of scope for this wave (final deferral list)

The remaining 5 ARE sprints, each with its named blocker:

| ARE | What it would do | Blocker |
|---|---|---|
| ARE-01 | Fix 35 `mypy --strict` errors in `runtime/db_lock.py` + `substrate/event_log/events.py` | Touches critical invariant #1's enforcement file. The parallel-stream tooling was actively modifying `runtime/db_lock.py` during this session. Operator review needed on the `runtime/db_lock.py:510` `Optional[str]` → `open()` site before touching. |
| ARE-02 M3–M5 | Refactor 3 boundary sites to return `Result[T, SubstrateError]` | Operator must choose which 3 sites; the Hermes-bridge chaos test (commit `cd602c9`) must continue to pass after each refactor. |
| ARE-03 | Inventory + convert variant-typed dispatches across `substrate/dispatch/`, `substrate/event_log/`, `substrate/legal_gate/` | Large blast radius; ARE-02 boundary work should land first so each match site can also return `Result[T, SubstrateError]` uniformly. |
| ARE-04 | Ownership handles for dispatch budget + event_log writer | Needs design alignment with the parallel Hashimoto stream's `substrate/invariants.py` enforcement (I-001 single-writer-duckdb already covers DuckDB; would my handle layer duplicate or extend it?). |
| ARE-11 | `substrate_floor.yml` CI workflow wiring | The lints landed but with empty allowlists — wiring them WITHOUT a baseline file would block every existing PR. Needs operator to run `python -m tools.lints.no_raise_in_substrate_writers substrate/ > baseline.txt` first and commit the baseline. |

The remaining ARE-08 milestones (ADR backfills) are intentionally not on this list because they're editorial — the template landed; the operator decides what to backfill.

## Self-ratification

- **Intellectual honesty:** documented the `056fa95` commit mixing explicitly so the operator knows what's mine vs the other Claude session's. Did not silently re-attribute. Named 5 still-deferred ARE sprints with per-item blockers.
- **Fairness:** ARE-10 acknowledged that automation-of-rubric-enforcement would be theater at single-operator scale; light-touch is the right verdict, and the trigger to flip is "discipline lapses." ARE-12 acknowledged the limit of synthetic benchmarks — operator-production paths are TODO, not pretended-measured.
- **Rigor:** every benchmark has a real measurement (the JSON file is committed); every verdict has a quantitative trigger; the harness has a smoke test that runs every registered `bench_*.py run()` and asserts BenchResult shape.
- **Diligence:** matched `tools/` conventions (per-tool directory with `__init__.py` + `__main__.py`); read `runtime/db_lock.py` doctring and `substrate/event_log/__init__.py` re-exports to align discriminated-union style.
- **Defensibility:** every commit message is standalone; the deferral table in this ADR is concrete enough that a future session can pick up any item with no further reading.

## Reproducibility

Branch is on origin as of this commit. Re-run the gauntlet above; expected output matches.

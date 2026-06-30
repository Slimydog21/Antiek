# Decision: raise CI `pytest` job `timeout-minutes` 15 → 25 → 40

**Date:** 2026-05-30 (15→25), amended **2026-06-01** (25→40)
**Context:** PR #31 (`ingest/integration` → `main`, the 10-sprint corpus-ingest
architecture). CI's `pytest` job was reported **cancelled**, not failed.

> **2026-06-01 amendment (SECOND bump, 25 → 40).** The flywheel-foundation run
> (SPR-01..07) plus two parallel-session merges (PR #42 rights kill-gate, PR #44
> caddy routes) grew the suite again. SPR-06 passed at ~23.5 min execution —
> already inside ~1.5 min of the 25-min ceiling — and **SPR-07's** PR #45 `pytest`
> job was **cancelled at 25 m 4 s** (`conclusion: cancelled`, no `FAILED` lines,
> `tsc` job green): the suite tipped past 25 min. This is the same
> cancelled-not-failed signature as the original, one ceiling higher. Raised to
> **40 min** as a stopgap so the remaining sprints (SPR-08..11) can finish without
> re-hitting the wall. **This is the second timeout bump; the treadmill is now the
> headline finding — `xdist`/sharding has moved from "deferred" to the REQUIRED
> real fix (see Reconsider-if).** Nothing about *what* is checked changed: the gate
> still runs the full `pytest tests/ -q -m "not integration"` suite and still fails
> on any real failure; the craft-signature latency baseline is untouched.

## What happened

The `pytest` job in `.github/workflows/ci.yml` hit `timeout-minutes: 15` and was
cancelled at ~54% with `##[error]The operation was canceled`. There were **no**
`FAILED` test lines; the full suite passes locally (4653 passed / 8 skipped on
the same Python 3.14 venv). The apparent "5-minute stall" in the log is GitHub
Actions' buffered `-q` dot output flushing in bursts, not a hung test (an
audit of the changed files found **no** un-mocked network egress — no
`requests`/`httpx`/`urllib`/`socket` calls outside fixtures, and no real
`time.sleep` beyond a 5 ms case).

## Root cause (not this PR's code)

The CI timeout was **already under-provisioned on `main`**:

| Recent `main` `ci.yml` run | wall-clock | result |
|---|---|---|
| 26652892533 | 14.4 min | success |
| 26645830889 | 13.9 min | success |
| 26643640319 | 15.2 min | **cancelled** |

The shared `ubuntu-latest` runner is ~1.66× slower than the baseline dev
hardware (locked rubric-latency benchmark: p95 323.85 µs on CI vs 194.85 µs
baseline). The base suite already sat within ~1 min of the 15-min ceiling and
had been cancelled at it at least once. The corpus-ingest PR adds ~40 test files
on top, reliably pushing the full run past 15 min.

## Decision

Raise the `pytest` job `timeout-minutes` from **15 → 25**.

This changes **only the wall-clock ceiling**. The gate still runs the full
`pytest tests/ -q -m "not integration"` suite and still fails the PR on any real
test failure. No test is skipped, no assertion is weakened, and the informational
inline-rubric latency craft-signature baseline (194.85 µs, locked at `640a31c`)
is **untouched** — this is not a craft-baseline move.

## Why not the alternatives

- **`pytest-xdist -n auto`** would cut wall-clock substantially and is the
  better long-term fix, but the suite is not obviously parallel-safe (DuckDB
  single-writer + many temp-file/temp-DB fixtures); introducing it under a
  "make this PR green" mandate risks new flakiness. Deferred.
- **Sharding the job** is a larger CI change, same deferral rationale.
- **Marking/removing slow tests** would reduce coverage — rejected (the suite is
  legitimately large, not pathologically slow).

## Reconsider-if

Drop back toward 15 min once the suite is sharded or xdist-parallelized (the
real throughput fix). Until then, 25 min gives ~6 min headroom over the
estimated ~18–19 min full-branch run plus shared-runner variance.

---

## Update: → 35 then converged to 40 (2026-06-01, Personal-Reading Lane + SPR-07)

**Context:** PR #43 (`personal-lane/pr` → `main`, the 10-sprint Personal-Reading
Lane) hit the SAME symptom independently: the `pytest` job was **cancelled** (not
failed) at the timeout — `##[error]The operation was canceled` at the *post-pytest*
"Substrate/dispatch boundary check" step, **after** `5405 passed, 14 skipped, 0
failed` (~22.5 min pytest step). Verified across **three** CI attempts on the same
head SHA: tests always green, cancel always at the same post-test step.

**Root cause (not this PR's correctness):** the lane adds ~225 tests (5180 →
5405). The `pytest` step alone now runs ~22.5 min on the shared runner; with
install (~2–3 min) and the post-pytest boundary/lint check steps, the **job**
crossed the 25-min ceiling and GitHub cancelled it mid-cleanup.

**Decision:** PR #43 first raised the ceiling 25 → 35. In parallel, SPR-07 (PR
#45) hit the same wall and raised it 25 → **40**. These converged on merge:
**the unified value is 40** (the higher, more recent number absorbs both the lane
and the flywheel growth). Ceiling-only, identical to the 15→25 rationale: the
gate still runs the full `pytest tests/ -q -m "not integration"` suite, still
fails on any real test failure, no test skipped, no assertion weakened, the locked
rubric-latency baseline untouched.

**Reconsider-if (now BINDING — per SPR-07's note below, a fourth bump is not the
answer):**

**This has now been bumped twice (15→25→40). A third bump is NOT the answer** —
it would mask a real and continuing throughput problem behind ever-longer
wall-clock. The required next action, before the suite grows much further, is the
throughput fix that was deferred above:

- **`pytest-xdist -n auto`** (the suite is large but the per-test DuckDB fixtures
  are temp-file/temp-DB scoped, so `--dist loadscope` is plausibly parallel-safe;
  this needs a focused validation pass against the known order-sensitive tests —
  `test_arxiv_audit`, `test_coordination_no_fork`, the magic-link tamper test —
  not a "make it green" drive-by), **or**
- **sharding the job** across N runners.

Either drops wall-clock back well under 15 min and lets this ceiling return toward
15. **Owner: a dedicated CI-infra task, not a flywheel sprint** (it touches
test-isolation across the whole suite — too risky to fold into an autonomous
feature run). 40 min is the stopgap until then; reconsider the moment a run
approaches ~35 min.

## 2026-06-01 — the SPR-09 keystone moved to its own job (the OOM, not the clock)

A distinct failure from the timeout treadmill above, found while merging SPR-11
onto the Personal-Reading-Lane base (~5400 tests): the **SPR-09 compounding-
benchmark keystone** — which had ridden as a tail step of the `pytest` job —
began failing in CI with a `null` step-conclusion, no `FAILED` line, ~26–29 min
into the job (UNDER the 40-min timeout, so NOT a cancellation), at a *variable*
point across runs — while the identical `pytest compounding/benchmark/tests/ -m
"not slow"` passes **48/48, deterministic and tmp-isolated**, on a fresh machine.
That signature is an **OOM-kill**, not the clock and not a test defect: the
benchmark spins multiple DuckDB graphs + asyncio researchers, and after the full
~5400-test suite the shared `ubuntu-latest` runner is already near its memory
ceiling.

**Fix (not another timeout bump):** extract the keystone into its **own CI job**
(`keystone`) on a fresh runner with full memory. The gate is unchanged — the same
tests run, still fail on a real defect, and a keystone failure still reds the PR;
it simply no longer competes for memory with the full suite. Orthogonal to (and
cheaper than) the xdist/sharding fix above, which remains the right move for the
`pytest` job's own wall-clock. **Reconsider-if:** the suite is sharded so the
keystone can re-home into a shard cheaply.

## 2026-06-30 — xdist validation attempt, not yet wired

The required throughput fix was validated far enough to prove it is viable, but
**not** far enough to wire into CI. The intended command remains:

```bash
python -m pytest tests/ -q -m "not integration" -n auto --dist loadscope
```

`pytest-xdist` is already declared in the `dev` extra. The workflow still runs
serial at the 40-minute stopgap because the full xdist run is not green yet. Do
not lower the timeout or add `-n auto` to CI until the blockers below are closed.

Validation completed:

- `tests/test_coordination_no_fork.py` failed both serial and xdist because the
  canonical `specs/` directory can exist without the untracked roster dirs,
  causing `build_roadmap()` to skip the committed roster manifest and return an
  empty roadmap.
- `substrate/coordination/roadmap.py` now falls back to
  `sprint_rosters.json` per missing canonical roster dir, while preserving
  strict fixture semantics for explicit `specs_root` calls.
- Known order-sensitive validation passed under xdist:
  `tests/test_acquisition_arxiv.py tests/test_coordination_no_fork.py tests/test_magic_link_auth.py -q -n 4 --dist loadscope`
  → 82 passed.
- Personal-reading lane validation passed under xdist:
  `tests/test_personal_reading_lane.py tests/test_personal_lane_read_side.py tests/test_retrieval_substrate_personal_reading.py tests/test_get_chunk_personal_reading.py tests/test_x_byok_training_exclusion.py -q -n 4 --dist loadscope`
  → 34 passed.

Full-suite validation result:

```bash
python -m pytest tests/ -q -m "not integration" -n auto --dist loadscope --tb=short
# 5815 passed, 14 skipped, 12 failed before operator interrupt during teardown
```

Remaining blockers observed in that run:

- `tests/test_krea_routes.py::test_routes_registered_and_health_unaffected`
  saw an `_IncludedRouter` route object without `.path`.
- Turbopuffer retrieval tests selected the credentialed spike stub and raised
  `NotImplementedError` instead of the no-credentials skip path.
- `tests/test_declared_bar.py::test_mypy_targets_match_wheel_packages` saw
  `services` in wheel packages but not declared mypy targets.
- `tests/test_compliance_invariants.py::test_raw_body_scanner_reports_zero_violations_on_the_current_tree`
  reported existing raw-body SQL reads outside the serve gate.
- `tests/test_weekly_report.py` hit naive-vs-aware datetime comparison in
  acquisition-cost collection.
- `tests/test_retrieval_bench.py::test_run_benchmark_emits_artifact` hit the
  Turbopuffer spike stub.
- `tests/test_dispatch_bootstrap.py::test_health_endpoint_reports_registered_providers`
  observed registered providers beyond the two pinned in the test.

Next CI-infra slice: close or quarantine these full-suite blockers, then rerun
the exact full xdist command above before changing `.github/workflows/ci.yml`.

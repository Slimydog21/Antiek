# Decision: raise CI `pytest` job `timeout-minutes` 15 → 25

**Date:** 2026-05-30
**Context:** PR #31 (`ingest/integration` → `main`, the 10-sprint corpus-ingest
architecture). CI's `pytest` job was reported **cancelled**, not failed.

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

## Update: 25 → 35 (2026-06-01, Personal-Reading Lane)

**Context:** PR #43 (`personal-lane/pr` → `main`, the 10-sprint Personal-Reading
Lane). Same symptom recurred: the `pytest` job was **cancelled** (not failed) at
the timeout — `##[error]The operation was canceled` at the *post-pytest*
"Substrate/dispatch boundary check" step, **after** `5405 passed, 14 skipped, 0
failed` (~22.5 min pytest step). Verified across **three** CI attempts on the
same head SHA: tests always green, cancel always at the same post-test step.

**Root cause (not this PR's correctness):** the lane adds ~225 tests (5180 →
5405). The `pytest` step alone now runs ~22.5 min on the shared runner; with
install (~2–3 min) and the post-pytest boundary/lint check steps, the **job**
crossed the 25-min ceiling and GitHub cancelled it mid-cleanup. The 25-min
ceiling set on 2026-05-30 had ~6 min headroom over an ~18–19 min run; the lane's
+225 tests consumed it.

**Decision:** raise `timeout-minutes` 25 → 35. Ceiling-only, identical to the
15→25 rationale: the gate still runs the full `pytest tests/ -q -m "not
integration"` suite, still fails on any real test failure, no test skipped/no
assertion weakened, the locked rubric-latency baseline untouched.

**Reconsider-if (unchanged + sharper):** drop back toward 15–20 once the suite
is sharded or `pytest-xdist`-parallelized (the real throughput fix — deferred
here for the same DuckDB-single-writer / temp-DB-fixture parallel-safety reason).
35 gives ~10 min headroom over the observed ~24–25 min full-job run plus
shared-runner variance.

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

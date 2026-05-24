# Antiek's craft signature

Antiek's craft signature is **inline-rubric latency** — specifically
the p95 wall time of `substrate.synthesis_rubric.scorer.score_synthesis`
on the 100-fixture benchmark corpus.

## The target

| | locked baseline (2026-05-24, `640a31c`) |
|---|---|
| **p95** | 194.85 μs |
| p50 | 129.83 μs |
| p99 | 213.84 μs |

CI fails on any commit whose p95 regresses by more than **10%** against
this baseline. The full machinery lives at `benchmarks/rubric_latency.py`;
the locked numbers + corpus distribution sit in `benchmarks/baseline.json`.

## Why this dimension, not others

The §14.4 inline rubric fires on every Phase 6 exit; the operator sees
it inline while reading a synthesis. Its latency is therefore
operator-perceptible — a slow rubric breaks the read flow. The function
is also pure-deterministic with no I/O, which makes the measurement
stable: run-to-run p95 variance is ~1% on a quiet machine, well below
the 10% regression threshold.

Hashimoto on Ghostty's renderer: *"each frame updates in roughly 9
microseconds. We could have made it 2,000 microseconds and it wouldn't
have mattered. But that's not fun. I want to make it sub 10."* Antiek's
9μs is 194μs — the rubric does meaningful work on Python data
structures, and the floor reflects that — but the discipline is the
same: pick one dimension, keep it tight, write everything else off.

## What's explicitly "good enough"

These dimensions stay at their current bar; no perf work is in scope
for them unless a real operator-perceptible problem surfaces.

| Dimension | Good-enough bar |
|---|---|
| `antiek-continuous-research.service` poll cadence | Whatever the systemd timer specifies; we don't optimize daemon wake-up. |
| Dispatch decision time | Single-digit ms per call is fine; bottleneck is provider latency, not Antiek's routing. |
| DuckDB query latency under `db_lock` contention | The 5-minute timeout in `runtime/db_lock.py` is the operating envelope; faster lock acquisition is not the goal. |
| Autoresearch end-to-end | Network-bound; throughput matters, not per-call latency. |
| Storybook component render | Whatever the dev server gives us; this is a developer tool, not a user-facing surface. |
| FastAPI request latency (substrate API) | < 200ms for everything but synthesis endpoints; no tighter goal until a real user surfaces a complaint. |
| TS compilation time | Whatever `npx tsc --noEmit` produces; pre-merge CI hops on the slow path acceptably. |

## How to update the baseline

The current baseline is locked. **Do not update it silently.** If a
deliberate perf-improving change ships, update via:

```
python -m benchmarks.rubric_latency --update-baseline
```

and document the change in the same commit. The baseline file carries
its `git_sha` + `captured_at` so the lock is recoverable to a specific
point in history.

If the regression check fires unintentionally on CI, the right response
is to fix the regression — not to bump the baseline. The 10% threshold
exists precisely to prevent silent drift.

## Provenance

- Spec: `~/specs/antiek-hashimoto-engineering/sprint-e7-craft-benchmark.html`
- Philosophy round: `~/specs/antiek-philosophy/rounds/round-01-hashimoto/sprint-08-craft.html`
- Hashimoto source: 2026-Q1 podcast interview (Hashicorp + Ghostty)
- Locked: 2026-05-24, git SHA `640a31c` (the main HEAD when SPR-E7 ran)

## Open question for the operator

The 10% threshold is a defensible starting number, not science. If a
future tuning pass establishes a tighter run-to-run noise floor (or
ships a multi-run-median CI check), tighten the threshold accordingly.
For now: 10% is the contract.

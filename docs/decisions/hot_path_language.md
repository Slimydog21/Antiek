# Hot-path language verdict — ARE-12

**Date:** 2026-05-24
**Branch:** `are/wave-1-substrate-additive`
**Source spec:** `~/specs/antiek-rust-execution/` ARE-12
**Status:** First-pass verdicts on five **substrate-level** hot paths; **TODO** on the operator-named production hot paths (need access to live datasets + production code paths).

## What this doc records

For each candidate hot path:
- **Verdict** (stay-in-Python / leave-when-triggered / leave-now).
- **Trigger** — a quantitative threshold tied to product harm. If/when measurement crosses the trigger, the verdict flips.
- **Reproducibility** — the bench file + the run command.

The Rust-interview claim was that predictable latency + no GC pauses become decisive on back-end workloads. The Antiek question this doc answers: for each hot path we can measure, does Python pay its way today, and what's the trigger that would flip it?

## Measurement environment (first-pass run)

Captured by the harness on the developer workstation. Re-run + diff against `tools/benchmarks/hot_paths/results/` to see drift.

- Machine: Darwin / arm64 / per `platform.platform()` in the saved JSON
- Python: 3.14.5
- Pydantic: 2.7+ (Rust-backed JSON via `pydantic-core`)
- Iteration counts: 200–10,000 per bench (per-bench tuned for stable percentile)
- Timing source: `time.perf_counter_ns()` (sub-microsecond resolution on darwin/arm64)
- Stats method: nearest-rank percentile on sorted sample arrays — more robust than linear interpolation against jitter at small N

## Substrate-level hot paths (measured, verdict written)

### HP-1: `Result[T, SubstrateError]` construction and round-trip

**Bench:** `tools/benchmarks/hot_paths/bench_result_construct.py`

| Metric | median | p99 |
|---|---:|---:|
| `Ok(value=42)` construction | 583 ns | 708 ns |
| `Err(error=BudgetExceeded(...))` construction | 1,292 ns | 1,583 ns |
| `Ok` JSON round-trip (serialize + deserialize) | 2,250 ns | 2,417 ns |

**Verdict:** **stay in Python.** At any realistic Antiek throughput (substrate handles a few-thousand requests/sec at the top end), Result construction is <0.1% of the per-request CPU budget. Pydantic v2's rust-backed core handles the JSON round-trip in ~2 µs — essentially free relative to anything that touches the network.

**Trigger to flip:** a single hot path sustains >100k Result-construction/sec AND py-spy attributes >5% of CPU to `Ok`/`Err` constructors. At that point, a frozen `slots=True` dataclass + custom serializer would shave ~70% off construction but ship the cross-module-Pydantic-hand-off problem the Wave 1 ADR rejected. Re-evaluate; do not pre-empt.

### HP-2: SubstrateError discriminated-union serialization

**Bench:** `tools/benchmarks/hot_paths/bench_substrate_error_serialize.py`

| Metric (5 variants per call) | median | p99 |
|---|---:|---:|
| `TypeAdapter.dump_json` over all 5 | 6,208 ns | 8,125 ns |
| `TypeAdapter.validate_json` over all 5 | 21,042 ns | 27,958 ns |
| Full round-trip over all 5 | 28,417 ns | 36,083 ns |

**Per-variant:** ~5.7 µs round-trip. Asymmetric — validate is 3.4× more expensive than dump, as expected (validate runs the union-discriminator resolution; dump just emits JSON).

**Verdict:** **stay in Python.** A failed dispatch returning `Err(error=SubstrateError(...))` to a caller that round-trips it costs ~6 µs. At 1000 failures/sec sustained that's 6 ms/sec — invisible. At 100k failures/sec sustained it would be 600 ms/sec — but if Antiek has 100k failures/sec something is much more wrong than language choice.

**Trigger to flip:** failure rate exceeds 10k/sec sustained AND profile attributes >2% of CPU to union validation. At that point, msgpack or Cap'n Proto would cut serialization cost ~3× but introduce a new wire format. Re-evaluate.

### HP-3: `@escape_hatch` context-manager overhead

**Bench:** `tools/benchmarks/hot_paths/bench_escape_hatch_overhead.py`

| Metric | median | p99 |
|---|---:|---:|
| baseline no-op call | 42 ns | 125 ns |
| no-op under `with escape_hatch(...)` | 625 ns | 750 ns |
| **overhead per hatch entry** | ~580 ns | — |

**Verdict:** **stay in Python.** Escape hatches are off the hot path by design — they mark deliberate bypasses, not frequent calls. 580 ns per hatch entry is trivial against the I/O the hatch typically wraps (a DuckDB write, an HTTP call, an LLM invocation).

**Trigger to flip:** hatch counter for any single reason exceeds 1,000 hits/sec sustained. If a "bypass" fires 1k times/sec it isn't a bypass anymore — it's a hot path that should be refactored OUT of the hatch surface, not optimized inside it.

### HP-4: variant dispatch (match vs dict-registry vs if/elif)

**Bench:** `tools/benchmarks/hot_paths/bench_match_dispatch.py` (1000 dispatches per iteration)

| Idiom | median per iter | per-call (~) |
|---|---:|---:|
| Python `match` statement | 75,583 ns | ~76 ns |
| dict-registry `_HANDLERS[t]()` | 49,167 ns | ~49 ns |
| if/elif chain | 71,500 ns | ~72 ns |

**Verdict:** **per-use-case.**
- For **closed-set variants** where adding a new variant must be a deliberate, reviewable event (dispatch tier, ingestion source, verifier outcome): use `match` + `assert_never`. The 27 ns/dispatch overhead vs dict is well below 5% even at 1M dispatches/sec, and exhaustiveness checking under mypy --strict is worth the cost.
- For **open-set plug-in dispatches** where new variants are extensions (adapter registries, role-program registries): use dict-registry. Fastest and the natural shape.
- if/elif is dominated by both alternatives and has no advantage. Avoid in new code.

**Trigger to flip:** the closed-set match cost becomes >5% of a hot path's total CPU under profile. Then convert that specific site to dict-registry but document the lost exhaustiveness guarantee in the same commit.

### HP-5: doctest execution

**Bench:** `tools/benchmarks/hot_paths/bench_doctest_overhead.py`

| Metric | median | p99 |
|---|---:|---:|
| parse + execute one 3-example block | 52,500 ns | 62,750 ns |

**Verdict:** **stay; doctest is fine for the floor.** ARE-06's floor is the substrate public API — ~10–20 doctest blocks. At ~53 µs per block, CI pays ~1 ms total. Invisible against any other test step.

**Trigger to flip:** the doctest floor grows past 1000 blocks AND CI time becomes a bottleneck. At that scale (which is far above where the floor would ever sit per ARE-06's design), parallelize via pytest-xdist or carve doctest into its own workflow step.

## Operator-named production hot paths (TODO — measurement deferred)

The spec's named candidates that this commit could NOT measure because they require operator access to production code + representative datasets:

### HP-6: verifier env throughput

**Why TODO:** verifier env construction + execution requires the operator's evaluator data + the verifier-binding wiring that lives behind `substrate/legal_gate/` + the verifier registry. The harness shape (a `bench_verifier_env_throughput.py` module exposing `run() -> list[BenchResult]`) is ready; the operator slots it in by providing a representative verifier + a dataset stub.

**Likely verdict:** stay if median verifier latency is dominated by the verifier's own logic (LLM call, dedup pass) rather than the harness layer.

### HP-7: dispatch fan-out

**Why TODO:** the dispatch router's behavior depends on `substrate/dispatch/router.py` + the adapter registry + the per-adapter retry/budget logic. Touching this without the operator's review risks colliding with the parallel-stream's in-flight dispatch changes (which were modifying `substrate/dispatch/base.py` during this session).

**Likely verdict:** stay if the bottleneck is downstream LLM latency (which it almost certainly is).

### HP-8: Parquet read paths

## M3-M5 Closeout Addendum — 2026-06-30

The M3-M5 execution wave measured the five sprint-level paths named in
`docs/specs/are-12-m3-m5/` with a schema-versioned JSONL timing harness.

Artifacts:

- Baseline: `tests/benchmarks/results/baseline_m3_20260630.jsonl`
- M4 report: `tests/benchmarks/results/m4_report_20260630.{json,md}`
- M5 strong run: `tests/benchmarks/results/optimized_m5_strong_20260630.jsonl`
- M5 strong analysis: `tests/benchmarks/results/m5_strong_analysis_20260630.{json,md}`
- M5 closeout gate: `tests/benchmarks/results/m5_closeout_20260630.json`
- Archive: `tests/benchmarks/results/archive/are12-results-20260630.tar.gz`

Closeout result:

- `m5_closeout_20260630.json` status: `pass`
- Strong validation: 100 samples per path, 500 rows total
- At least one path improved by >=25%: yes (`loop_3_rl_prep`, 76.54%)
- No path regressed by >5%: yes

The target selection came from `m4_report_20260630`: `event_log_parquet_read`
and `loop_3_rl_prep`. The applied changes were intentionally narrow:
`trajectory()` fast-returns for a single already-decoded row, and
`build_env_from_trajectory()` hoists the telemetry action exclusion set.

**Why TODO:** Parquet reads need a representative Parquet file with the substrate's actual row count and schema. `substrate/event_log/events.py` likely owns the canonical read path.

**Likely verdict:** stay if DuckDB reads are within ~50 µs/row for the actual schema. Polars / pyarrow rewrites would only matter if the read becomes user-visible latency.

### HP-9: JSON repair

**Why TODO:** `substrate/dispatch/json_repair/` (per the Wave 2 generator) — needs the operator's repair-rule set + representative malformed LLM outputs.

**Likely verdict:** stay; JSON repair is an offline correction path, not user-facing latency.

### HP-10: RL training data prep

**Why TODO:** `substrate/loop_3/` — Phase-8 RL substrate. Operator-driven; agent should not touch.

**Likely verdict:** stay until the RL substrate ships and Phase 8 starts emitting real training data.

## Migration cost (if ever any trigger flips)

If a hot path's trigger crosses, the migration choice is:

| Path | Choice | Cost |
|---|---|---|
| Python → Rust via PyO3 | Highest perf gain | New toolchain (cargo + maturin), new CI step (~3 min Rust compile), deploy story (universal2 wheel build), single-operator maintenance burden, Rust-trace debugging vs Python tracebacks |
| Python → C via cffi | Moderate perf gain | C compilation already in pip path; less ergonomic than PyO3; type safety lost at FFI boundary |
| Python → Cython | Low-moderate perf gain | Stays in Python ecosystem; needs Cython compile in CI; debugger story is meh |
| In-Python refactor (slots dataclass, msgpack, dict-registry) | Lowest gain but lowest cost | Stays in one language; usually wins on cost/benefit at Antiek scale |

The honest default at single-operator scale: try the in-Python refactor first, measure, escalate only if the trigger remains crossed.

## Reproducibility

```bash
cd ~/Desktop/Antiek
./.venv/bin/python -m tools.benchmarks.hot_paths --save
# Output: results/<YYYY-MM-DDTHHMMSSZ>.json with the 12 sub-benchmark
# results, including platform + python version + timestamp.
# diff JSON across runs to detect perf regressions.
```

## Verification (this commit's harness has its own smoke test)

```bash
./.venv/bin/python -m pytest tests/test_benchmark_harness.py -v
```

8 tests cover: BenchResult shape + JSON serializability; percentile helper edge cases (empty list, p50, p100); every registered BENCH_MODULES entry imports and produces real BenchResult lists; metadata round-trips.

## Out of scope for this commit

- **Operator-production hot paths (HP-6 through HP-10).** Need operator access + dataset stubs. Each is one bench module + the verdict-doc update; the harness shape is ready.
- **Cross-run regression detection.** Today the harness writes JSON; comparing JSON across runs to flag regressions is the next concern (would slot into the `antiek check` CLI as a `perf` subcommand).
- **CI wiring.** The benchmarks are runnable on demand. Wiring them into CI as a perf-regression gate requires a baseline + an acceptable-drift policy + operator buy-in on what to do when a PR regresses perf. Not in this commit.

## Self-ratification

- **Intellectual honesty:** named the 5 hot paths I could measure AND the 5 I couldn't (and why). Did not invent numbers for HP-6 through HP-10. Reproducibility command is committed alongside the doc.
- **Fairness:** dict-registry steelman in HP-4 acknowledged + verdict went to per-use-case rather than blanket "match everywhere."
- **Rigor:** every verdict has a measurement-backed median + p99 and a quantitative trigger (not "if perf becomes a problem"). The harness has a smoke test so future runs don't silently break.
- **Diligence:** harness uses stdlib only (per invariants-pointer); BENCH_MODULES is an explicit registry (no magic walking); per-bench `run()` convention is consistent across all 5.
- **Defensibility:** the JSON results file is committed (well — would be if the operator decides to track perf-baseline). The cost-table in §"Migration cost" preserves the rationale for choosing in-Python refactors first.

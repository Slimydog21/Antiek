"""
Inline-rubric latency benchmark.

Antiek's craft signature, per ``docs/craft_signature.md``: ``score_synthesis``
in ``substrate/synthesis_rubric/scorer.py`` is the §14.4 inline rubric that
fires on every Phase 6 exit. Its latency is operator-perceptible (the rubric
is on the read path of every synthesis the operator sees inline) and its
internals are pure-deterministic — perfect for a stable benchmark.

This benchmark:

1. Builds a 100-fixture corpus deterministically (``benchmarks.fixtures``).
2. Warms up for N=10 invocations (discarded — first call pays for the
   lazy import of ``tools.prompt_autoresearch.score.deterministic_voice_style_score``
   plus any module-level work in the scorer).
3. Times N=500 invocations with ``time.perf_counter_ns`` per call,
   rotating through the fixture corpus.
4. Reports p50/p95/p99/max in microseconds plus the corpus checksum
   and git SHA at run time so the baseline is recoverable.

Modes:

- default (no args): print the report, exit 0.
- ``--update-baseline``: write the result to ``benchmarks/baseline.json``
  alongside captured_at + git_sha + corpus summary. Operator-only
  invocation; not run in CI.
- ``--check-regression``: compare against ``baseline.json``; exit 2 if
  the p95 has regressed by more than ``--threshold-pct`` (default 10).
  CI wires this in.

Why a separate ``--check-regression`` mode instead of "always compare":
running locally during development, the operator wants to see the raw
numbers without flunking themselves on a tight machine state. CI runs in
a controlled environment where flunking is the right answer.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e7-craft-benchmark.html
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.fixtures import build_corpus, serialize_corpus_summary
from substrate.synthesis_rubric.scorer import score_synthesis

BENCH_DIR = Path(__file__).resolve().parent
BASELINE_FILE = BENCH_DIR / "baseline.json"
DEFAULT_WARMUP = 10
DEFAULT_SAMPLES = 500
DEFAULT_REGRESSION_THRESHOLD_PCT = 10.0


@dataclass(frozen=True)
class BenchmarkResult:
    """One benchmark run's numeric summary."""

    p50_us: float
    p95_us: float
    p99_us: float
    max_us: float
    mean_us: float
    samples: int
    warmup: int
    corpus_size: int
    git_sha: str
    captured_at: str


def _git_sha() -> str:
    """Return the short HEAD SHA or ``"unknown"`` if not in a repo."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return sha or "unknown"


def _percentile(sorted_samples: list[float], q: float) -> float:
    """Linear-interpolated percentile (``q`` in [0, 100]).

    Avoids the numpy dependency. ``statistics.quantiles`` rounds in
    ways that aren't great for tail latency reporting.
    """
    if not sorted_samples:
        return 0.0
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    pos = (len(sorted_samples) - 1) * (q / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_samples) - 1)
    frac = pos - lo
    return sorted_samples[lo] + (sorted_samples[hi] - sorted_samples[lo]) * frac


def run_benchmark(samples: int = DEFAULT_SAMPLES, warmup: int = DEFAULT_WARMUP) -> BenchmarkResult:
    """Execute the benchmark; return the result.

    Pure function over (samples, warmup). The corpus is built fresh
    each call (deterministic on seed); the scorer is imported once at
    module load. No global state beyond the lazy-imported voice-style
    helper.
    """
    corpus = build_corpus()
    # Warmup. Discarded.
    for i in range(warmup):
        score_synthesis(corpus[i % len(corpus)])
    # Time each invocation.
    timings_ns: list[int] = []
    for i in range(samples):
        payload = corpus[i % len(corpus)]
        start = time.perf_counter_ns()
        score_synthesis(payload)
        timings_ns.append(time.perf_counter_ns() - start)
    timings_us = sorted(t / 1000.0 for t in timings_ns)
    return BenchmarkResult(
        p50_us=_percentile(timings_us, 50),
        p95_us=_percentile(timings_us, 95),
        p99_us=_percentile(timings_us, 99),
        max_us=timings_us[-1],
        mean_us=statistics.mean(timings_us),
        samples=samples,
        warmup=warmup,
        corpus_size=len(corpus),
        git_sha=_git_sha(),
        captured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _format_report(result: BenchmarkResult) -> str:
    lines = [
        "inline-rubric latency benchmark",
        "================================",
        f"corpus size:  {result.corpus_size} fixtures (deterministic)",
        f"warmup:       {result.warmup} invocations (discarded)",
        f"samples:      {result.samples} timed invocations",
        f"git SHA:      {result.git_sha}",
        f"captured_at:  {result.captured_at}",
        "",
        f"p50:  {result.p50_us:8.2f} us",
        f"p95:  {result.p95_us:8.2f} us",
        f"p99:  {result.p99_us:8.2f} us",
        f"max:  {result.max_us:8.2f} us",
        f"mean: {result.mean_us:8.2f} us",
    ]
    return "\n".join(lines)


def _write_baseline(result: BenchmarkResult) -> None:
    payload = {
        "result": asdict(result),
        "corpus_summary": serialize_corpus_summary(),
        "notes": (
            "Antiek craft signature per docs/craft_signature.md. CI's "
            "--check-regression mode compares the current p95 against this "
            "baseline and exits 2 if regressed by more than 10% (default). "
            "Update this file with --update-baseline only after a deliberate "
            "perf change has been reviewed."
        ),
    }
    BASELINE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _check_regression(result: BenchmarkResult, threshold_pct: float) -> tuple[bool, str]:
    """Return ``(regressed, message)``."""
    if not BASELINE_FILE.exists():
        # Display the path repo-relative when possible (cleaner CI logs);
        # fall back to absolute when the caller monkey-patched it outside
        # the repo (test fixtures do this).
        try:
            shown = BASELINE_FILE.relative_to(BENCH_DIR.parent)
        except ValueError:
            shown = BASELINE_FILE
        return False, (
            f"no baseline at {shown}; "
            "run with --update-baseline once to lock the current numbers."
        )
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    baseline_p95 = float(baseline["result"]["p95_us"])
    current_p95 = result.p95_us
    delta_pct = 100.0 * (current_p95 - baseline_p95) / baseline_p95
    if delta_pct > threshold_pct:
        return True, (
            f"p95 REGRESSED: baseline={baseline_p95:.2f}us, current={current_p95:.2f}us, "
            f"delta=+{delta_pct:.1f}% (threshold +{threshold_pct:.1f}%). "
            f"Either fix the regression or, if intentional, run "
            f"`python -m benchmarks.rubric_latency --update-baseline` and explain why."
        )
    if delta_pct < -threshold_pct:
        return False, (
            f"p95 IMPROVED: baseline={baseline_p95:.2f}us, current={current_p95:.2f}us, "
            f"delta={delta_pct:.1f}%. Consider running --update-baseline so future "
            f"regressions are caught against the improved bar."
        )
    return False, f"p95 within tolerance: baseline={baseline_p95:.2f}us, current={current_p95:.2f}us, delta={delta_pct:+.1f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.rubric_latency",
        description="Benchmark Antiek's craft signature (inline-rubric latency).",
    )
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES,
        help=f"timed invocations (default {DEFAULT_SAMPLES})",
    )
    parser.add_argument(
        "--warmup", type=int, default=DEFAULT_WARMUP,
        help=f"discarded warmup invocations (default {DEFAULT_WARMUP})",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="write the result to benchmarks/baseline.json (operator only)",
    )
    parser.add_argument(
        "--check-regression", action="store_true",
        help="compare against baseline; exit 2 on regression",
    )
    parser.add_argument(
        "--threshold-pct", type=float, default=DEFAULT_REGRESSION_THRESHOLD_PCT,
        help=f"p95 regression threshold in percent (default {DEFAULT_REGRESSION_THRESHOLD_PCT})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON only (useful for piping into another tool)",
    )
    args = parser.parse_args(argv)

    result = run_benchmark(samples=args.samples, warmup=args.warmup)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(_format_report(result))

    if args.update_baseline:
        _write_baseline(result)
        print(f"\nbaseline updated: {BASELINE_FILE.relative_to(BENCH_DIR.parent)}")

    if args.check_regression:
        regressed, message = _check_regression(result, args.threshold_pct)
        print(f"\n{message}")
        return 2 if regressed else 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

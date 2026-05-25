"""Driver: run every registered hot-path benchmark and emit results.

Usage::

    python -m tools.benchmarks.hot_paths
    python -m tools.benchmarks.hot_paths --save  # also write JSON

By default prints a summary table. With ``--save``, writes one
``results/<YYYY-MM-DD>-<bench>.json`` per benchmark for diffing across
runs.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from tools.benchmarks.hot_paths._harness import BenchResult

# Registry — adding a new ``bench_<x>.py`` requires adding it here.
# Keeps the driver explicit (no magic import walking).
BENCH_MODULES: tuple[str, ...] = (
    "tools.benchmarks.hot_paths.bench_result_construct",
    "tools.benchmarks.hot_paths.bench_substrate_error_serialize",
    "tools.benchmarks.hot_paths.bench_escape_hatch_overhead",
    "tools.benchmarks.hot_paths.bench_match_dispatch",
    "tools.benchmarks.hot_paths.bench_doctest_overhead",
)

RESULTS_DIR = Path(__file__).parent / "results"


def _run_all() -> list[BenchResult]:
    results: list[BenchResult] = []
    for mod_path in BENCH_MODULES:
        mod = importlib.import_module(mod_path)
        # Convention: every bench module exposes a top-level ``run() -> list[BenchResult]``
        results.extend(mod.run())
    return results


def _save_results(results: list[BenchResult]) -> Path:
    """Write one JSON file containing every result, named by date.

    Per-benchmark single files were considered but rejected: makes
    diffing across runs harder. A single file per run is the right
    granularity for comparing day-over-day or pre-after-refactor.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = RESULTS_DIR / f"{stamp}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump([r.to_dict() for r in results], fh, indent=2, default=str)
    return path


def _print_summary(results: list[BenchResult]) -> None:
    print()
    print("=" * 100)
    print("Antiek hot-path benchmarks — ARE-12")
    print("=" * 100)
    for r in results:
        print(r.format_summary_line())
    print("-" * 100)
    print(f"{len(results)} benchmarks completed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hot-path-benchmarks",
        description=(
            "Run ARE-12 hot-path benchmarks against Antiek Wave 1 substrate. "
            "Stdlib-only (timeit-equivalent); no new dep."
        ),
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help=f"also write per-run JSON to {RESULTS_DIR}",
    )
    args = parser.parse_args(argv)

    results = _run_all()
    _print_summary(results)
    if args.save:
        path = _save_results(results)
        print(f"\nResults written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

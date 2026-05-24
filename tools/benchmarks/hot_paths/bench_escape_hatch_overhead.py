"""Bench: escape_hatch context-manager overhead vs raw no-op call."""

from __future__ import annotations

from substrate.escape_hatch import escape_hatch, reset_counters_for_tests
from tools.benchmarks.hot_paths._harness import BenchResult, measure


def _noop() -> None:
    pass


def _noop_under_hatch() -> None:
    with escape_hatch(reason="benchmark-overhead-measurement"):
        pass


def run() -> list[BenchResult]:
    reset_counters_for_tests()
    # Prime the WARN log so we measure steady state, not cold path
    with escape_hatch(reason="benchmark-overhead-measurement"):
        pass
    return [
        measure("baseline.noop_call", _noop, iterations=10000),
        measure(
            "escape_hatch.noop_under_with_block",
            _noop_under_hatch,
            iterations=10000,
            metadata={"note": "steady-state per-call; first-hit WARN already emitted"},
        ),
    ]


if __name__ == "__main__":
    for r in run():
        print(r.format_summary_line())

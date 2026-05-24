"""Shared harness for hot-path benchmarks. stdlib-only."""

from __future__ import annotations

import platform
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class BenchResult:
    bench_name: str
    iterations: int
    median_ns: int
    p95_ns: int
    p99_ns: int
    min_ns: int
    max_ns: int
    total_wall_s: float
    timestamp_utc: str
    python_version: str
    platform: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_summary_line(self) -> str:
        return (
            f"{self.bench_name:<40} "
            f"med={self.median_ns:>10,}ns  "
            f"p95={self.p95_ns:>10,}ns  "
            f"p99={self.p99_ns:>10,}ns  "
            f"n={self.iterations}"
        )


def _percentile(sorted_samples: list[int], pct: float) -> int:
    if not sorted_samples:
        return 0
    rank = max(1, int(round(pct / 100.0 * len(sorted_samples))))
    return sorted_samples[min(rank - 1, len(sorted_samples) - 1)]


def measure(
    bench_name: str,
    fn: Callable[[], object],
    iterations: int = 1000,
    warmup: int = 50,
    metadata: dict[str, Any] | None = None,
) -> BenchResult:
    for _ in range(warmup):
        fn()
    samples_ns: list[int] = [0] * iterations
    wall_start = time.perf_counter()
    for i in range(iterations):
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        samples_ns[i] = t1 - t0
    total_wall_s = time.perf_counter() - wall_start
    sorted_samples = sorted(samples_ns)
    return BenchResult(
        bench_name=bench_name,
        iterations=iterations,
        median_ns=int(statistics.median(samples_ns)) if samples_ns else 0,
        p95_ns=_percentile(sorted_samples, 95.0),
        p99_ns=_percentile(sorted_samples, 99.0),
        min_ns=min(samples_ns) if samples_ns else 0,
        max_ns=max(samples_ns) if samples_ns else 0,
        total_wall_s=total_wall_s,
        timestamp_utc=datetime.now(UTC).isoformat(),
        python_version=sys.version.split()[0],
        platform=f"{platform.system()}-{platform.machine()}-{platform.release()}",
        metadata=metadata or {},
    )

"""Compare two saved ARE-12 hot-path benchmark runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRICS = ("median_ns", "p95_ns", "p99_ns")


@dataclass(frozen=True)
class RegressionFinding:
    bench_name: str
    metric: str
    baseline_ns: int
    current_ns: int
    regression_pct: float

    def format_line(self) -> str:
        return (
            f"{self.bench_name} {self.metric}: "
            f"{self.baseline_ns:,}ns -> {self.current_ns:,}ns "
            f"({self.regression_pct:.1f}% slower)"
        )


def _load_run(path: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a JSON list of benchmark results")
    out: dict[str, dict[str, Any]] = {}
    for row in raw:
        if not isinstance(row, dict) or not isinstance(row.get("bench_name"), str):
            raise ValueError(f"{path} contains a malformed benchmark row: {row!r}")
        bench_name = row["bench_name"]
        if bench_name in out:
            raise ValueError(f"{path} contains duplicate benchmark {bench_name!r}")
        out[bench_name] = row
    return out


def _metric_ns(row: dict[str, Any], metric: str, *, path: Path) -> int:
    if metric not in row:
        raise ValueError(f"{path} row {row.get('bench_name')!r} missing {metric}")
    try:
        value = round(float(row[metric]))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{path} row {row.get('bench_name')!r} has non-numeric {metric}"
        ) from exc
    if value <= 0:
        raise ValueError(
            f"{path} row {row.get('bench_name')!r} has non-positive {metric}"
        )
    return value


def compare_runs(
    baseline_path: Path,
    current_path: Path,
    *,
    max_regression_pct: float,
    metrics: tuple[str, ...] = METRICS,
) -> list[RegressionFinding]:
    baseline = _load_run(baseline_path)
    current = _load_run(current_path)
    missing = sorted(set(baseline) - set(current))
    if missing:
        raise ValueError(
            f"{current_path} is missing benchmark(s) from baseline: {', '.join(missing)}"
        )
    findings: list[RegressionFinding] = []

    for bench_name in sorted(set(baseline) & set(current)):
        b_row = baseline[bench_name]
        c_row = current[bench_name]
        for metric in metrics:
            b_value = _metric_ns(b_row, metric, path=baseline_path)
            c_value = _metric_ns(c_row, metric, path=current_path)
            regression_pct = ((c_value - b_value) / b_value) * 100.0
            if regression_pct > max_regression_pct:
                findings.append(
                    RegressionFinding(
                        bench_name=bench_name,
                        metric=metric,
                        baseline_ns=b_value,
                        current_ns=c_value,
                        regression_pct=regression_pct,
                    )
                )
    return findings

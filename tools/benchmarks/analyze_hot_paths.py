#!/usr/bin/env python3
"""M4 analysis script for ARE-12 baseline comparison reports."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

REQUIRED_PATHS = (
    "verifier_throughput",
    "dispatch_fanout",
    "event_log_parquet_read",
    "json_repair_error_path",
    "loop_3_rl_prep",
)

BOTTLENECK_MAP = {
    "verifier_throughput": {
        "function": "tests/benchmarks/test_hot_paths.py::verify_pair",
        "line_range": "66-69",
    },
    "dispatch_fanout": {
        "function": "substrate/dispatch/router.py::_compute_cost_usd",
        "line_range": "226-246",
    },
    "event_log_parquet_read": {
        "function": "substrate/event_log/events.py::trajectory",
        "line_range": "535-574",
    },
    "json_repair_error_path": {
        "function": "substrate/dispatch/json_repair.py::repair_json_string",
        "line_range": "13-26",
    },
    "loop_3_rl_prep": {
        "function": "substrate/loop_3/verifiers_env.py::build_env_from_trajectory",
        "line_range": "101-116",
    },
}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        # glob support simple
        candidates = list(Path("tests/benchmarks/results").glob("baseline_m3_*.jsonl"))
        if not candidates:
            raise SystemExit(1)
        input_path = candidates[0]

    records: list[dict[str, Any]] = []
    with input_path.open() as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if len(records) < 15:
        raise SystemExit("insufficient samples")

    by_path: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if r.get("schema_version") != 1:
            raise SystemExit(f"bad schema_version in row: {r!r}")
        by_path[r["path"]].append(r["duration_ms"])

    missing = {
        path: len(by_path.get(path, []))
        for path in REQUIRED_PATHS
        if len(by_path.get(path, [])) < 3
    }
    if missing:
        raise SystemExit(f"required paths missing or under-sampled: {missing}")

    paths_stats = []
    for path_name in REQUIRED_PATHS:
        durations = by_path[path_name]
        stats = {
            "path": path_name,
            "samples": len(durations),
            "p50": round(statistics.median(durations), 6),
            "p95": round(statistics.quantiles(durations, n=20)[18], 6) if len(durations) >= 20 else round(max(durations), 6),
            "mean": round(statistics.mean(durations), 6),
            "stddev": round(statistics.stdev(durations), 6) if len(durations) > 1 else 0.0,
            "bottleneck_map": BOTTLENECK_MAP[path_name],
        }
        paths_stats.append(stats)

    # Rank slowest first by p95
    paths_stats.sort(key=lambda x: x["p95"], reverse=True)
    top2 = paths_stats[:2]

    report = {
        "generated_at": "deterministic-from-input",
        "git_sha": records[0].get("git_sha", "unknown"),
        "python_version": records[0].get("python_version"),
        "os": records[0].get("os"),
        "paths": paths_stats,
        "top_bottlenecks": [
            {
                "path": t["path"],
                "p95": t["p95"],
                "function": t["bottleneck_map"]["function"],
                "line_range": t["bottleneck_map"]["line_range"],
            }
            for t in top2
        ],
    }

    out_base = Path(args.output)
    out_json = out_base.with_suffix(".json")
    out_md = out_base.with_suffix(".md")

    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    md = ["# ARE-12 M4 Comparison Report\n"]
    md.append(f"Generated: {report['generated_at']}\n")
    md.append("| Path | p50 | p95 | mean | stddev | samples | Bottleneck map |\n")
    md.append("|------|-----|-----|------|--------|---------|----------------|\n")
    for p in paths_stats:
        bm = p["bottleneck_map"]
        md.append(
            f"| {p['path']} | {p['p50']} | {p['p95']} | {p['mean']} | "
            f"{p['stddev']} | {p['samples']} | {bm['function']}:{bm['line_range']} |\n"
        )
    md.append("\n## Top-2 Bottlenecks\n")
    for i, t in enumerate(top2, 1):
        bm = t["bottleneck_map"]
        md.append(
            f"{i}. bottleneck: {t['path']} (p95={t['p95']}ms) at "
            f"{bm['function']}:{bm['line_range']}\n"
        )

    out_md.write_text("".join(md), encoding="utf-8")
    print(f"Wrote {out_json} and {out_md}")

if __name__ == "__main__":
    main()

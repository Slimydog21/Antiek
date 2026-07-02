#!/usr/bin/env python3
"""Compare ARE-12 baseline and optimized reports for M5 closeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _by_path(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["path"]: row for row in report["paths"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--optimized", required=True)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-improvement-pct", type=float, default=25.0)
    parser.add_argument("--max-regression-pct", type=float, default=5.0)
    args = parser.parse_args()

    baseline = _load_report(Path(args.baseline))
    optimized = _load_report(Path(args.optimized))
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    target_names = {row["name"] for row in targets["paths"]}
    base_by_path = _by_path(baseline)
    opt_by_path = _by_path(optimized)

    rows = []
    regressions = []
    improvements = []
    for path_name, base_row in base_by_path.items():
        opt_row = opt_by_path[path_name]
        before = float(base_row["p95"])
        after = float(opt_row["p95"])
        if before == 0:
            change_pct = 0.0 if after == 0 else -100.0
        else:
            change_pct = round(((before - after) / before) * 100.0, 2)
        row = {
            "path": path_name,
            "targeted": path_name in target_names,
            "before_p95_ms": before,
            "after_p95_ms": after,
            "change_pct": change_pct,
        }
        rows.append(row)
        if change_pct >= args.min_improvement_pct:
            improvements.append(row)
        if change_pct < -args.max_regression_pct:
            regressions.append(row)

    closeout = {
        "status": "pass" if improvements and not regressions else "fail",
        "requirements": {
            "min_improvement_pct": args.min_improvement_pct,
            "max_regression_pct": args.max_regression_pct,
            "at_least_one_path_meets_improvement": bool(improvements),
            "no_path_exceeds_regression_limit": not regressions,
        },
        "baseline": str(args.baseline),
        "optimized": str(args.optimized),
        "targets": sorted(target_names),
        "rows": rows,
        "improvements": improvements,
        "regressions": regressions,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(closeout, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({closeout['status']})")
    if closeout["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

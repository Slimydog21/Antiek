#!/usr/bin/env python3
"""ATSB SPR-07 — aggregate dispatch.call metrics for TileRT verdict ADR.

Reads investigation event logs (same source as export_dispatch_events_parquet).
Prints a markdown table to stdout; does not mutate the ADR automatically.

Usage::

    uv run python scripts/tilert_speed_verdict_report.py
    uv run python scripts/tilert_speed_verdict_report.py --events-dir ~/.antiek/research_events

Exit 0 always when the script runs; verdict line states insufficient_data when
N < min_investigations (default 10) or no speed-tier synthesizer samples.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from substrate.analytics.dispatch_rows import iter_dispatch_call_rows  # noqa: E402


def _sorted_investigation_ids(events_dir: str) -> list[str]:
    import os

    if not os.path.isdir(events_dir):
        return []
    ids: list[str] = []
    for fn in sorted(os.listdir(events_dir)):
        if fn.endswith(".jsonl"):
            ids.append(fn[: -len(".jsonl")])
        elif fn.endswith(".parquet"):
            ids.append(fn[: -len(".parquet")])
    return sorted(set(ids))


def _p50(values: list[int | float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _aggregate(events_dir: str, *, max_investigations: int | None) -> dict:
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    investigation_ids: set[str] = set()
    speed_synth_investigations: set[str] = set()

    inv_filter: list[str] | None = None
    if max_investigations is not None and max_investigations > 0:
        inv_filter = _sorted_investigation_ids(events_dir)[:max_investigations]

    for row in iter_dispatch_call_rows(
        events_dir=events_dir,
        investigation_ids=inv_filter,
    ):
        iid = row.get("investigation_id")
        if isinstance(iid, str) and iid:
            investigation_ids.add(iid)
        role = row.get("target_role") or row.get("role") or ""
        tier = row.get("tier") or ""
        if not isinstance(role, str):
            role = str(role)
        if not isinstance(tier, str):
            tier = str(tier)
        if role == "synthesizer" and tier == "speed" and isinstance(iid, str):
            speed_synth_investigations.add(iid)
        key = (role, tier)
        by_key[key].append(row)

    def bucket(role: str, tier: str) -> dict:
        rows = by_key.get((role, tier), [])
        latencies = [
            int(r["latency_ms"])
            for r in rows
            if r.get("latency_ms") is not None
        ]
        costs = [
            float(r["cost_usd"])
            for r in rows
            if r.get("cost_usd") is not None
        ]
        return {
            "n_calls": len(rows),
            "p50_latency_ms": _p50(latencies),
            "sum_cost_usd": sum(costs) if costs else None,
        }

    return {
        "events_dir": events_dir,
        "n_investigations": len(investigation_ids),
        "n_speed_synth_investigations": len(speed_synth_investigations),
        "speed_synth_investigation_ids": sorted(speed_synth_investigations)[:20],
        "synthesizer_speed": bucket("synthesizer", "speed"),
        "synthesizer_synthesis": bucket("synthesizer", "synthesis"),
        "all_speed": bucket("*", "speed"),
    }


def _fmt_num(v: float | None) -> str:
    if v is None:
        return "_TBD_"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", default=None)
    parser.add_argument(
        "--min-investigations",
        type=int,
        default=10,
        help="SPR-07 rigor: verdict needs at least this many investigations with data.",
    )
    parser.add_argument(
        "--max-investigations",
        type=int,
        default=500,
        help="Cap event-log scan for CLI responsiveness (0 = no cap).",
    )
    args = parser.parse_args()

    from substrate.event_log.events import default_events_dir

    events_dir = args.events_dir or default_events_dir()
    cap = args.max_investigations if args.max_investigations > 0 else None
    agg = _aggregate(events_dir, max_investigations=cap)

    ss = agg["synthesizer_speed"]
    sp = agg["synthesizer_synthesis"]
    n = agg["n_speed_synth_investigations"]
    min_n = args.min_investigations
    if n < min_n or ss["n_calls"] == 0:
        verdict = "insufficient_data"
    else:
        verdict = "data_available_update_adr_manually"

    print("# TileRT speed verdict report (generated)\n")
    print(f"- events_dir: `{agg['events_dir']}`")
    if cap is not None:
        print(f"- scan cap: **{cap}** investigations (use --max-investigations 0 for full scan)")
    print(f"- investigations (any dispatch): **{agg['n_investigations']}**")
    print(f"- investigations with synthesizer tier=speed: **{n}**")
    print(f"- verdict: **{verdict}** (min_investigations={min_n})\n")
    print("| Metric | GLM speed (synthesizer) | Premium synthesis |")
    print("|--------|-------------------------|-------------------|")
    print(
        f"| p50 latency_ms | {_fmt_num(ss['p50_latency_ms'])} | "
        f"{_fmt_num(sp['p50_latency_ms'])} |"
    )
    print(
        f"| dispatch.call count | {ss['n_calls']} | {sp['n_calls']} |"
    )
    print(
        f"| sum cost_usd (role tier) | {_fmt_num(ss['sum_cost_usd'])} | "
        f"{_fmt_num(sp['sum_cost_usd'])} |"
    )
    print("\n## Sample investigation ids (speed synthesizer, max 20)\n")
    if agg["speed_synth_investigation_ids"]:
        for iid in agg["speed_synth_investigation_ids"]:
            print(f"- `{iid}`")
    else:
        print("_None — OA-022 / prod traffic required._\n")
    print("\n## Verifier pass rate\n")
    print(
        "_Not computed in this script — correlate verifier role events manually "
        "or extend iter_dispatch_call_rows join (SPR-07 milestone 2)._"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
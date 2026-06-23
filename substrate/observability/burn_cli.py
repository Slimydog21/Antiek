"""``antiek burn`` — per-call burn telemetry (duckdb_plane §13 CLIs)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from substrate.observability.burn_report import (
    GroupBy,
    default_analytics_db_path,
    report_cost_view_summary,
    report_dispatch_groups,
    report_from_analytics_db,
    report_write_log_rollup,
)
from substrate.event_log.events import default_events_dir


def _cmd_report(args: argparse.Namespace) -> int:
    group_by: GroupBy = args.by
    if args.source == "analytics":
        adb = args.analytics_db or default_analytics_db_path()
        rows = report_from_analytics_db(adb, group_by=group_by)
        payload: object = {"groups": rows, "analytics_db": str(adb)}
    elif group_by == "workflow" and not args.investigation:
        payload = report_cost_view_summary(
            events_dir=args.events_dir,
            investigation_ids=args.investigation,
        )
        if args.detail:
            payload = {
                "summary": payload,
                "groups": report_dispatch_groups(
                    events_dir=args.events_dir,
                    investigation_ids=args.investigation,
                    group_by="workflow",
                ),
            }
    else:
        payload = {
            "groups": report_dispatch_groups(
                events_dir=args.events_dir,
                investigation_ids=args.investigation,
                group_by=group_by,
            ),
            "events_dir": args.events_dir or default_events_dir(),
        }

    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    if isinstance(payload, dict) and "groups" in payload and "summary" not in payload:
        groups = payload["groups"]
        if not groups:
            sys.stdout.write("no dispatch burn in window (idle posture: $0)\n")
            return 0
        for g in groups:
            sys.stdout.write(
                f"{g['key']}\tcalls={g['call_count']}\t"
                f"cost_usd={g['cost_usd']:.6f}\n"
            )
        return 0

    if isinstance(payload, dict) and "per_workflow" in payload:
        agg = payload["aggregate"]
        sys.stdout.write(
            f"aggregate\tcalls={agg['call_count']}\t"
            f"cost_usd={agg['raw_cost_usd']:.6f}\n"
        )
        for w in payload["per_workflow"]:
            sys.stdout.write(
                f"{w['workflow']}\tcalls={w['call_count']}\t"
                f"cost_usd={w['raw_cost_usd']:.6f}\n"
            )
        return 0

    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


def _cmd_write_log(args: argparse.Namespace) -> int:
    rows = report_write_log_rollup(db_path=args.db)
    if args.json:
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
        return 0
    if not rows:
        sys.stdout.write("write_log: (absent or empty)\n")
        return 0
    for r in rows:
        sys.stdout.write(
            f"{r['purpose']}\twrites={r['write_count']}\t"
            f"duration_s={r['total_duration_s']:.3f}\t"
            f"ok={r['success_count']}\n"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="antiek burn",
        description="Per-call burn telemetry (event log + optional analytics DuckDB).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report_p = sub.add_parser("report", help="Dispatch cost aggregates")
    report_p.add_argument(
        "--by",
        choices=("workflow", "provider", "model", "tool", "role"),
        default="workflow",
        help="Group dispatch.call rows (default: workflow)",
    )
    report_p.add_argument(
        "--source",
        choices=("events", "analytics"),
        default="events",
        help="events=jsonl truth; analytics=rebuild-only duckdb",
    )
    report_p.add_argument(
        "--events-dir",
        default=None,
        help=f"Research events dir (default: {default_events_dir()})",
    )
    report_p.add_argument(
        "--investigation",
        action="append",
        dest="investigation",
        default=None,
        help="Limit to investigation id(s)",
    )
    report_p.add_argument(
        "--analytics-db",
        type=Path,
        default=None,
        help="Path to analytics.duckdb when --source analytics",
    )
    report_p.add_argument(
        "--detail",
        action="store_true",
        help="With workflow + events, include per-workflow group table",
    )
    report_p.add_argument("--json", action="store_true", help="JSON output")
    report_p.set_defaults(func=_cmd_report)

    wl_p = sub.add_parser(
        "write-log", help="OLTP write_log purpose rollup (connect_read)"
    )
    wl_p.add_argument(
        "--db",
        default=None,
        help="Antiek OLTP path (default: ANTIEK_DUCKDB_PATH / substrate default)",
    )
    wl_p.add_argument("--json", action="store_true")
    wl_p.set_defaults(func=_cmd_write_log)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
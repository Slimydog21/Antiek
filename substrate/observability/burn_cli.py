"""``antiek burn`` CLI — report / raw / export against per-project burn store."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from substrate.observability.burn import BurnRecorder

_SINCE_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_since(text: str) -> datetime:
    m = _SINCE_RE.match(text)
    if not m:
        raise ValueError(f"--since must look like 7d / 24h / 30m / 60s, got {text!r}")
    n, unit = int(m.group(1)), m.group(2)
    delta = {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
             "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
    return datetime.now(timezone.utc) - delta


def _print(rows: list[dict[str, Any]], json_out: bool) -> None:
    if json_out:
        sys.stdout.write(json.dumps({"rows": rows}, default=str, indent=2) + "\n")
        return
    if not rows:
        sys.stdout.write("(no rows)\n")
        return
    cols = list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    sys.stdout.write(" | ".join(c.ljust(widths[c]) for c in cols) + "\n")
    sys.stdout.write("-+-".join("-" * widths[c] for c in cols) + "\n")
    for r in rows:
        sys.stdout.write(" | ".join(str(r[c]).ljust(widths[c]) for c in cols) + "\n")


def _cmd_report(args: argparse.Namespace) -> int:
    recorder = BurnRecorder.for_project(args.project_root)
    since_iso = _parse_since(args.since).isoformat()
    group_col = {
        "tool": "COALESCE(tool_id, '<none>')", "model": "model",
        "session": "session_id", "day": "substr(ts, 1, 10)",
    }[args.by]
    rows = recorder.query(
        f"SELECT {group_col} AS bucket, COUNT(*) AS calls, "
        "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, "
        "SUM(cached_tokens) AS cached_tokens, "
        "SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors "
        "FROM burn_events WHERE ts >= ? "
        + (f"AND session_id = ? " if args.session else "")
        + (f"AND project_id = ? " if args.project else "")
        + "GROUP BY bucket ORDER BY input_tokens + output_tokens DESC",
        tuple(
            [since_iso]
            + ([args.session] if args.session else [])
            + ([args.project] if args.project else [])
        ),
    )
    _print(rows, args.json)
    return 0


def _cmd_raw(args: argparse.Namespace) -> int:
    recorder = BurnRecorder.for_project(args.project_root)
    rows = recorder.query("SELECT * FROM burn_events ORDER BY ts DESC LIMIT ?", (args.limit,))
    _print(rows, args.json)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    recorder = BurnRecorder.for_project(args.project_root)
    rows = recorder.query("SELECT * FROM burn_events ORDER BY event_id")
    if args.format == "json":
        sys.stdout.write(json.dumps(rows, default=str, indent=2) + "\n")
    else:
        import csv
        if not rows:
            return 0
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antiek burn", description="Burn telemetry CLI")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="cmd", required=True)
    rep = sub.add_parser("report")
    rep.add_argument("--since", default="24h")
    rep.add_argument("--by", choices=["tool", "model", "session", "day"], default="tool")
    rep.add_argument("--session")
    rep.add_argument("--project")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=_cmd_report)
    raw = sub.add_parser("raw")
    raw.add_argument("--limit", type=int, default=20)
    raw.add_argument("--json", action="store_true")
    raw.set_defaults(func=_cmd_raw)
    exp = sub.add_parser("export")
    exp.add_argument("--format", choices=["json", "csv"], default="csv")
    exp.set_defaults(func=_cmd_export)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

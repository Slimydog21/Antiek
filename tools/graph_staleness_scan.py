#!/usr/bin/env python3
"""Scan graph edges for temporal staleness and optionally emit advisory events."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from middleware.temporal import scan_graph_edge_staleness
from runtime.db_lock import connect_read
from substrate.graph import default_db_path


def _parse_as_of(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        default=None,
        help="DuckDB graph file. Defaults to substrate.graph.default_db_path().",
    )
    parser.add_argument(
        "--investigation-id",
        default="graph-staleness-scan",
        help="Investigation id for emitted staleness events.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="ISO timestamp for deterministic scans, e.g. 2026-07-07T00:00:00Z.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of active edges to scan.",
    )
    parser.add_argument(
        "--emit-events",
        action="store_true",
        help="Append graph.staleness.flagged typed events. Omit for a dry run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    graph = Path(args.graph or default_db_path()).expanduser()
    if not graph.exists():
        print(f"::error::graph_staleness_scan: graph not found: {graph}", file=sys.stderr)
        return 2

    try:
        as_of = _parse_as_of(args.as_of)
    except ValueError as exc:
        print(f"::error::graph_staleness_scan: invalid --as-of: {exc}", file=sys.stderr)
        return 2

    try:
        with connect_read(str(graph)) as con:
            result = scan_graph_edge_staleness(
                con,
                investigation_id=args.investigation_id,
                as_of=as_of,
                limit=args.limit,
                emit_events=bool(args.emit_events),
            )
    except ValueError as exc:
        print(f"::error::graph_staleness_scan: {exc}", file=sys.stderr)
        return 2

    summary = {
        "graph": str(graph),
        "emit_events": bool(args.emit_events),
        "scanned": result.scanned,
        "flagged": len(result.flagged),
        "unclassified": result.unclassified,
        "flags": [asdict(flag) for flag in result.flagged],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI entry for the inbox acquisition connector.

``python -m acquisition.inbox --inbox ~/research/inbox [--since YYYY-MM-DD] [--db PATH]``
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .adapter import ingest_inbox_dir


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m acquisition.inbox")
    parser.add_argument("--inbox", required=True, help="Path to dated inbox root")
    parser.add_argument("--since", type=_parse_date, default=None, help="Only ingest folders on/after YYYY-MM-DD")
    parser.add_argument("--db", default=None, help="DuckDB path override")
    args = parser.parse_args(argv)

    summary = ingest_inbox_dir(
        Path(args.inbox).expanduser(),
        since=args.since,
        db_path=args.db,
    )
    print(f"folders scanned: {summary.folders_scanned}")
    print(f"files considered: {summary.files_considered}")
    print(f"files ingested: {summary.files_ingested}")
    print(f"duplicates skipped: {summary.duplicates_skipped}")
    print(f"chunks written: {summary.chunks_written}")
    print(f"files skipped: {summary.files_skipped}")
    for reason, count in sorted(summary.skipped_by_reason.items()):
        print(f"  {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

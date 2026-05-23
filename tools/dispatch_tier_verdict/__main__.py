"""CLI entry point for the dispatch tier verdict analyzer."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.dispatch_tier_verdict.analyzer import (
    analyse_events,
    render_verdict_markdown,
)


def _default_events_path() -> Path:
    raw = os.environ.get("ANTIEK_EVENT_LOG_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".antiek" / "events"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.dispatch_tier_verdict",
        description=(
            "Compute the §14.4 dispatch tier-differentiation verdict "
            "from the trajectory event log."
        ),
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=_default_events_path(),
        help="Path to event log directory or single JSONL file.",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Start of measurement window (ISO 8601). Defaults to 14 days ago.",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="End of measurement window (ISO 8601). Defaults to now.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/decisions/dispatch-tier-verdict.md"),
        help="Where to write the verdict markdown.",
    )
    args = parser.parse_args()

    def _parse_iso_to_utc(raw: str) -> datetime:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    since = (
        _parse_iso_to_utc(args.since)
        if args.since
        else datetime.now(timezone.utc) - timedelta(days=14)
    )
    until = (
        _parse_iso_to_utc(args.until)
        if args.until
        else datetime.now(timezone.utc)
    )

    print(f"Analyzing events in {args.events}")
    print(f"  window: {since.isoformat()} → {until.isoformat()}")

    verdict = analyse_events(events_path=args.events, since=since, until=until)
    md = render_verdict_markdown(verdict)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md)
    print()
    print(f"Verdict: {verdict.decision}")
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

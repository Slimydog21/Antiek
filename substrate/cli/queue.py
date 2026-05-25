"""``antiek queue`` CLI — list registered bounded queues + their stats."""

from __future__ import annotations

import argparse
import json
import sys

from substrate.queue import get_registry


def _cmd_status(args: argparse.Namespace) -> int:
    stats = get_registry().all_stats()
    if args.json:
        sys.stdout.write(json.dumps(stats, indent=2) + "\n")
        return 0
    if not stats:
        sys.stdout.write(
            "(no queues registered in this process)\n\n"
            "queue stats are process-local; for historical watermark events use:\n"
            "  antiek burn report --by tool\n"
        )
        return 0
    cols = ("name", "depth", "capacity", "above_watermark",
            "enqueue_count", "dequeue_count", "reject_count", "watermark_crossings")
    widths = {c: max(len(c), *(len(str(s.get(c, ""))) for s in stats)) for c in cols}
    sys.stdout.write(" | ".join(c.ljust(widths[c]) for c in cols) + "\n")
    sys.stdout.write("-+-".join("-" * widths[c] for c in cols) + "\n")
    for s in stats:
        sys.stdout.write(" | ".join(str(s.get(c, "")).ljust(widths[c]) for c in cols) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antiek queue")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=_cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""HTML projection backfill command."""

from __future__ import annotations

import argparse
import sys

from substrate.reading.projection.backfill import DEFAULT_LEASE_SECONDS, backfill_projections


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antiek projections")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--source-object-root", required=True)
    parser.add_argument("--html-object-root", required=True)
    parser.add_argument("--worker-id", default="html-projection-backfill")
    parser.add_argument("--lease-seconds", type=float, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = backfill_projections(
            db_path=args.db_path,
            source_object_root=args.source_object_root,
            html_object_root=args.html_object_root,
            apply=args.apply,
            worker_id=args.worker_id,
            lease_seconds=args.lease_seconds,
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    if args.json:
        sys.stdout.buffer.write(report.canonical_json_bytes() + b"\n")
    else:
        sys.stdout.write(
            f"plan {report.plan_id}: {report.candidates} candidates, "
            f"{report.would_convert} convertible, {report.conversion_failed} failed\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

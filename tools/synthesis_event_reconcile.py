"""Guarded exact-authority operator drain for synthesis event intents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from runtime.db_lock import connect_write
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.synthesis_event_outbox import reconcile_synthesis_events


def _authority(args: argparse.Namespace) -> InvestigationAuthority:
    for value in (args.account_id, args.investigation_id):
        if not value or value != value.strip() or len(value) > 512:
            raise ValueError("authority value is invalid")
    return InvestigationAuthority(
        args.account_id,
        args.investigation_id,
        root=args.root.expanduser().resolve(),
    )


def _status(db_path: Path, authority: InvestigationAuthority) -> dict[str, int | str]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        pending, delivered, failed = con.execute(
            "SELECT count(*) FILTER (WHERE delivery_state = 'pending' "
            "AND NOT coalesce(terminal_failure, FALSE)), "
            "count(*) FILTER (WHERE delivery_state = 'delivered'), "
            "count(*) FILTER (WHERE coalesce(terminal_failure, FALSE)) "
            "FROM synthesis_event_outbox "
            "WHERE account_digest = ? AND investigation_digest = ?",
            [authority.account_digest, authority.investigation_digest],
        ).fetchone()
        return {
            "state": "status",
            "pending": int(pending),
            "delivered": int(delivered),
            "failed": int(failed),
        }
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or reconcile synthesis events for one exact authority"
    )
    parser.add_argument("action", choices=("status", "reconcile"))
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--approve-reconcile", action="store_true")
    args = parser.parse_args(argv)
    db_path = args.db_path.expanduser().resolve()
    try:
        authority = _authority(args)
        if not 1 <= args.limit <= 10_000:
            raise ValueError("limit is invalid")
    except ValueError as exc:
        parser.error(str(exc))

    if args.action == "status":
        receipt = _status(db_path, authority)
    else:
        if not args.approve_reconcile:
            parser.error("reconcile requires --approve-reconcile")
        with connect_write(str(db_path), purpose="synthesis-events:reconcile") as con:
            result = reconcile_synthesis_events(con, authority, limit=args.limit)
        receipt = {
            "state": "reconciled",
            "attempted": result.attempted,
            "delivered": result.delivered,
            "pending": result.pending,
        }
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

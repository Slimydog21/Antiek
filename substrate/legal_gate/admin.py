"""Operator CLI for cited global legal-policy revisions.

The global capability is loaded only from installed process configuration.
Request/account identity never mints this authority.
"""

from __future__ import annotations

import argparse
import contextlib
import json
from datetime import datetime
from typing import Any

from runtime.db_lock import connect_read, connect_write
from substrate.graph import default_db_path
from substrate.graph.schema import init_database_at_path

from .policy_store import (
    append_policy_event,
    global_policy_authority,
    load_global_policy_admin_capability,
)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m substrate.legal_gate.admin")
    parser.add_argument("--db", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    for command in ("add", "revoke"):
        item = sub.add_parser(command)
        item.add_argument(
            "--matcher-kind",
            required=True,
            choices=("domain", "corpus", "author", "title", "content_sha256"),
        )
        item.add_argument("--matcher-value", required=True)
        item.add_argument("--citation-ref", required=True)
        item.add_argument("--reason-code", required=True)
        item.add_argument("--effective-at", required=True, type=_timestamp)
        item.add_argument("--dry-run", action="store_true")
    add = sub.choices["add"]
    add.add_argument("--expires-at", type=_timestamp)
    revoke = sub.choices["revoke"]
    revoke.add_argument("--supersedes-event-id", required=True)
    return parser


def _redacted_global_events(path: str) -> list[dict[str, Any]]:
    con = connect_read(path)
    try:
        rows = con.execute(
            "SELECT event_id, matcher_kind, decision, citation_ref, issuer_id, "
            "reason_code, effective_at, expires_at, supersedes_event_id, "
            "event_fingerprint FROM legal_policy_events WHERE scope_kind = 'global' "
            "ORDER BY effective_at, event_id"
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "event_id": str(row[0]),
            "matcher_kind": str(row[1]),
            "decision": str(row[2]),
            "citation_ref": str(row[3]),
            "issuer_id": str(row[4]),
            "reason_code": str(row[5]),
            "effective_at": row[6].isoformat(),
            "expires_at": None if row[7] is None else row[7].isoformat(),
            "supersedes_event_id": None if row[8] is None else str(row[8]),
            "event_fingerprint": str(row[9]),
        }
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = args.db or default_db_path()
    if args.command == "list":
        capability = load_global_policy_admin_capability()
        global_policy_authority(capability)
        rows = _redacted_global_events(path)
        print(json.dumps({"scope": "global", "events": rows}, sort_keys=True))
        return 0

    init_database_at_path(path)
    capability = load_global_policy_admin_capability()
    authority = global_policy_authority(capability)
    con = connect_write(path, purpose=f"legal-policy-{args.command}")
    try:
        con.execute("BEGIN TRANSACTION")
        event_id = append_policy_event(
            con,
            authority,
            scope_kind="global",
            matcher_kind=args.matcher_kind,
            matcher_value=args.matcher_value,
            decision="deny" if args.command == "add" else "revoke",
            citation_ref=args.citation_ref,
            issuer_id=capability.issuer_id,
            reason_code=args.reason_code,
            effective_at=args.effective_at,
            expires_at=getattr(args, "expires_at", None),
            supersedes_event_id=getattr(args, "supersedes_event_id", None),
        )
        if args.dry_run:
            con.execute("ROLLBACK")
        else:
            con.execute("COMMIT")
    except BaseException:
        with contextlib.suppress(Exception):
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    print(
        json.dumps(
            {
                "event_id": event_id,
                "scope": "global",
                "applied": not args.dry_run,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

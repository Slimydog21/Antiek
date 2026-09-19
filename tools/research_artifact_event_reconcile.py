"""Guarded exact-authority drain for durable ResearchArtifact events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.outbox import reconcile_pending_events


def _authority(args: argparse.Namespace) -> ArtifactAuthority:
    for value in (args.account_id, args.investigation_id):
        if not value or value != value.strip() or len(value.encode("utf-8")) > 512:
            raise ValueError("authority value is invalid")
    return ArtifactAuthority(args.account_id, args.investigation_id)


def _counts(authority: ArtifactAuthority, root: Path) -> dict[str, int | str]:
    account = authority.account_dir(root)
    return {
        "state": "status",
        "pending": len(list((account / "pending-events").glob("*.json"))),
        "quarantined": len(list((account / "quarantined-events").glob("*.json"))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or reconcile artifact events for one exact authority"
    )
    parser.add_argument("action", choices=("status", "reconcile"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--events-root", type=Path, required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--approve-reconcile", action="store_true")
    args = parser.parse_args(argv)
    artifact_root = args.artifact_root.expanduser().resolve()
    events_root = args.events_root.expanduser().resolve()
    try:
        authority = _authority(args)
        if not 1 <= args.limit <= 10_000:
            raise ValueError("limit is invalid")
    except ValueError as exc:
        parser.error(str(exc))

    if args.action == "status":
        receipt = _counts(authority, artifact_root)
    else:
        if not args.approve_reconcile:
            parser.error("reconcile requires --approve-reconcile")
        result = reconcile_pending_events(
            authority,
            events_dir=str(events_root),
            root=artifact_root,
            limit=args.limit,
        )
        receipt = {
            "state": "reconciled",
            "attempted": result.attempted,
            "delivered": result.delivered,
            "pending": result.pending,
            "quarantined": result.quarantined,
        }
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

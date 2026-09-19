#!/usr/bin/env python3
"""Dry-run/apply/resume/rollback the conservative legal history migration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.investigation_tenancy import InvestigationAuthority  # noqa: E402
from substrate.legal_gate.history_migration import (  # noqa: E402
    LegacyDocumentClaim,
    migrate_legacy_documents,
    rollback_legacy_migration,
)


def _claims(path: Path | None) -> tuple[LegacyDocumentClaim, ...]:
    if path is None:
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("claims file must contain a JSON list")
    claims: list[LegacyDocumentClaim] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each legacy claim must be an object")
        claims.append(LegacyDocumentClaim(**item))
    return tuple(claims)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--claims", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", metavar="RUN_ID")
    args = parser.parse_args(argv)
    authority = InvestigationAuthority(args.account_id, args.investigation_id)
    db_path = args.db_path or default_db_path()
    ensure_initialized(db_path)
    with connect_write(db_path, purpose="tools/legal-history-migrate") as con:
        if args.rollback:
            result = rollback_legacy_migration(con, authority, args.rollback)
        else:
            result = migrate_legacy_documents(
                con,
                authority,
                claims=_claims(args.claims),
                apply=args.apply,
            )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "state": result.state,
                "candidate_count": result.candidate_count,
                "admitted_count": result.admitted_count,
                "quarantined_count": result.quarantined_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Dry-run/apply/rollback legacy engagement owner assignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from substrate.engagement_spine.migration import migrate_legacy_engagement


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engagement-root", type=Path, required=True)
    parser.add_argument("--session-root", type=Path)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--mode", choices=("dry-run", "apply", "rollback"), default="dry-run")
    parser.add_argument("--migration-id")
    args = parser.parse_args()
    result = migrate_legacy_engagement(
        engagement_root=args.engagement_root,
        session_root=args.session_root,
        account_id=args.account_id,
        mode=args.mode,
        migration_id=args.migration_id,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

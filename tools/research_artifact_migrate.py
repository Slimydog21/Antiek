"""Operator CLI for redacted ResearchArtifact inventory and migration."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from substrate.research_artifact.authority import OPERATOR_ACCOUNT_ID
from substrate.research_artifact.migration import (
    legacy_inventory_report,
    migrate_legacy_artifact,
)
from substrate.research_artifact.paths import research_artifacts_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy ResearchArtifact HTML")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--resume-after", metavar="SOURCE_DIGEST")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-operator-migration", action="store_true")
    args = parser.parse_args(argv)
    root = (args.root or research_artifacts_dir()).expanduser().resolve()
    if not args.apply:
        print(json.dumps(asdict(legacy_inventory_report(root)), sort_keys=True))
        return 0
    if not args.approve_operator_migration:
        parser.error("--apply requires --approve-operator-migration")
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    if args.source is not None:
        candidates = [(hashlib.sha256(args.source.name.encode()).hexdigest(), args.source)]
    else:
        candidates = sorted(
            (
                (hashlib.sha256(path.name.encode()).hexdigest(), path)
                for path in root.glob("*.html")
                if not path.name.startswith("compose-")
            ),
            key=lambda item: item[0],
        )
    if args.resume_after:
        candidates = [item for item in candidates if item[0] > args.resume_after]
    candidates = candidates[: args.batch_size]
    receipts: list[dict[str, object]] = []
    refused: list[dict[str, str]] = []
    for source_digest, source in candidates:
        try:
            receipt = migrate_legacy_artifact(
                source,
                account_id=OPERATOR_ACCOUNT_ID,
                approved=args.approve_operator_migration,
                root=root,
            )
        except Exception as exc:
            refused.append(
                {"source_digest": source_digest, "error_type": type(exc).__name__}
            )
        else:
            receipts.append(asdict(receipt))
    result = {
        "attempted": len(candidates),
        "migrated": len(receipts),
        "refused": refused,
        "receipts": receipts,
        "resume_after": candidates[-1][0] if candidates else args.resume_after,
    }
    print(json.dumps(result, sort_keys=True))
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())

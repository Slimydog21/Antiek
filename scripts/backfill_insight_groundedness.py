#!/usr/bin/env python3
"""Backfill insight groundedness_score with current note-evidence loader.

Honest re-score only (same lexical scorer as deposit). Does not lower the
reuse gate. Example:

  PYTHONPATH=. python scripts/backfill_insight_groundedness.py \
    --document-id doc-book-a0ebbd6fd3bfa7c6 --apply
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--document-id", default=None, help="Limit to one source document")
    p.add_argument("--events-dir", default=None)
    p.add_argument("--db-path", default=None)
    p.add_argument("--apply", action="store_true", help="Write updated scores (default dry-run)")
    p.add_argument("--only-below", action="store_true", help="Skip units already >= 0.5")
    p.add_argument("--threshold", type=float, default=0.5)
    args = p.parse_args(argv)

    from substrate.graph.insight_question import rescore_promoted_note_groundedness

    rows = rescore_promoted_note_groundedness(
        db_path=args.db_path,
        events_dir=args.events_dir,
        source_document_id=args.document_id,
        dry_run=not args.apply,
        only_below_threshold=args.only_below,
        threshold=args.threshold,
    )
    ge_old = sum(1 for r in rows if r["old"] is not None and r["old"] >= args.threshold)
    ge_new = sum(1 for r in rows if r["new"] >= args.threshold)
    crossed = sum(1 for r in rows if r["crossed_threshold"])
    print(
        json.dumps(
            {
                "considered": len(rows),
                "ge_threshold_before": ge_old,
                "ge_threshold_after": ge_new,
                "crossed_threshold": crossed,
                "updated": sum(1 for r in rows if r["updated"]),
                "dry_run": not args.apply,
                "rows": rows,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

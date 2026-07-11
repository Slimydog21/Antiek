"""Per-title free-copy preflight CLI.

Searches existing PD book connectors (Gutendex, Internet Archive) for a
freely-available copy of a given title.  Default = dry-run report;
``--ingest`` performs the classify_and_ingest handoff on a hit.

Exit codes:
    0 — free copy found
    3 — not freely available
    2 — error

Usage:
    python tools/book_lookup.py "The Republic"
    python tools/book_lookup.py "Walden" --author "Henry David Thoreau"
    python tools/book_lookup.py "Republic" --source gutenberg --json
    python tools/book_lookup.py "Republic" --ingest --db-path /tmp/lib.duckdb
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.lookup import (  # noqa: E402
    FreeCopyFound,
    NotFreelyAvailable,
    SourceOutcome,
    ingest_found_copy,
    search_free_copy,
)

logger = logging.getLogger("tools.book_lookup")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Search for a freely-available copy of a book title.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  Free copy found\n"
            "  3  Not freely available\n"
            "  2  Error\n"
        ),
    )
    p.add_argument("title", help="Book title to search for")
    p.add_argument("--author", help="Author name (improves hit rate)")
    p.add_argument(
        "--source",
        action="append",
        choices=["gutenberg", "internet_archive"],
        help="Source(s) to search (default: gutenberg, internet_archive)",
    )
    p.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest the found copy via classify_and_ingest (requires --db-path for real run)",
    )
    p.add_argument("--db-path", help="DuckDB path for ingest (required with --ingest)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--debug", action="store_true", help="Debug logging")
    return p


def _format_source(outcome: SourceOutcome) -> str:
    parts = [f"  {outcome.source}: not found"]
    if outcome.error:
        parts.append(f" (error: {outcome.error})")
    parts.append(f"  query: {outcome.query}")
    parts.append(f"  at: {outcome.timestamp}")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    level = logging.DEBUG if args.debug else logging.WARNING
    if not args.json:
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    sources = tuple(args.source) if args.source else ("gutenberg", "internet_archive")
    result = search_free_copy(args.title, args.author, sources=sources)

    if isinstance(result, FreeCopyFound):
        if args.json:
            print(json.dumps({
                "status": "found",
                "source": result.source,
                "rights_basis": result.rights_basis,
                "retrieved_at": result.retrieved_at,
            }, indent=2))
        else:
            print(f"Free copy found!")
            print(f"  Source:  {result.source}")
            print(f"  Title:   {result.candidate_ref.title}")
            author = result.candidate_ref.author
            if author:
                print(f"  Author:  {author}")
            print(f"  Rights:  {result.rights_basis}")
            print(f"  At:      {result.retrieved_at}")

        if args.ingest:
            if not args.json:
                print("\nIngesting...")
            try:
                outcome = ingest_found_copy(result, fetcher=None, db_path=args.db_path)
                if hasattr(outcome, "ingested") and outcome.ingested:
                    if args.json:
                        print(json.dumps({"ingested": True, "document_id": outcome.document_id}))
                    else:
                        print(f"  Ingested: {outcome.document_id}")
                else:
                    reason = getattr(outcome, "skipped_reason", "unknown")
                    if args.json:
                        print(json.dumps({"ingested": False, "reason": reason}))
                    else:
                        print(f"  Skipped: {reason}")
            except Exception as exc:
                if args.json:
                    print(json.dumps({"ingested": False, "error": str(exc)}))
                else:
                    print(f"  Ingest error: {exc}")
                return 2
        return 0

    # NotFreelyAvailable
    if args.json:
        print(json.dumps({
            "status": "not_found",
            "title": result.title,
            "author": result.author,
            "sources_searched": [o.source for o in result.outcomes],
            "outcomes": [
                {
                    "source": o.source,
                    "found": o.found,
                    "query": o.query,
                    "error": o.error,
                    "timestamp": o.timestamp,
                }
                for o in result.outcomes
            ],
            "checked_at": result.checked_at,
        }, indent=2))
    else:
        print(f"No free copy found for: {result.title}")
        if result.author:
            print(f"Author: {result.author}")
        print(f"Sources searched: {', '.join(o.source for o in result.outcomes)}")
        print(f"Per-source outcomes:")
        for o in result.outcomes:
            print(_format_source(o))
        print(f"\nRecommendation: purchase or request through library.")
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

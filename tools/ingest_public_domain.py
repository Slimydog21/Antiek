"""Batch-ingest public-domain books into an Antiek substrate (SPR-01).

Discovers public-domain works (Project Gutenberg primary, archive.org
secondary), downloads the PDF, tags rights provenance, and ingests each
through the existing servable-book path
(``acquisition.books.ingest_servable_book``) as
``content_class=public_domain`` so the full text renders.

Note: the SPR-01 page claimed a batch CLI already wrapped the ingest path
at ``tools/ingest_books.py``. That file does not exist; this is the
batch CLI, built fresh against ``ingest_servable_book``.

Usage:

    # discover what would be fetched, write nothing
    python -m tools.ingest_public_domain --subject philosophy --limit 5 --dry-run

    # real run into a LOCAL/TEMP DuckDB (never prod)
    python -m tools.ingest_public_domain --subject philosophy \\
        --limit 20 --db-path /tmp/antiek-library.duckdb

    # the curated canonical starter list (philosophy/science/literature)
    python -m tools.ingest_public_domain --curated --db-path /tmp/library.duckdb

    # explicit Gutenberg ids
    python -m tools.ingest_public_domain --ids 1342,84,1661 \\
        --db-path /tmp/library.duckdb

Idempotent: re-running over the same inputs writes zero duplicate
documents (the adapter dedups on a stable doc id). Per-item failures are
logged and the batch continues.

Constraints (hard): never targets prod. ``--db-path`` is required for a
real run and must point at a local/temp file. All writes go through
``connect_write`` via ``ingest_servable_book``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.public_domain import (  # noqa: E402
    IngestOutcome,
    PublicDomainWork,
    SourceClient,
    SourceError,
    gutenberg_candidates,
    ingest_work,
)

logger = logging.getLogger("tools.ingest_public_domain")


# Curated canonical public-domain spine, by Project Gutenberg book id, so the
# library has shape on day one across philosophy / science / literature. Each
# is long out of copyright; Gutenberg's per-book copyright=false flag is still
# the authority of record at ingest time (we do not hard-code the rights
# claim here — the source must assert it, per rigor #1).
CURATED_GUTENBERG_IDS: tuple[int, ...] = (
    # Philosophy
    1497,   # Plato — The Republic
    1656,   # Plato — Apology
    8438,   # Aristotle — Ethics (Nicomachean)
    2680,   # Marcus Aurelius — Meditations
    4280,   # Kant — The Critique of Pure Reason
    5827,   # Locke — Second Treatise of Government
    7370,   # Mill — On Liberty
    3207,   # Hobbes — Leviathan
    # Science
    2009,   # Darwin — On the Origin of Species
    1228,   # Darwin — The Voyage of the Beagle
    37729,  # Einstein — Relativity: The Special and General Theory
    14725,  # Faraday — The Chemical History of a Candle
    33283,  # Newton — Opticks
    # Literature
    1342,   # Austen — Pride and Prejudice
    84,     # Shelley — Frankenstein
    1661,   # Doyle — The Adventures of Sherlock Holmes
    2701,   # Melville — Moby-Dick
    1400,   # Dickens — Great Expectations
    11,     # Carroll — Alice's Adventures in Wonderland
    98,     # Dickens — A Tale of Two Cities
    2542,   # Ibsen — A Doll's House
    1080,   # Swift — A Modest Proposal
)


@dataclass(frozen=True)
class BatchReport:
    candidates: int
    ingested: list[IngestOutcome]
    skipped: list[IngestOutcome]

    @property
    def ingested_count(self) -> int:
        return len(self.ingested)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def discover(
    client: SourceClient,
    *,
    subject: Optional[str],
    search: Optional[str],
    ids: Optional[Sequence[int]],
    curated: bool,
    limit: int,
) -> list[PublicDomainWork]:
    """Resolve the selectors to a candidate list. Gutenberg is the only
    discovery surface here; archive.org is reachable per-identifier via
    ``acquisition.books.public_domain.archive_candidate`` but is not part of
    the subject/curated discovery flow (its rights metadata is uploader free
    text — see the module steelman)."""
    if curated:
        ids = list(CURATED_GUTENBERG_IDS)
        limit = max(limit, len(ids))
    return gutenberg_candidates(
        client, subject=subject, search=search, ids=ids, limit=limit
    )


def run_batch(
    works: Sequence[PublicDomainWork],
    client: SourceClient,
    *,
    investigation_id: str,
    db_path: str,
    dry_run: bool,
) -> BatchReport:
    ingested: list[IngestOutcome] = []
    skipped: list[IngestOutcome] = []
    for work in works:
        if dry_run:
            continue
        try:
            outcome = ingest_work(
                work,
                client,
                investigation_id=investigation_id,
                db_path=db_path,
            )
        except Exception as exc:  # belt-and-braces: never let one item kill the batch
            logger.exception("unexpected failure ingesting %s", work.source_uri)
            outcome = IngestOutcome(
                work=work, ingested=False, skipped_reason=f"unexpected: {exc}"
            )
        if outcome.ingested:
            ingested.append(outcome)
            logger.info(
                "ingested %s (%s) → %s [%s, %d words]",
                work.title, work.source, outcome.document_id,
                outcome.servability, outcome.word_count,
            )
        else:
            skipped.append(outcome)
            logger.warning(
                "skipped %s (%s): %s",
                work.title, work.source, outcome.skipped_reason,
            )
    return BatchReport(candidates=len(works), ingested=ingested, skipped=skipped)


def _print_dry_run(works: Sequence[PublicDomainWork]) -> None:
    print(f"DRY RUN — {len(works)} candidate(s), nothing written:\n")
    for w in works:
        basis = w.pd_basis or "(NO public-domain basis — would be SKIPPED)"
        print(f"  [{w.source}] {w.title}")
        print(f"      author: {w.author or '(unknown)'}")
        print(f"      source: {w.source_uri}")
        print(f"      format: {w.download_format} → {w.download_url}")
        print(f"      basis:  {basis}")
        print()


def _is_prod_db(db_path: str) -> bool:
    """Heuristic guard against ever pointing this CLI at the prod DB. The
    real prod path is the substrate default (``substrate.graph.default_db_path``);
    requiring an explicit --db-path and rejecting that default keeps the
    'never write to prod' constraint mechanical, not just documented."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.ingest_public_domain",
        description="Ingest public-domain books as servable into a LOCAL Antiek DB.",
    )
    sel = p.add_argument_group("selection (choose one)")
    sel.add_argument("--subject", help="Gutenberg topic/subject filter")
    sel.add_argument("--search", help="Gutenberg full-text search term")
    sel.add_argument("--ids", help="comma-separated Gutenberg book ids")
    sel.add_argument(
        "--curated", action="store_true",
        help="ingest the curated canonical starter spine (≈22 works)",
    )
    p.add_argument("--limit", type=int, default=25, help="max works to fetch")
    p.add_argument(
        "--investigation-id", default="inv-library",
        help="investigation id stamped on ingested docs",
    )
    p.add_argument(
        "--db-path",
        help="LOCAL/TEMP DuckDB path (required for a real run; never prod)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="list what would be fetched + ingested; write nothing",
    )
    p.add_argument(
        "--min-interval", type=float, default=1.0,
        help="min seconds between source requests (in-process throttle)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    if not (args.subject or args.search or args.ids or args.curated):
        print("error: choose --subject, --search, --ids, or --curated", file=sys.stderr)
        return 2

    if not args.dry_run:
        if not args.db_path:
            print("error: --db-path is required for a real run", file=sys.stderr)
            return 2
        if _is_prod_db(args.db_path):
            print(
                "error: --db-path resolves to the prod substrate default; "
                "this CLI may only write to a LOCAL/TEMP DB (prod ingest is SPR-08)",
                file=sys.stderr,
            )
            return 2

    ids: Optional[list[int]] = None
    if args.ids:
        try:
            ids = [int(x) for x in args.ids.split(",") if x.strip()]
        except ValueError:
            print("error: --ids must be comma-separated integers", file=sys.stderr)
            return 2

    client = SourceClient(min_interval_s=args.min_interval)
    try:
        works = discover(
            client,
            subject=args.subject,
            search=args.search,
            ids=ids,
            curated=args.curated,
            limit=args.limit,
        )
    except SourceError as exc:
        print(f"error: discovery failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(works)
        return 0

    report = run_batch(
        works, client,
        investigation_id=args.investigation_id,
        db_path=args.db_path,
        dry_run=False,
    )
    print(
        f"\ningested {report.ingested_count} / {report.candidates} candidate(s); "
        f"{report.skipped_count} skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

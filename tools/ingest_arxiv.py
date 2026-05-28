"""Batch-ingest arXiv papers into an Antiek substrate, license-gated (SPR-02).

Searches arXiv (by ``--query`` / ``--ids`` / ``--category``), resolves each
paper's declared license to a servable class, fetches the full-text PDF,
and ingests it through the shared servable-book path
(``acquisition.arxiv.adapter.ingest_paper_with_rights`` ->
``acquisition.books.ingest_servable_book``).

THE INVARIANT: no paper is served on a license Antiek does not hold.
CC-BY / CC-BY-SA / CC0 -> servable; arXiv default terms / NC / ND /
unknown / missing -> GATED. ``--dry-run`` reports the would-be
content_class + license per paper WITHOUT writing anything.

All live arXiv requests go through ``ArxivThrottle`` (>= 3s spacing,
cross-process, 429 -> ban sentinel) so a batch can't re-trigger the
IP-scoped ban documented in the arxiv-ingestion failure cluster.

Usage:

    # report the rights decision per paper, write nothing
    python -m tools.ingest_arxiv --query "diffusion models" --limit 5 --dry-run

    # real run into a LOCAL/TEMP DuckDB (never prod)
    python -m tools.ingest_arxiv --ids 2402.03300,2401.12345 \\
        --db-path /tmp/antiek-arxiv.duckdb

    # by category
    python -m tools.ingest_arxiv --category cs.LG --limit 10 \\
        --db-path /tmp/antiek-arxiv.duckdb

Constraints (hard): never targets prod. ``--db-path`` is required for a
real run and must NOT resolve to the substrate default. Per-item failures
are logged and the batch continues. Prod ingest is SPR-06.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import (  # noqa: E402
    ArxivBanned,
    ArxivPaper,
    ArxivThrottle,
    ingest_paper_with_rights,
    resolve_license,
    search,
)
from acquisition.arxiv.client import fetch_by_id  # noqa: E402

logger = logging.getLogger("tools.ingest_arxiv")


@dataclass(frozen=True)
class BatchReport:
    candidates: int
    servable: int
    gated: int
    failed: int


def _note_http_status(throttle: ArxivThrottle, exc: httpx.HTTPStatusError) -> bool:
    """Feed an HTTP error's status back to the throttle. The CLI owns the
    throttle instance, so this is the one place a live 429 (raised deep in
    the client or the PDF fetcher) can persist the cross-process ban
    sentinel — without it, the next invocation has no ban knowledge and
    re-hits the banned endpoint. Returns True iff the status was a 429."""
    status = exc.response.status_code
    throttle.note_response(status, headers=exc.response.headers)
    return status == 429


def _request_with_429_sentinel(throttle, fn):
    """Run a live discovery request; on ANY HTTP error persist the status to
    the throttle (so a 429 writes the ban sentinel), then re-raise. The
    caller's discovery handler turns the error into the existing exit-1 —
    but now the sentinel is on disk, so the next invocation honors the ban
    instead of re-hitting the endpoint. Non-429 errors are unaffected."""
    try:
        return fn()
    except httpx.HTTPStatusError as exc:
        _note_http_status(throttle, exc)
        raise


def _discover(
    *,
    query: Optional[str],
    category: Optional[str],
    ids: Optional[Sequence[str]],
    limit: int,
    throttle: ArxivThrottle,
) -> List[ArxivPaper]:
    """Resolve selectors to a candidate list. Every live request is fronted
    by the throttle's ``wait_if_needed`` so spacing + ban state are honored
    process-wide. ``--ids`` fetch one paper at a time (arXiv's id_list could
    batch, but per-id fetch keeps a partial failure from dropping the whole
    list)."""
    if ids:
        papers: List[ArxivPaper] = []
        for pid in ids:
            throttle.wait_if_needed()
            p = _request_with_429_sentinel(throttle, lambda: fetch_by_id(pid))
            if p is not None:
                papers.append(p)
            else:
                logger.warning("arxiv id %s returned no entry", pid)
        return papers

    throttle.wait_if_needed()
    return _request_with_429_sentinel(
        throttle, lambda: search(query=query, category=category, max_results=limit)
    )


def _print_dry_run(papers: Sequence[ArxivPaper]) -> None:
    print(f"DRY RUN — {len(papers)} paper(s), nothing written:\n")
    for p in papers:
        res = resolve_license(p.license_uri)
        verdict = "SERVABLE" if res.redistributable else "GATED"
        print(f"  [{verdict}] {p.arxiv_id}{p.version} — {p.title}")
        print(f"      license: {p.license_uri or '(none declared)'}")
        print(f"      -> {res.content_class} ({res.license_name})")
        print(f"      why: {res.rationale}")
        print()


def run_batch(
    papers: Sequence[ArxivPaper],
    *,
    investigation_id: str,
    db_path: str,
    throttle: ArxivThrottle,
) -> BatchReport:
    servable = gated = failed = 0
    for p in papers:
        try:
            # The per-paper PDF fetch (arxiv.org/pdf) raises its own
            # HTTPStatusError; catching it here is how a 429 from that fetch
            # reaches note_response — the throttle lives at this CLI boundary,
            # not inside the adapter's fetcher.
            throttle.wait_if_needed()
            result = ingest_paper_with_rights(
                p,
                investigation_id=investigation_id,
                db_path=db_path,
            )
        except ArxivBanned as exc:
            # Ban sentinel active — PAUSE the whole batch rather than march
            # through every paper re-hitting a banned endpoint.
            logger.error("arxiv banned, halting batch: %s", exc)
            break
        except httpx.HTTPStatusError as exc:
            if _note_http_status(throttle, exc):
                # A live 429: sentinel now persisted. Halt the batch instead
                # of continuing and re-hitting the banned endpoint.
                logger.error("arxiv 429, halting batch: %s", exc)
                break
            failed += 1
            logger.warning("failed to ingest %s: %s", p.arxiv_id, exc)
            continue
        except Exception as exc:  # never let one paper kill the batch
            failed += 1
            logger.warning("failed to ingest %s: %s", p.arxiv_id, exc)
            continue
        if result.servable_full_text:
            servable += 1
        else:
            gated += 1
        logger.info(
            "ingested %s -> %s (%s) [%s]",
            p.arxiv_id, result.content_class, result.servability,
            "servable" if result.servable_full_text else "gated",
        )
    return BatchReport(
        candidates=len(papers), servable=servable, gated=gated, failed=failed
    )


def _is_prod_db(db_path: str) -> bool:
    """Guard against ever pointing this CLI at the prod DB. Mirrors the
    SPR-01 CLI: the prod path is the substrate default; requiring an
    explicit --db-path and rejecting that default keeps 'never write to
    prod' mechanical."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.ingest_arxiv",
        description=(
            "Ingest arXiv papers, license-gated, into a LOCAL Antiek DB."
        ),
    )
    sel = p.add_argument_group("selection (choose one)")
    sel.add_argument("--query", help="arXiv full-text search query")
    sel.add_argument("--category", help="arXiv category, e.g. cs.LG")
    sel.add_argument("--ids", help="comma-separated arXiv ids")
    p.add_argument("--limit", type=int, default=10, help="max papers to fetch")
    p.add_argument(
        "--investigation-id", default="inv-arxiv",
        help="investigation id stamped on ingested docs",
    )
    p.add_argument(
        "--db-path",
        help="LOCAL/TEMP DuckDB path (required for a real run; never prod)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="report content_class + license per paper; write nothing",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    if not (args.query or args.category or args.ids):
        print("error: choose --query, --category, or --ids", file=sys.stderr)
        return 2

    if not args.dry_run:
        if not args.db_path:
            print("error: --db-path is required for a real run", file=sys.stderr)
            return 2
        if _is_prod_db(args.db_path):
            print(
                "error: --db-path resolves to the prod substrate default; "
                "this CLI may only write to a LOCAL/TEMP DB (prod ingest is SPR-06)",
                file=sys.stderr,
            )
            return 2

    ids: Optional[List[str]] = None
    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]

    throttle = ArxivThrottle()
    try:
        papers = _discover(
            query=args.query,
            category=args.category,
            ids=ids,
            limit=args.limit,
            throttle=throttle,
        )
    except ArxivBanned as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # network / HTTP / parse failure in discovery
        print(f"error: arxiv discovery failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(papers)
        return 0

    report = run_batch(
        papers,
        investigation_id=args.investigation_id,
        db_path=args.db_path,
        throttle=throttle,
    )
    print(
        f"\ningested {report.candidates - report.failed} / {report.candidates}; "
        f"{report.servable} servable, {report.gated} gated, {report.failed} failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

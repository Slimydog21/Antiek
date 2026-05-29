"""Batch-ingest open-access papers into an Antiek substrate, license-gated (SPR-03).

Resolves candidate works from an OA aggregator, derives each item's servable
class from its DECLARED license (deny-by-default), fetches the best legal OA
PDF, and ingests it through the shared servable-book path
(``acquisition.openaccess.ingest.ingest_oa_item`` ->
``acquisition.books.ingest_servable_book``).

THE INVARIANT: no item is served on a license Antiek does not hold. CC-BY /
CC-BY-SA / CC0 / CC-PDM -> servable; bronze OA / CC-NC / CC-ND / unknown /
missing -> GATED. "Free to read" is NEVER "free to redistribute."

Sources:
  --source openalex   discovery: --query / --author -> candidate works; the
                      work's best-OA PDF + license are resolved inline.
  --source unpaywall  --dois -> Unpaywall best-OA-location PDF + license.
  --source pmc        --dois -> Europe PMC OA full text + per-article license.
  --source doaj       --dois -> journal-level OA confirmation + license. DOAJ
                      does not host PDFs, so doaj is confirmation-only and is
                      rejected for a real (writing) run unless paired.

Usage:
    # report the rights decision per item, write nothing
    python -m tools.ingest_open_access --source openalex --query "graph neural networks" --dry-run
    python -m tools.ingest_open_access --source unpaywall --dois 10.1371/journal.pone.0000308 --dry-run

    # real run into a LOCAL/TEMP DuckDB (never prod)
    python -m tools.ingest_open_access --source unpaywall \\
        --dois 10.1371/journal.pone.0000308 --db-path /tmp/antiek-oa.duckdb

Constraints (hard): never targets prod. ``--db-path`` is required for a real
run and must NOT resolve to the substrate default. Per-item failures are
logged and the batch continues. Prod ingest is SPR-06.
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

from acquisition.openaccess import OAThrottle, resolve_oa_license  # noqa: E402
from acquisition.openaccess import doaj, openalex, pmc, unpaywall  # noqa: E402
from acquisition.openaccess.ingest import (  # noqa: E402
    build_license_basis,
    ingest_oa_item,
)
from acquisition.openaccess.licenses import LicenseResolution  # noqa: E402

logger = logging.getLogger("tools.ingest_open_access")

SOURCES = ("openalex", "unpaywall", "pmc", "doaj")


@dataclass(frozen=True)
class Candidate:
    """A resolved OA candidate ready to route. ``pdf_url`` is None when the
    source confirmed OA/license but resolved no fetchable PDF (DOAJ always;
    a landing-page-only Unpaywall/PMC hit) — such an item can be reported but
    not ingested."""

    doi: Optional[str]
    title: str
    pdf_url: Optional[str]
    license_uri: Optional[str]
    resolution: LicenseResolution
    source: str
    how: str
    # Ordered PDF-URL candidates from OpenAlex (best/primary/locations[].pdf_url,
    # then the landing url last). Empty for the DOI-keyed sources, which resolve
    # a single best-OA pdf_url. The OA ingest thunk walks these in order so a
    # leading HTML landing page no longer fails the whole item. Defaulted, so
    # the unpaywall/pmc/doaj construction sites are unchanged.
    pdf_url_candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchReport:
    candidates: int
    servable: int
    gated: int
    failed: int
    no_pdf: int


def _resolve_candidates(
    *,
    source: str,
    query: Optional[str],
    author: Optional[str],
    dois: Optional[Sequence[str]],
    limit: int,
    throttle: OAThrottle,
) -> List[Candidate]:
    """Resolve the selectors to a candidate list for the chosen source. Each
    candidate carries its deny-by-default license verdict already computed."""
    out: List[Candidate] = []
    if source == "openalex":
        works = openalex.search_works(
            search=query, author=author, per_page=limit, throttle=throttle
        )
        for w in works:
            out.append(
                Candidate(
                    doi=w.doi,
                    title=w.title,
                    pdf_url=w.best_oa_pdf_url,
                    pdf_url_candidates=w.pdf_url_candidates,
                    license_uri=w.license_uri,
                    resolution=resolve_oa_license(w.license_uri),
                    source="OpenAlex best-OA-location",
                    how="per OpenAlex best_oa_location.license",
                )
            )
        return out

    # The DOI-keyed resolvers.
    for doi in dois or []:
        try:
            if source == "unpaywall":
                ft = unpaywall.resolve_doi(doi, throttle=throttle)
                out.append(
                    Candidate(
                        doi=ft.doi, title="", pdf_url=ft.pdf_url,
                        license_uri=ft.license_uri, resolution=ft.resolution,
                        source="Unpaywall best-OA-location",
                        how="per best_oa_location.license",
                    )
                )
            elif source == "pmc":
                art = pmc.resolve_by_doi(doi, throttle=throttle)
                if art is None:
                    logger.warning("pmc: no record for %s", doi)
                    continue
                out.append(
                    Candidate(
                        doi=art.doi or doi, title=art.title, pdf_url=art.pdf_url,
                        license_uri=art.license_uri, resolution=art.resolution,
                        source="Europe PMC", how="per article-level license",
                    )
                )
            elif source == "doaj":
                art = doaj.confirm_by_doi(doi, throttle=throttle)
                if art is None:
                    logger.warning("doaj: no record for %s", doi)
                    continue
                out.append(
                    Candidate(
                        doi=art.doi or doi, title=art.title,
                        pdf_url=None,  # DOAJ does not host PDFs
                        license_uri=art.license_uri, resolution=art.resolution,
                        source="DOAJ journal-level",
                        how="per journal-level license",
                    )
                )
        except httpx.HTTPStatusError as exc:
            logger.warning("%s: %s -> %s", source, doi, exc)
            continue
        except Exception as exc:  # never let one DOI kill discovery
            logger.warning("%s: failed to resolve %s: %s", source, doi, exc)
            continue
    return out


def _print_dry_run(cands: Sequence[Candidate]) -> None:
    print(f"DRY RUN — {len(cands)} candidate(s), nothing written:\n")
    for c in cands:
        verdict = "SERVABLE" if c.resolution.redistributable else "GATED"
        pdf = c.pdf_url or "(no fetchable PDF)"
        print(f"  [{verdict}] {c.doi or '(no doi)'} — {c.title[:70]}")
        print(f"      license: {c.license_uri or '(none declared)'}")
        print(f"      -> {c.resolution.content_class} ({c.resolution.license_name})")
        print(f"      pdf: {pdf}")
        print(f"      why: {c.resolution.rationale}")
        print()


def _source_fetcher(source: str, throttle: OAThrottle):
    """The per-source PDF byte fetcher (a pdf_url -> bytes callable)."""
    if source in ("openalex", "unpaywall"):
        return lambda url: unpaywall.download_pdf(url, throttle=throttle)
    if source == "pmc":
        return lambda url: pmc.download_pdf(url, throttle=throttle)
    raise ValueError(f"source {source} has no PDF fetcher")


def run_batch(
    cands: Sequence[Candidate],
    *,
    source: str,
    investigation_id: str,
    db_path: str,
    throttle: OAThrottle,
) -> BatchReport:
    servable = gated = failed = no_pdf = 0
    fetch_pdf = _source_fetcher(source, throttle)
    for c in cands:
        if not c.pdf_url:
            no_pdf += 1
            logger.info("%s: no fetchable PDF, skipping ingest", c.doi)
            continue
        basis = build_license_basis(c.resolution, source=c.source, how=c.how)
        try:
            result = ingest_oa_item(
                investigation_id=investigation_id,
                doi=c.doi,
                pdf_url=c.pdf_url,
                resolution=c.resolution,
                license_basis=basis,
                fetch_pdf=fetch_pdf,
                db_path=db_path,
            )
        except Exception as exc:  # transient errors already retried in fetcher
            failed += 1
            logger.warning("failed to ingest %s: %s", c.doi, exc)
            continue
        if result.servable_full_text:
            servable += 1
        else:
            gated += 1
        logger.info(
            "ingested %s -> %s (%s) [%s]",
            c.doi, result.content_class, result.servability,
            "servable" if result.servable_full_text else "gated",
        )
    return BatchReport(
        candidates=len(cands), servable=servable, gated=gated,
        failed=failed, no_pdf=no_pdf,
    )


def _is_prod_db(db_path: str) -> bool:
    """Guard against ever pointing this CLI at the prod DB. Mirrors SPR-02:
    the prod path is the substrate default; requiring an explicit --db-path
    and rejecting that default keeps 'never write to prod' mechanical."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.ingest_open_access",
        description="Ingest open-access papers, license-gated, into a LOCAL Antiek DB.",
    )
    p.add_argument("--source", choices=SOURCES, required=True, help="OA aggregator")
    sel = p.add_argument_group("selection")
    sel.add_argument("--query", help="full-text search (openalex)")
    sel.add_argument("--author", help="author name filter (openalex)")
    sel.add_argument("--dois", help="comma-separated DOIs (unpaywall/pmc/doaj)")
    p.add_argument("--limit", type=int, default=25, help="max works (openalex)")
    p.add_argument(
        "--investigation-id", default="inv-open-access",
        help="investigation id stamped on ingested docs",
    )
    p.add_argument(
        "--db-path",
        help="LOCAL/TEMP DuckDB path (required for a real run; never prod)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="report content_class + license per item; write nothing",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    dois: Optional[List[str]] = None
    if args.dois:
        dois = [x.strip() for x in args.dois.split(",") if x.strip()]

    if args.source == "openalex":
        if not (args.query or args.author):
            print("error: openalex needs --query or --author", file=sys.stderr)
            return 2
    else:
        if not dois:
            print(f"error: {args.source} needs --dois", file=sys.stderr)
            return 2

    if not args.dry_run:
        if args.source == "doaj":
            print(
                "error: doaj is OA-confirmation only (no hosted PDF); use it "
                "for --dry-run or pair with unpaywall/pmc for a real run",
                file=sys.stderr,
            )
            return 2
        if not args.db_path:
            print("error: --db-path is required for a real run", file=sys.stderr)
            return 2
        if _is_prod_db(args.db_path):
            print(
                "error: --db-path resolves to the prod substrate default; this "
                "CLI may only write to a LOCAL/TEMP DB (prod ingest is SPR-06)",
                file=sys.stderr,
            )
            return 2

    throttle = OAThrottle()
    try:
        cands = _resolve_candidates(
            source=args.source, query=args.query, author=args.author,
            dois=dois, limit=args.limit, throttle=throttle,
        )
    except Exception as exc:
        print(f"error: {args.source} discovery failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(cands)
        return 0

    report = run_batch(
        cands, source=args.source, investigation_id=args.investigation_id,
        db_path=args.db_path, throttle=throttle,
    )
    print(
        f"\ningested {report.candidates - report.failed - report.no_pdf} / "
        f"{report.candidates}; {report.servable} servable, {report.gated} gated, "
        f"{report.no_pdf} no-pdf, {report.failed} failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

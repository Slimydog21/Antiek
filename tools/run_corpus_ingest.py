"""Unified, quality-gated, deduped corpus-ingest orchestrator (SPR-08).

This is the one orchestrator the per-source CLIs (``ingest_public_domain``,
``ingest_arxiv``, ``ingest_open_access``) pointed at with "prod ingest is
SPR-08". It wires the three rights-correct connectors through a single plan:

    discover (each connector, as-is)
        → normalize to CandidateRef + assessable text + an ingest thunk
        → cross-source dedup            (acquisition.corpus_quality.dedup_candidates)
        → corpus-quality gate           (acquisition.corpus_quality.assess_corpus_quality)
        → ingest the kept ∩ passing     (through the connectors' own connect_write path)

The orchestration does NOT reimplement acquisition: discovery and ingest call
the existing connector functions. It adds only the cross-source plan (dedup +
gate + reporting) on top.

Two honest design boundaries, documented because the gate's strength depends
on them (intellectual honesty):

1. **What text the gate sees, per source.** The OCR-garbage / real-word
   checks need the document body. We assess on the richest text available
   *without a connector rewrite*:
     - public-domain: the downloaded plain-text body (boilerplate-stripped)
       WHEN Gutenberg serves a text format — that is where the OCR/garble
       checks bite hardest. Note ``gutenberg_candidates`` PREFERS a PDF when
       one is offered (most books have one), and a PDF body is extracted only
       at ingest, not here; such works are gated metadata-only and flagged
       ``[body not assessed pre-ingest]``. So the body checks run on the
       text-format subset, honestly reported, not on every PD work;
     - arXiv: the abstract (born-digital LaTeX; full-PDF OCR garble is
       negligible, and the abstract is real prose ≥ the gate's token floor);
     - open-access: metadata only at discovery (the body is a publisher PDF
       fetched at ingest), so the gate runs ``assess_body=False`` — running
       the text checks on a title would spuriously reject a clean born-digital
       paper. The verdict records ``body_assessed=False`` so this is reported,
       never hidden.

2. **Dry-run vs real write.** ``--dry-run`` (the default-safe mode) runs the
   FULL plan — discovery, body fetch for assessment, dedup, gate, and the
   rejection-rate report — and writes NOTHING. A real run additionally calls
   the per-candidate ingest thunk, which writes through the connectors'
   ``runtime.db_lock.connect_write`` single-writer path. Writing to the prod
   substrate default is refused unless ``--allow-prod-write`` is given AND the
   single-writer lock is free; that flag is the operator's, exercised per the
   runbook (``infrastructure/runbooks/corpus-ingest.md``) — never autonomously.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Optional

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# Defensive SSL bootstrap: a python.org-3.11 interpreter ships without a system
# CA bundle (the arxiv-missing-ssl-env failure mode). Point at certifi when the
# env is unset so the HTTPS handshake to arxiv.org / OA sources does not fail
# silently mid-window. Idempotent and read-only w.r.t. the DB.
if not os.environ.get("SSL_CERT_FILE"):
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(certifi.where()))
    except Exception:
        pass  # certifi absent -> leave env as-is; fall through to system default

from acquisition.corpus_quality import (  # noqa: E402
    CandidateRef,
    DedupResult,
    QualityRunReport,
    QualityVerdict,
    aggregate_verdicts,
    assess_corpus_quality,
    dedup_candidates,
)

logger = logging.getLogger("tools.run_corpus_ingest")


# ---------------------------------------------------------------------------
# Pure core — the testable seam. Operates over already-materialized
# candidates; no network, no DB. Discovery (below) builds these.
# ---------------------------------------------------------------------------


# An ingest thunk takes the target db_path and performs the real write through
# the owning connector, returning a short human status (e.g. the document id).
IngestThunk = Callable[[str], str]


@dataclass(frozen=True)
class PlannedCandidate:
    """One discovered work, normalized for planning + ingest.

    ``ref`` drives dedup. ``assessable_text`` + ``assess_body`` drive the
    quality gate (see the module docstring's per-source boundary). ``ingest``
    is the deferred write — called ONLY on a real run, never during planning
    or dry-run — so the plan stays a pure, side-effect-free computation.
    """

    ref: CandidateRef
    source: str  # "public_domain" | "arxiv" | "open_access"
    assessable_text: str
    assess_body: bool
    ingest: IngestThunk
    allow_null_author_reason: Optional[str] = None

    def quality_verdict(self) -> QualityVerdict:
        """Gate this candidate on the text available for its source. The
        metadata identifier is the highest-precedence id the ref carries
        (DOI / arXiv id / source id) — the same identity the dedup keys on."""
        identifier = self.ref.doi or self.ref.arxiv_id or self.ref.source_id
        return assess_corpus_quality(
            self.assessable_text,
            title=self.ref.title,
            author=self.ref.author,
            source_id=identifier,
            allow_null_author_reason=self.allow_null_author_reason,
            assess_body=self.assess_body,
        )


@dataclass(frozen=True)
class CorpusPlan:
    """The computed ingest plan: what survives dedup + the quality gate, what
    each stage dropped, and the rejection-rate report. Fully determined by the
    input candidates — building it writes nothing."""

    deduped: DedupResult
    to_ingest: tuple[PlannedCandidate, ...]
    quality_rejected: tuple[tuple[PlannedCandidate, QualityVerdict], ...]
    quality_report: QualityRunReport

    def render(self) -> str:
        lines: list[str] = []
        lines.append(self.deduped.render())
        lines.append(self.quality_report.render())
        if self.quality_rejected:
            lines.append("quality rejections:")
            for pc, verdict in self.quality_rejected:
                lines.append(
                    f"  [{pc.source}] {pc.ref.title or pc.ref.ref_id}: "
                    f"{verdict.rejection_reason}"
                )
        lines.append("would ingest:")
        if not self.to_ingest:
            lines.append("  (nothing)")
        for pc in self.to_ingest:
            note = "" if pc.assess_body else "  [body not assessed pre-ingest]"
            lines.append(
                f"  [{pc.source}] {pc.ref.title or pc.ref.ref_id}{note}"
            )
        return "\n".join(lines)


def plan_corpus(candidates: Sequence[PlannedCandidate]) -> CorpusPlan:
    """Compute the ingest plan: dedup first (cheap, identity-based), then gate
    only the survivors (so we don't pay quality assessment for duplicates).

    Pure: no network, no DB, no ingest thunk is called. The plan a dry-run
    prints and the plan a real run executes are the SAME object — there is no
    second, divergent code path that could quietly ingest something the
    dry-run did not show (defensibility).
    """
    by_ref_id = {c.ref.ref_id: c for c in candidates}
    deduped = dedup_candidates([c.ref for c in candidates])

    to_ingest: list[PlannedCandidate] = []
    quality_rejected: list[tuple[PlannedCandidate, QualityVerdict]] = []
    verdicts: list[QualityVerdict] = []
    for ref in deduped.kept:
        pc = by_ref_id[ref.ref_id]
        verdict = pc.quality_verdict()
        verdicts.append(verdict)
        if verdict.passed:
            to_ingest.append(pc)
        else:
            quality_rejected.append((pc, verdict))

    return CorpusPlan(
        deduped=deduped,
        to_ingest=tuple(to_ingest),
        quality_rejected=tuple(quality_rejected),
        quality_report=aggregate_verdicts(verdicts),
    )


@dataclass(frozen=True)
class ExecuteReport:
    """Outcome of executing a plan. On a dry-run, ``ingested`` and ``failed``
    are 0 and ``dry_run`` is True — nothing was written."""

    planned: int
    ingested: int
    failed: int
    dry_run: bool
    statuses: tuple[str, ...] = field(default_factory=tuple)


def execute_plan(
    plan: CorpusPlan, *, db_path: Optional[str], dry_run: bool
) -> ExecuteReport:
    """Ingest the plan's ``to_ingest`` set. On ``dry_run`` no thunk is called
    and nothing is written. Per-item failures are isolated so one bad fetch
    does not abort the batch.
    """
    planned = len(plan.to_ingest)
    if dry_run:
        return ExecuteReport(
            planned=planned, ingested=0, failed=0, dry_run=True
        )
    if not db_path:
        raise ValueError("db_path is required for a real (non-dry-run) ingest")

    ingested = failed = 0
    statuses: list[str] = []
    for pc in plan.to_ingest:
        try:
            status = pc.ingest(db_path)
        except Exception as exc:  # never let one item kill the batch
            failed += 1
            logger.warning(
                "failed to ingest [%s] %s: %s", pc.source, pc.ref.ref_id, exc
            )
            continue
        ingested += 1
        statuses.append(status)
        logger.info("ingested [%s] %s → %s", pc.source, pc.ref.ref_id, status)
    return ExecuteReport(
        planned=planned, ingested=ingested, failed=failed,
        dry_run=False, statuses=tuple(statuses),
    )


# ---------------------------------------------------------------------------
# Discovery adapters — the network edge. Each maps a connector's records into
# PlannedCandidates. Kept thin: the connectors own their own tests; these only
# normalize + close over the ingest call.
# ---------------------------------------------------------------------------


def _arxiv_candidates(
    *, query: Optional[str], category: Optional[str],
    ids: Optional[Sequence[str]], limit: int, investigation_id: str,
) -> list[PlannedCandidate]:
    import httpx

    from acquisition.arxiv import (
        ArxivBanned,
        ArxivPaper,
        ArxivThrottle,
        ingest_paper_with_rights,
        search,
    )
    from acquisition.arxiv.client import fetch_by_id
    from tools.ingest_arxiv import _request_with_429_sentinel

    throttle = ArxivThrottle()
    papers: list[ArxivPaper] = []
    # Isolate arXiv discovery like the PD/OA paths: a live 429 (export.arxiv.org
    # IP-ban) is recorded to the throttle's banned_until sentinel (so the NEXT
    # run honors the ban instead of re-hitting and EXTENDING it) and degrades to
    # zero arXiv candidates — it must NOT abort the whole multi-source run.
    # SPR-09 M1: the throttle is threaded into search/fetch_by_id, which route the
    # export-search GET through the host-global rate governor (fcntl.flock around
    # the >=3s spacing + ban sentinel) so this discovery contends on the SAME gate
    # as a concurrent OAI harvest / PDF fetch — two host jobs can no longer both
    # fire in one 3s window.
    # This does NOT let arXiv ingest SUCCEED while the ban is active; it only
    # stops extending the ban and stops aborting PD+OA. arXiv resumes once
    # banned_until elapses. (S2 metadata fallback is deliberately NOT used: S2
    # omits the arXiv license element, so it would deny-gate every CC-BY paper.)
    try:
        if ids:
            for pid in ids:
                # Pre-flight ban check: if a sentinel is already active this raises
                # ArxivBanned WITHOUT constructing any request, so discovery
                # degrades to [] without touching the banned endpoint. The
                # authoritative spacing + ban gate is the governor's flock (held
                # inside search/fetch_by_id); this pre-check only short-circuits a
                # known-banned run early.
                throttle.wait_if_needed()
                p = _request_with_429_sentinel(
                    throttle, lambda pid=pid: fetch_by_id(pid, throttle=throttle)
                )
                if p is not None:
                    papers.append(p)
        else:
            throttle.wait_if_needed()
            papers = list(
                _request_with_429_sentinel(
                    throttle,
                    lambda: search(
                        query=query, category=category,
                        max_results=limit, throttle=throttle,
                    ),
                )
            )
    except ArxivBanned as exc:
        logger.error("arxiv banned, skipping arxiv discovery: %s", exc)
        return []
    except httpx.HTTPStatusError as exc:
        logger.error("arxiv discovery http error, skipping arxiv: %s", exc)
        return []

    out: list[PlannedCandidate] = []
    for p in papers:
        author = p.authors[0] if p.authors else None

        def _ingest(db_path: str, _p: ArxivPaper = p) -> str:
            throttle.wait_if_needed()
            result = ingest_paper_with_rights(
                _p, investigation_id=investigation_id, db_path=db_path
            )
            return f"{result.content_class} ({result.servability})"

        out.append(
            PlannedCandidate(
                ref=CandidateRef(
                    ref_id=f"arxiv:{p.arxiv_id}",
                    arxiv_id=p.arxiv_id,
                    title=p.title,
                    author=author,
                ),
                source="arxiv",
                assessable_text=p.abstract,  # born-digital; abstract is prose
                assess_body=True,
                ingest=_ingest,
            )
        )
    return out


class _BodyCachingClient:
    """Wraps a public-domain ``SourceClient`` and memoizes ``get_bytes`` by URL.

    The amplifier behind the SPR-08 dry-run/real-run reliability gap: a
    text-format work's body is fetched once by ``_fetch_pd_body`` (for the
    quality gate) and again by ``ingest_work`` (for the write), doubling
    gutendex load in the maintenance window — which is what pushed gutendex
    into the 503/timeout regime a real run hit but a dry-run did not. Memoizing
    by URL collapses that to a single fetch. ``get_json`` is deliberately NOT
    cached (paging/metadata must stay live). The PD code paths use only these
    two methods (verified)."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self._body_cache: dict[str, bytes] = {}

    def get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        return self._inner.get_json(url, params=params)  # type: ignore[attr-defined]

    def get_bytes(self, url: str) -> bytes:
        if url not in self._body_cache:
            self._body_cache[url] = self._inner.get_bytes(url)  # type: ignore[attr-defined]
        return self._body_cache[url]


def _public_domain_candidates(
    *, subject: Optional[str], search_term: Optional[str],
    ids: Optional[Sequence[int]], curated: bool, limit: int,
    investigation_id: str, min_interval_s: float,
) -> list[PlannedCandidate]:
    from acquisition.books.public_domain import (
        PublicDomainWork,
        SourceClient,
        SourceError,
        gutenberg_candidates,
        ingest_work,
        strip_gutenberg_boilerplate,
    )
    from tools.ingest_public_domain import CURATED_GUTENBERG_IDS

    client = _BodyCachingClient(SourceClient(min_interval_s=min_interval_s))
    selected_ids: Optional[Sequence[int]] = ids
    if curated:
        selected_ids = list(CURATED_GUTENBERG_IDS)
        limit = max(limit, len(selected_ids))
    try:
        works = gutenberg_candidates(
            client, subject=subject, search=search_term, ids=selected_ids, limit=limit
        )
    except SourceError as exc:
        # A transient gutendex 503/timeout during PD discovery must NOT abort
        # the whole run (and block OA, which runs after PD). Isolate it like the
        # OA discovery path does per item; the run proceeds with the other
        # sources and reports zero PD candidates this pass. This restores the
        # contract SourceClient documents: a retry-exhausted request "raises
        # SourceError for the caller to catch per-item — it must NOT abort the
        # batch."
        logger.warning(
            "public-domain discovery failed (transient source error); "
            "skipping PD this run: %s",
            exc,
        )
        return []

    out: list[PlannedCandidate] = []
    for w in works:
        body = _fetch_pd_body(client, w, strip_gutenberg_boilerplate)

        def _ingest(db_path: str, _w: PublicDomainWork = w) -> str:
            outcome = ingest_work(
                _w, client, investigation_id=investigation_id, db_path=db_path
            )
            if outcome.ingested:
                return f"{outcome.document_id} ({outcome.word_count} words)"
            return f"skipped: {outcome.skipped_reason}"

        out.append(
            PlannedCandidate(
                ref=CandidateRef(
                    ref_id=f"{w.source}:{w.source_id}",
                    source_id=w.source_id,
                    title=w.title,
                    author=w.author,
                ),
                source="public_domain",
                assessable_text=body,
                # The downloaded body IS the text we'd ingest → assess it.
                assess_body=bool(body),
                ingest=_ingest,
                allow_null_author_reason=(
                    "public-domain work with no recorded author"
                    if not (w.author and w.author.strip())
                    else None
                ),
            )
        )
    return out


def _fetch_pd_body(
    client: object, work: object, strip: Callable[[str], str]
) -> str:
    """Best-effort download of the public-domain body for quality assessment.
    A fetch failure yields "" → the gate runs metadata-only for that work
    rather than aborting the plan (the real ingest will surface the failure)."""
    if getattr(work, "download_format", None) != "text":
        # PDF bodies are extracted at ingest by the reader, not assessed here —
        # so do not pay the download for them; the gate runs metadata-only.
        return ""
    try:
        raw = client.get_bytes(work.download_url)  # type: ignore[attr-defined]
    except Exception as exc:  # discovery is best-effort; ingest re-tries
        logger.warning(
            "could not fetch body for %s: %s",
            getattr(work, "source_uri", "?"), exc,
        )
        return ""
    try:
        text: str = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", "replace")
    if getattr(work, "source", None) == "project_gutenberg":
        text = strip(text)
    return text


def _open_access_candidates(
    *, source: str, query: Optional[str], author: Optional[str],
    dois: Optional[Sequence[str]], limit: int, investigation_id: str,
) -> list[PlannedCandidate]:
    from acquisition.openaccess import OAThrottle
    from acquisition.openaccess.ingest import build_license_basis, ingest_oa_item
    from tools.ingest_open_access import Candidate, _resolve_candidates, _source_fetcher

    throttle = OAThrottle()
    cands: list[Candidate] = _resolve_candidates(
        source=source, query=query, author=author,
        dois=dois, limit=limit, throttle=throttle,
    )
    fetch_pdf = _source_fetcher(source, throttle) if source != "doaj" else None

    out: list[PlannedCandidate] = []
    for c in cands:
        basis = build_license_basis(c.resolution, source=c.source, how=c.how)

        # Try each candidate PDF URL in order; a NotAPdf / landing-page response
        # is a recoverable miss -> fall through to the next candidate. Only when
        # ALL candidates fail does the item fail (still per-item isolated by
        # execute_plan's per-candidate try/except). Falls back to the single
        # pdf_url for the DOI-keyed sources, which expose no candidate list.
        _urls = tuple(c.pdf_url_candidates or ([c.pdf_url] if c.pdf_url else ()))

        def _ingest(
            db_path: str, _c: Candidate = c, _basis: str = basis, _urls=_urls
        ) -> str:
            if not _urls or fetch_pdf is None:
                return "skipped: no fetchable PDF"
            from acquisition.openaccess.unpaywall import NotAPdf

            last_exc: Optional[Exception] = None
            for u in _urls:
                try:
                    result = ingest_oa_item(
                        investigation_id=investigation_id,
                        doi=_c.doi, pdf_url=u, resolution=_c.resolution,
                        license_basis=_basis, fetch_pdf=fetch_pdf, db_path=db_path,
                    )
                    return f"{result.content_class} ({result.servability})"
                except NotAPdf as exc:
                    last_exc = exc
                    continue
            raise last_exc or ValueError("no candidate URL yielded a PDF")

        out.append(
            PlannedCandidate(
                ref=CandidateRef(
                    ref_id=f"oa:{c.doi or c.title}",
                    doi=c.doi,
                    title=c.title or None,
                    author=None,  # OA discovery records carry no author field
                ),
                source="open_access",
                assessable_text="",  # body is the publisher PDF, fetched at ingest
                assess_body=False,
                ingest=_ingest,
                allow_null_author_reason="open-access record exposes no author at discovery",
            )
        )
    return out


# ---------------------------------------------------------------------------
# Prod-write safety.
# ---------------------------------------------------------------------------


def _is_prod_db(db_path: str) -> bool:
    """True iff db_path resolves to the prod substrate default. Mirrors the
    per-source CLIs' mechanical 'never write prod by accident' guard."""
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def _assert_lock_free(db_path: str) -> None:
    """Pre-flight: confirm the single-writer lock is free before a prod write.
    A running uvicorn holds it; ingesting then would block until timeout. We
    acquire+release with a short deadline so the operator gets an immediate,
    legible 'stop the service first' instead of a 5-minute stall."""
    from runtime.db_lock import WriteLockTimeout, connect_write

    try:
        with connect_write(db_path, timeout_s=5, purpose="corpus-ingest preflight"):
            pass
    except WriteLockTimeout as exc:
        raise SystemExit(
            f"error: the single-writer lock on {db_path} is held — stop the "
            f"antiek.service (uvicorn) before a prod ingest. ({exc})"
        ) from exc


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.run_corpus_ingest",
        description=(
            "Unified quality-gated, deduped corpus ingest across the "
            "public-domain / arXiv / open-access connectors."
        ),
    )
    p.add_argument(
        "--source", action="append", dest="sources",
        choices=("public_domain", "arxiv", "open_access"),
        help="source to include (repeatable); default: all selected sources",
    )
    # public-domain selectors
    p.add_argument("--pd-subject", help="public-domain: Gutenberg subject")
    p.add_argument("--pd-search", help="public-domain: Gutenberg search term")
    p.add_argument("--pd-ids", help="public-domain: comma-separated Gutenberg ids")
    p.add_argument("--pd-curated", action="store_true", help="public-domain: curated spine")
    # arxiv selectors
    p.add_argument("--arxiv-query", help="arXiv: search query")
    p.add_argument("--arxiv-category", help="arXiv: category, e.g. cs.LG")
    p.add_argument("--arxiv-ids", help="arXiv: comma-separated ids")
    # open-access selectors
    p.add_argument(
        "--oa-source", choices=("openalex", "unpaywall", "pmc", "doaj"),
        help="open-access aggregator",
    )
    p.add_argument("--oa-query", help="open-access: openalex search query")
    p.add_argument("--oa-author", help="open-access: openalex author")
    p.add_argument("--oa-dois", help="open-access: comma-separated DOIs")
    # shared
    p.add_argument("--limit", type=int, default=25, help="per-source max")
    p.add_argument("--investigation-id", default="inv-corpus", help="investigation id stamped on docs")
    p.add_argument("--db-path", help="target DuckDB (required for a real run)")
    p.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    p.add_argument(
        "--allow-prod-write", action="store_true",
        help="permit writing to the prod substrate default (operator-only; see runbook)",
    )
    p.add_argument(
        "--pd-min-interval", type=float, default=1.0,
        help="public-domain: min seconds between source requests",
    )
    return p


def _csv_ints(value: Optional[str]) -> Optional[list[int]]:
    if not value:
        return None
    return [int(x) for x in value.split(",") if x.strip()]


def _csv_strs(value: Optional[str]) -> Optional[list[str]]:
    if not value:
        return None
    return [x.strip() for x in value.split(",") if x.strip()]


def discover_all(args: argparse.Namespace) -> list[PlannedCandidate]:
    """Run the selected sources' discovery adapters and concatenate. A source
    is included when explicitly named in --source, or (when --source is
    omitted) when any of its selectors is present."""
    sources = set(args.sources or [])
    candidates: list[PlannedCandidate] = []

    want_pd = "public_domain" in sources or (
        not sources and (args.pd_subject or args.pd_search or args.pd_ids or args.pd_curated)
    )
    want_arxiv = "arxiv" in sources or (
        not sources and (args.arxiv_query or args.arxiv_category or args.arxiv_ids)
    )
    want_oa = "open_access" in sources or (
        not sources and args.oa_source
    )

    if want_pd:
        candidates += _public_domain_candidates(
            subject=args.pd_subject, search_term=args.pd_search,
            ids=_csv_ints(args.pd_ids), curated=args.pd_curated,
            limit=args.limit, investigation_id=args.investigation_id,
            min_interval_s=args.pd_min_interval,
        )
    if want_arxiv:
        candidates += _arxiv_candidates(
            query=args.arxiv_query, category=args.arxiv_category,
            ids=_csv_strs(args.arxiv_ids), limit=args.limit,
            investigation_id=args.investigation_id,
        )
    if want_oa:
        if not args.oa_source:
            raise SystemExit("error: open-access needs --oa-source")
        candidates += _open_access_candidates(
            source=args.oa_source, query=args.oa_query, author=args.oa_author,
            dois=_csv_strs(args.oa_dois), limit=args.limit,
            investigation_id=args.investigation_id,
        )
    return candidates


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    if not args.dry_run:
        if not args.db_path:
            print("error: --db-path is required for a real run", file=sys.stderr)
            return 2
        if _is_prod_db(args.db_path):
            if not args.allow_prod_write:
                print(
                    "error: --db-path resolves to the prod substrate default. "
                    "A prod corpus ingest is an operator step: re-run with "
                    "--allow-prod-write after taking a backup and stopping the "
                    "writer (see infrastructure/runbooks/corpus-ingest.md).",
                    file=sys.stderr,
                )
                return 2
            _assert_lock_free(args.db_path)

    try:
        candidates = discover_all(args)
    except SystemExit:
        raise
    except Exception as exc:  # network / parse failure during discovery
        print(f"error: discovery failed: {exc}", file=sys.stderr)
        return 1

    if not candidates:
        print("no candidates discovered (check your selectors)", file=sys.stderr)
        return 1

    plan = plan_corpus(candidates)
    header = "DRY RUN — nothing written\n" if args.dry_run else "INGEST PLAN\n"
    print(header + plan.render())

    report = execute_plan(plan, db_path=args.db_path, dry_run=args.dry_run)
    if report.dry_run:
        print(f"\ndry-run: {report.planned} would be ingested; wrote nothing")
    else:
        print(
            f"\ningested {report.ingested} / {report.planned} planned; "
            f"{report.failed} failed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

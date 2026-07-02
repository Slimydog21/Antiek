"""Unified, quality-gated, deduped corpus-ingest orchestrator (SPR-08).

This is the one orchestrator the per-source CLIs (``ingest_public_domain``,
``ingest_arxiv``, ``ingest_open_access``) pointed at with "prod ingest is
SPR-08". It wires the three rights-correct connectors through a single plan:

    discover (each connector, as-is)
        → normalize to CandidateRef + assessable text + an ingest thunk
        → cross-source dedup            (acquisition.corpus_quality.dedup_candidates,
                                         keyed on the single substrate.dedup identity)
        → corpus-quality gate           (acquisition.corpus_quality.assess_corpus_quality)
        → ingest the kept ∩ passing     (through the connectors' own connect_write path)

The orchestration does NOT reimplement acquisition: discovery and ingest call
the existing connector functions. It adds only the cross-source plan (dedup +
gate + reporting) on top.

Identity is ONE fact, computed once. ``dedup_candidates`` keys its cross-source
clusters through ``substrate.dedup`` (DOI > ISBN-13 > arXiv-id > source-id >
content-hash > title+author, LOW). The very key that decided a candidate is a
duplicate is the key the plan stamps as that candidate's ``document_id`` basis
(``substrate.dedup.identity_basis``) — the contract SPR-01 consumes to derive
the content-stable ``document_id`` so a re-ingest is a no-op at BOTH the dedup
layer and SPR-01's ``on_conflict=ignore`` merge. There is no second, divergent
identity ladder: the dedup driver and the document_id basis are the same value.

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
from substrate.dedup import (  # noqa: E402
    Confidence,
    IdentityKey,
    identity_basis,
    identity_key,
)

logger = logging.getLogger("tools.run_corpus_ingest")


# ---------------------------------------------------------------------------
# Pure core — the testable seam. Operates over already-materialized
# candidates; no network, no DB. Discovery (below) builds these.
# ---------------------------------------------------------------------------


# An ingest thunk takes the target db_path AND the candidate's content-stable
# document_id basis (the SPR-04 identity SPR-01 derives the document_id from),
# performs the real write through the owning connector, and returns a short
# human status. The basis is passed to the write boundary so the identity the
# plan computed is the identity that reaches ingest — not a value computed and
# discarded. SPR-01's merge consumes it as the on_conflict=ignore document_id;
# until SPR-01 lands the connectors still mint their own ids, so today's thunks
# accept the basis and forward/record it (the documented seam, not a no-op).
IngestThunk = Callable[[str, str], str]


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
    allow_null_author_reason: str | None = None

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

    def identity(self) -> IdentityKey:
        """The content-stable identity key — the SAME key
        ``dedup_candidates`` keyed this candidate's cluster on (it keys through
        ``substrate.dedup`` too), and (via ``identity_basis``) the basis SPR-01
        turns into the document_id. The dedup decision and the idempotency
        contract are the same fact, computed once.

        ``CandidateRef`` carries the identity-bearing fields (doi / isbn /
        arxiv_id / source_id / title / author / body), so this just resolves
        that ref — there is no second projection that could disagree with what
        dedup keyed on."""
        return identity_key(self.ref.identity_record())


@dataclass(frozen=True)
class IdentityReport:
    """Run-level identity coverage over the kept candidates — the per-key-type
    distribution (incl. how many works rest only on the LOW-confidence
    fallback, the rigor-#1 coverage gap a run must report rather than hide).

    This is derived from the SAME ``substrate.dedup`` identity the cross-source
    dedup keyed on, not a second pass: the key that decided each survivor's
    identity is the key counted here and stamped as its document_id basis."""

    kept: int
    key_type_counts: dict[str, int]
    low_confidence: int

    def render(self) -> str:
        dist = ", ".join(
            f"{kt}={n}" for kt, n in sorted(self.key_type_counts.items())
        )
        return (
            f"identity: {self.kept} works with stable ids; "
            f"key types: {dist or '(none)'}; "
            f"low-confidence fallback: {self.low_confidence}"
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
    # The per-key-type identity distribution over the kept set (rigor #1) and
    # the document_id basis SPR-01 consumes per kept candidate. Both are read
    # off the SAME substrate.dedup identity that drove dedup above — not a
    # second, report-only ladder.
    identity_report: IdentityReport
    document_id_bases: tuple[tuple[str, str], ...] = ()  # (ref_id, basis)

    def render(self) -> str:
        lines: list[str] = []
        lines.append(self.deduped.render())
        lines.append(self.identity_report.render())
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
        bases = dict(self.document_id_bases)
        for pc in self.to_ingest:
            note = "" if pc.assess_body else "  [body not assessed pre-ingest]"
            basis = bases.get(pc.ref.ref_id, "?")
            lines.append(
                f"  [{pc.source}] {pc.ref.title or pc.ref.ref_id} "
                f"(id-basis {basis}){note}"
            )
        return "\n".join(lines)


def plan_corpus(candidates: Sequence[PlannedCandidate]) -> CorpusPlan:
    """Compute the ingest plan: dedup first (cheap, identity-based), then gate
    only the survivors (so we don't pay quality assessment for duplicates).

    Dedup keys through the single ``substrate.dedup`` identity ladder, so the
    cross-source collapse decision IS the SPR-04 identity. The identity report
    and the per-candidate document_id basis are read off that same identity for
    the kept set — there is no second collapse pass and no second ladder that
    could disagree with what dedup actually did.

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

    # Identity over the kept set, read off the SAME key dedup used. Each kept
    # candidate's identity key is its document_id basis (the SPR-01 contract)
    # AND its row in the per-key-type distribution (rigor #1). Computed once.
    bases: list[tuple[str, str]] = []
    key_type_counts: dict[str, int] = {}
    low_confidence = 0
    for pc in to_ingest:
        ikey = pc.identity()
        bases.append((pc.ref.ref_id, identity_basis(pc.ref.identity_record())))
        key_type_counts[ikey.key_type.value] = (
            key_type_counts.get(ikey.key_type.value, 0) + 1
        )
        if ikey.confidence is Confidence.LOW:
            low_confidence += 1

    identity_report = IdentityReport(
        kept=len(to_ingest),
        key_type_counts=key_type_counts,
        low_confidence=low_confidence,
    )

    return CorpusPlan(
        deduped=deduped,
        to_ingest=tuple(to_ingest),
        quality_rejected=tuple(quality_rejected),
        quality_report=aggregate_verdicts(verdicts),
        identity_report=identity_report,
        document_id_bases=tuple(bases),
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
    plan: CorpusPlan, *, db_path: str | None, dry_run: bool
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

    bases = dict(plan.document_id_bases)
    ingested = failed = 0
    statuses: list[str] = []
    for pc in plan.to_ingest:
        # The identity the plan computed reaches the write boundary: the thunk
        # is handed this candidate's document_id basis (the SPR-01 contract),
        # so the dedup identity and the ingest identity are the same value.
        basis = bases[pc.ref.ref_id]
        try:
            status = pc.ingest(db_path, basis)
        except Exception as exc:  # never let one item kill the batch
            failed += 1
            logger.warning(
                "failed to ingest [%s] %s: %s", pc.source, pc.ref.ref_id, exc
            )
            continue
        ingested += 1
        statuses.append(status)
        logger.info(
            "ingested [%s] %s (id-basis %s) → %s",
            pc.source, pc.ref.ref_id, basis, status,
        )
    return ExecuteReport(
        planned=planned, ingested=ingested, failed=failed,
        dry_run=False, statuses=tuple(statuses),
    )


# ---------------------------------------------------------------------------
# Discovery adapters — the network edge. Each maps a connector's records into
# PlannedCandidates. Kept thin: the connectors own their own tests; these only
# normalize + close over the ingest call.
# ---------------------------------------------------------------------------


def _arxiv_bulk_candidates(
    *, snapshot_path: str, category: str | None, limit: int,
    investigation_id: str,
) -> list[PlannedCandidate]:
    """Discover arXiv candidates from the LOCAL bulk metadata snapshot — never
    touching the export API (the path that 429-banned the box). The per-PDF
    fetch (at ingest) reuses the shared SourceThrottle (key ``arxiv_pdf``) + the
    shared assert_pdf check. Candidate shape matches the export path so dedup /
    rights / quality are unchanged.

    Body-quality boundary (intellectual honesty): the bulk snapshot carries only
    metadata + the abstract, NOT the body. The body is the PDF fetched at
    ingest. Assessing the abstract at discovery would be assessing the wrong
    text — a ~120-word abstract clears the token/real-word floors trivially
    while a truncated/OCR-garbled PDF body could still slip in. So discovery
    gates METADATA ONLY (``assess_body=False``), and the REAL body extracted
    from the fetched PDF is gated inside the ingest thunk via
    ``substrate.quality_gate.assess_extraction_quality`` BEFORE the document is
    written — OCR garbage in the PDF body is a counted per-item rejection, not a
    silent ingest."""
    import os as _os

    from acquisition.arxiv import (
        ArxivPaper,
        bulk_candidates_from_path,
        fetch_bulk_pdf,
        ingest_paper_with_rights,
    )
    from substrate.source_throttle import SourceThrottle

    if not snapshot_path or not _os.path.exists(snapshot_path):
        raise SystemExit(
            "error: --arxiv-source bulk needs --arxiv-bulk-snapshot pointing at "
            "a downloaded arxiv-metadata-oai-snapshot.json (JSON-Lines). See the "
            "runbook; the snapshot is fetched out-of-band, never via export."
        )

    papers = bulk_candidates_from_path(
        snapshot_path, category=category, limit=limit
    )
    persistent = SourceThrottle()

    out: list[PlannedCandidate] = []
    for p in papers:
        author = p.authors[0] if p.authors else None

        def _ingest(db_path: str, _basis: str, _p: ArxivPaper = p) -> str:
            # Per-PDF fetch dodges export; throttle + PDF-vs-HTML check reused.
            # _basis is the SPR-04 content-stable document_id basis, accepted at
            # the write boundary like the other connectors' thunks; SPR-01's
            # merge consumes it, today's ingest_paper_with_rights still mints its
            # own id (the documented seam, identical to the export/PD/OA thunks).
            pdf_bytes = fetch_bulk_pdf(_p, throttle=persistent)
            _assert_pdf_body_quality(pdf_bytes, ref_id=f"arxiv:{_p.arxiv_id}")
            result = ingest_paper_with_rights(
                _p, investigation_id=investigation_id,
                pdf_bytes=pdf_bytes, db_path=db_path,
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
                # Metadata-only at discovery: the abstract is NOT the body. The
                # body is gated from the fetched PDF in _ingest (see docstring).
                assessable_text="",
                assess_body=False,
                ingest=_ingest,
            )
        )
    return out


def _arxiv_candidates(
    *, query: str | None, category: str | None,
    ids: Sequence[str] | None, limit: int, investigation_id: str,
    arxiv_source: str = "export", bulk_snapshot: str | None = None,
) -> list[PlannedCandidate]:
    if arxiv_source == "bulk":
        return _arxiv_bulk_candidates(
            snapshot_path=bulk_snapshot or "", category=category,
            limit=limit, investigation_id=investigation_id,
        )

    import httpx

    from acquisition.arxiv import (
        ArxivBanned,
        ArxivPaper,
        ArxivThrottle,
        ingest_paper_with_rights,
        search,
    )
    from acquisition.arxiv.client import fetch_by_id
    from substrate.source_throttle import SourceThrottle
    from tools.ingest_arxiv import _request_with_429_sentinel

    throttle = ArxivThrottle()
    # The export API keeps its dedicated ArxivThrottle (its #23 tests pin it).
    # But the orchestrator's source rotation reads the SHARED sentinel, so when
    # the export endpoint bans us we mirror that ban under the arxiv_export key
    # in the shared file — the NEXT run's discover_all then rotates AWAY from
    # arXiv at the top of the run instead of entering this branch to re-discover
    # a banned endpoint. This is the bridge that makes export bans participate
    # in rotation without disturbing ArxivThrottle.
    shared = SourceThrottle()

    def _mirror_export_ban() -> None:
        until = throttle.banned_until()
        if until > 0:
            shared.note_response_at(ARXIV_EXPORT_KEY, until)

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
        _mirror_export_ban()
        return []
    except httpx.HTTPStatusError as exc:
        logger.error("arxiv discovery http error, skipping arxiv: %s", exc)
        _mirror_export_ban()
        return []

    out: list[PlannedCandidate] = []
    for p in papers:
        author = p.authors[0] if p.authors else None

        def _ingest(db_path: str, _basis: str, _p: ArxivPaper = p) -> str:
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

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        return self._inner.get_json(url, params=params)  # type: ignore[attr-defined]

    def get_bytes(self, url: str) -> bytes:
        if url not in self._body_cache:
            self._body_cache[url] = self._inner.get_bytes(url)  # type: ignore[attr-defined]
        return self._body_cache[url]


def _pd_curated_book_candidates(
    *, limit: int, investigation_id: str,
) -> list[PlannedCandidate]:
    """Discover from the five Wave-2 PD book connectors (SPR-06) registered in
    ``acquisition.books.registry``. Each connector fetches through its OWN
    SPR-03 throttle (keyed by source) and establishes PD per item; the
    servable/gated/skip verdict is delegated to ``classify()`` inside
    ``classify_and_ingest`` (never a local boolean). A per-source discovery
    failure is isolated (logged, skipped) so one source down does not abort the
    curated spine — the gutendex-503 lesson generalized across sources."""
    from acquisition.books.pd_connector_base import (
        BookCandidate,
        ThrottledFetcher,
        classify_and_ingest,
    )
    from acquisition.books.registry import PD_CURATED_SOURCES
    from substrate.source_throttle import SourceBanned, SourceThrottle

    persistent = SourceThrottle()
    out: list[PlannedCandidate] = []
    for src in PD_CURATED_SOURCES:
        fetcher = ThrottledFetcher(source=src.key, persistent=persistent)
        try:
            cands = src.discover(fetcher, limit=limit)
        except SourceBanned as exc:
            logger.warning(
                "pd-curated source %s banned (sentinel active); skipping: %s",
                src.key, exc,
            )
            continue
        except Exception as exc:  # one source's discovery must not abort the spine
            logger.warning(
                "pd-curated source %s discovery failed; skipping this run: %s",
                src.key, exc,
            )
            continue

        for c in cands:
            def _ingest(
                db_path: str, _basis: str,
                _c: BookCandidate = c, _fetcher: ThrottledFetcher = fetcher,
            ) -> str:
                outcome = classify_and_ingest(
                    _c, _fetcher, investigation_id=investigation_id,
                    db_path=db_path,
                )
                if outcome.ingested:
                    return f"{outcome.content_class} ({outcome.servability})"
                return f"skipped: {outcome.skipped_reason}"

            out.append(
                PlannedCandidate(
                    ref=CandidateRef(
                        ref_id=c.source_id,
                        # ISBN-13 (Hathi) keys above source-id when present.
                        isbn=c.isbn,
                        source_id=c.source_id,
                        title=c.title,
                        author=c.author,
                    ),
                    source="public_domain",
                    # Body is fetched/extracted at ingest; gate metadata-only at
                    # discovery (the PDF/epub body is quality-gated by the
                    # reader's word floor inside the ingest path).
                    assessable_text="",
                    assess_body=False,
                    ingest=_ingest,
                    allow_null_author_reason=(
                        f"{c.source} record exposes no author at discovery"
                        if not (c.author and c.author.strip())
                        else None
                    ),
                )
            )
    return out


def _public_domain_candidates(
    *, subject: str | None, search_term: str | None,
    ids: Sequence[int] | None, curated: bool, limit: int,
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
    from substrate.source_throttle import SourceBanned, SourceThrottle
    from tools.ingest_public_domain import CURATED_GUTENBERG_IDS

    # SHARED persistent ban sentinel for gutendex (the 2026-05-29 503 source).
    # A 429/503 now survives a process restart; an already-banned gutendex
    # raises SourceBanned and PD self-skips instead of re-hitting the source.
    persistent = SourceThrottle()
    client = _BodyCachingClient(
        SourceClient(min_interval_s=min_interval_s, persistent=persistent)
    )
    selected_ids: Sequence[int] | None = ids
    if curated:
        selected_ids = list(CURATED_GUTENBERG_IDS)
        limit = max(limit, len(selected_ids))
    try:
        works = gutenberg_candidates(
            client, subject=subject, search=search_term, ids=selected_ids, limit=limit
        )
    except SourceBanned as exc:
        logger.warning(
            "public-domain source banned (sentinel active); skipping PD: %s", exc
        )
        return []
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

        def _ingest(db_path: str, _basis: str, _w: PublicDomainWork = w) -> str:
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
                    # source_id is namespaced by source so a Gutenberg id and an
                    # archive.org id can never collide at the source-id level.
                    source_id=f"{w.source}:{w.source_id}",
                    title=w.title,
                    author=w.author,
                    # The downloaded body (when a text format was served) lets a
                    # body-bearing work key on its content-hash above the LOW
                    # title fallback; empty when only a PDF is offered.
                    body=body or None,
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

    # SPR-06: the curated PD spine also rotates the five new PD book connectors
    # (Standard Ebooks / Wikisource / Internet Archive / HathiTrust / LoC).
    # Their fetch + rights verdict + dedup all compose the same Wave-1 spine;
    # the cross-source dedup below collapses a work shared with Gutenberg.
    if curated:
        out += _pd_curated_book_candidates(
            limit=limit, investigation_id=investigation_id,
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


# The SPR-07 paper-aggregator oa-sources. These route through the papers
# package (acquisition.papers.*), NOT the openaccess connectors — they are NEW
# paper sources (CORE / S2 / bioRxiv-medRxiv / PLOS), disjoint from what
# acquisition/openaccess/ already covers (OpenAlex / Unpaywall / PMC / DOAJ).
PAPER_AGGREGATOR_OA_SOURCES = ("core", "semantic_scholar", "biorxiv", "medrxiv", "plos")


def _paper_aggregator_candidates(
    *, source: str, query: str | None, limit: int, investigation_id: str,
    biorxiv_server: str = "biorxiv", biorxiv_interval: str | None = None,
) -> list[PlannedCandidate]:
    """Discover + plan candidates from a SPR-07 paper aggregator (CORE / S2 /
    bioRxiv-medRxiv / PLOS).

    Every record's content_class is resolved ONLY by the chokepoint via
    ``acquisition.papers.classify_paper`` — no source assigns a class by any
    other route. A servable record fetches+stages its body through the shared
    ``ingest_servable_paper`` (which composes ``ingest_servable_book`` ->
    ``connect_write``); a gated record (closed S2, no-reuse biorxiv, unknown
    CORE) is staged metadata+abstract only, body NEVER fetched. The
    cross-process SourceThrottle carries each aggregator's ban sentinel so a
    banned source self-skips. The body-quality (PDF-vs-HTML) reality check runs
    via the shared ``assert_pdf`` inside the per-source fetch.
    """
    from acquisition.openaccess.pdf_detect import NotAPdf
    from acquisition.papers import (
        classify_paper,
        ingest_servable_paper,
        paper_candidate_ref,
    )
    from substrate.source_throttle import SourceBanned, SourceThrottle

    persistent = SourceThrottle()

    # Discover the source's raw records behind its throttle. A ban self-skips.
    try:
        records = _discover_paper_records(
            source=source, query=query, limit=limit, throttle=persistent,
            biorxiv_server=biorxiv_server, biorxiv_interval=biorxiv_interval,
        )
    except SourceBanned as exc:
        logger.error("paper aggregator %s banned, skipping: %s", source, exc)
        return []
    except Exception as exc:  # network / parse failure isolated per-source
        logger.warning("paper aggregator %s discovery failed, skipping: %s", source, exc)
        return []

    out: list[PlannedCandidate] = []
    for rec in records:
        classification = classify_paper(rec)
        # Gated records (incl. servable-licensed-but-no-body) never fetch a body.
        serve = classification.serve_body

        def _ingest(
            db_path: str, _basis: str,
            _rec=rec, _cls=classification, _serve=serve,
        ) -> str:
            if not _serve:
                # Gated / no-body: stage metadata + abstract only; body NEVER
                # fetched-and-served. The abstract is landed as the source so
                # the work is privately searchable, gated. Reuse the arXiv
                # abstract-only adapter shape via a lightweight metadata stage.
                return _stage_paper_metadata_only(
                    _rec, _cls, investigation_id=investigation_id, db_path=db_path
                )
            # Servable: fetch the body behind the throttle + the PDF reality
            # check, then stage the full text through the shared servable path.
            try:
                pdf_bytes = _fetch_paper_pdf(
                    _rec, throttle=persistent, source=source
                )
            except NotAPdf as exc:
                # OA-claimed but the "PDF" was an HTML landing page (the 6/15
                # prod failure mode): a counted per-item miss, not a servable
                # ingest. Surfaced for the rigor-#1 OA-claim-failure report.
                raise ValueError(f"OA-claimed PDF was not a PDF: {exc}") from exc
            result = ingest_servable_paper(
                _rec, _cls, investigation_id=investigation_id,
                pdf_bytes=pdf_bytes, db_path=db_path,
            )
            return f"{result.content_class} (servable={result.servable_full_text})"

        # The body is fetched at ingest, so the quality gate runs metadata-only
        # at discovery (assess_body=False) — assessing an abstract would
        # spuriously reject a clean paper. The real PDF body's reality check is
        # the shared assert_pdf in _fetch_paper_pdf.
        out.append(
            PlannedCandidate(
                ref=paper_candidate_ref(rec),
                source="open_access",
                assessable_text="",
                assess_body=False,
                ingest=_ingest,
                allow_null_author_reason=(
                    None if rec.primary_author
                    else f"{source} record exposes no author at discovery"
                ),
            )
        )
    return out


def _discover_paper_records(
    *, source: str, query: str | None, limit: int, throttle,
    biorxiv_server: str, biorxiv_interval: str | None,
):
    """Dispatch to the right SPR-07 paper aggregator's discovery, returning raw
    PaperRecords. Each connector reads its per-record declared license."""
    if source == "core":
        from acquisition.papers.core import search_works
        return search_works(query=query or "", limit=limit, throttle=throttle)
    if source == "semantic_scholar":
        from acquisition.papers.semantic_scholar import search_papers
        return search_papers(query=query or "", limit=limit, throttle=throttle)
    if source in ("biorxiv", "medrxiv"):
        from acquisition.papers.biorxiv import fetch_details
        kwargs = {"server": biorxiv_server or source, "limit": limit, "throttle": throttle}
        if biorxiv_interval:
            kwargs["interval"] = biorxiv_interval
        return fetch_details(**kwargs)
    if source == "plos":
        from acquisition.papers.plos import search_articles
        return search_articles(query=query or "", limit=limit, throttle=throttle)
    raise SystemExit(f"error: unknown paper aggregator oa-source {source!r}")


def _fetch_paper_pdf(rec, *, throttle, source: str) -> bytes:
    """Fetch a servable paper's PDF behind the shared throttle + the shared
    PDF-vs-HTML reality check. Quality/reality only — content_class is already
    decided by the chokepoint."""
    import httpx

    from acquisition.openaccess.pdf_detect import assert_pdf

    throttle_key = {"core": "core", "semantic_scholar": "semantic_scholar",
                    "plos": "plos"}.get(source, f"biorxiv_{source}")
    throttle.before_request(throttle_key)
    url = rec.pdf_url
    with httpx.Client(
        follow_redirects=True,
        timeout=30.0,  # match the existing PDF fetch request timeout below
    ) as c:
        r = c.get(url, headers={"User-Agent": "Antiek/0.1 (acquisition.papers)"}, timeout=30.0)
    if r.status_code in (429, 503):
        throttle.note_response(throttle_key, r.status_code, dict(r.headers))
    r.raise_for_status()
    content = r.content
    assert_pdf(content, content_type=r.headers.get("content-type"), url=url)
    return content


def _stage_paper_metadata_only(
    rec, classification, *, investigation_id: str, db_path: str
) -> str:
    """Stage a GATED paper's metadata + abstract — body NEVER fetched/served.

    The abstract is landed as a markdown document through the shared
    servable-book classification path with the resolved GATED content_class +
    the source-specific license_basis, so the row is an auditable gated decision
    (not a silent omission) and the work is privately searchable. The body is
    not fetched; servable_full_text is derived False from the gated class.
    """
    from acquisition.books.adapter import ingest_servable_book
    from acquisition.books.public_domain import text_to_pdf

    title = rec.title or rec.source_id
    abstract = rec.abstract or ""
    body = f"{title}\n\nAbstract:\n{abstract}\n\n(Metadata-only gated record; full text withheld.)"
    # text_to_pdf yields a tiny PDF the shared reader/chunker accepts; the
    # GATED content_class makes servable_full_text False — body never served.
    pdf_bytes = text_to_pdf(body, title=title)
    # A gated record's body is deliberately just its (often short) abstract, so
    # the full-book "scanned/empty" word-count floor (100) must NOT apply here —
    # otherwise a paper with a sub-100-word abstract would be skip-dropped and
    # never staged gated, defeating the private-search guarantee. Floor of 1
    # keeps a genuinely empty body (no title, no abstract) skipped while always
    # staging a record that carries any text.
    result = ingest_servable_book(
        pdf_bytes,
        investigation_id=investigation_id,
        content_class=classification.content_class,
        license_basis=classification.license_basis,
        source_uri=(f"https://doi.org/{rec.doi}" if rec.doi else None),
        provenance=rec.source,
        db_path=db_path,
        min_word_count=1,
    )
    return f"{classification.content_class} (servable={result.servable_full_text}, metadata-only)"


def _opt_in_candidates(
    *, manifest_path: str | None, limit: int, investigation_id: str,
) -> list[PlannedCandidate]:
    """Discover §9.10 publisher-opt-in candidates from a catalog manifest FILE.

    This lane reaches NO network: a publisher hands the operator a catalog
    manifest (their works + stable ids + an explicit serving grant), and this
    adapter reads it locally. The rights decision for every work is made by the
    ONE chokepoint (``acquisition.licenses_core.classify`` via
    ``acquisition.opt_in.ingest_entry``) — a valid grant -> servable
    (opt_in_licensed), an absent/invalid grant -> gated (deny-by-default). The
    publisher's ip_holder is resolved ONCE (pre_onboarded if needed) and every
    work links to it.

    Each manifest entry becomes one PlannedCandidate so the orchestrator's
    cross-source dedup + corpus-quality gate apply uniformly; the ingest thunk
    runs ``ingest_entry`` (which writes through the connectors'
    ``connect_write`` / staging path, never the live DB directly)."""
    from acquisition.opt_in import ingest_entry, load_manifest, resolve_publisher_holder

    if not manifest_path:
        raise SystemExit(
            "error: --oa-source opt_in needs --oa-query pointing at a publisher "
            "catalog manifest JSON (see acquisition/opt_in/MANIFEST.md)."
        )
    manifest = load_manifest(manifest_path)
    publisher = manifest.publisher

    out: list[PlannedCandidate] = []
    for entry in manifest.entries[:limit] if limit else manifest.entries:
        body = entry.body_text
        if body is None and entry.body_path:
            try:
                with open(entry.body_path, encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                body = None

        def _ingest(
            db_path: str, _basis: str, _entry=entry, _publisher=publisher,
            _catalog_grant=manifest.catalog_grant,
        ) -> str:
            # Holder resolution is idempotent (resolve-or-create keyed on the
            # stable publisher_id), so resolving per-thunk reuses the one holder
            # the whole manifest shares — no duplicate accounts.
            holder_id, _ = resolve_publisher_holder(_publisher, db_path=db_path)
            outcome = ingest_entry(
                _entry, _publisher,
                ip_holder_id=holder_id, db_path=db_path,
                catalog_grant=_catalog_grant,
                investigation_id=investigation_id,
            )
            if outcome.skipped_reason:
                return f"skipped: {outcome.skipped_reason}"
            servability = "servable" if outcome.servable else "gated"
            return f"{outcome.content_class} ({servability})"

        out.append(
            PlannedCandidate(
                ref=CandidateRef(
                    ref_id=f"opt_in:{entry.doi or entry.isbn or entry.title}",
                    doi=entry.doi,
                    isbn=entry.isbn,
                    title=entry.title,
                    author=entry.author,
                    # The body lets a metadata-poor work key on its content-hash
                    # above the LOW title fallback (same as the PD path).
                    body=body or None,
                ),
                source="open_access",
                # The body IS the text we'd ingest → assess it when present.
                assessable_text=body or "",
                assess_body=bool(body),
                ingest=_ingest,
                allow_null_author_reason=(
                    "opt-in catalog work with no recorded author"
                    if not (entry.author and entry.author.strip())
                    else None
                ),
            )
        )
    return out


def _open_access_candidates(
    *, source: str, query: str | None, author: str | None,
    dois: Sequence[str] | None, limit: int, investigation_id: str,
) -> list[PlannedCandidate]:
    from acquisition.openaccess import OAThrottle
    from acquisition.openaccess.ingest import build_license_basis, ingest_oa_item
    from substrate.source_throttle import SourceBanned, SourceThrottle
    from tools.ingest_open_access import Candidate, _resolve_candidates, _source_fetcher

    # Front the OA throttle with the SHARED persistent ban sentinel keyed per
    # aggregator (oa_unpaywall / oa_pmc / ...). A 429/503 now survives a process
    # restart, and an already-banned aggregator raises SourceBanned here so this
    # source self-skips (returns []) instead of aborting the whole run — the
    # same per-source isolation #23 gave PD/arXiv, now backed by a sentinel.
    persistent = SourceThrottle()
    oa_source_key = f"oa_{source}"
    throttle = OAThrottle(persistent=persistent, source=oa_source_key)
    try:
        cands: list[Candidate] = _resolve_candidates(
            source=source, query=query, author=author,
            dois=dois, limit=limit, throttle=throttle,
        )
    except SourceBanned as exc:
        logger.error("open-access source banned, skipping OA discovery: %s", exc)
        return []
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
            db_path: str, _doc_basis: str,
            _c: Candidate = c, _license_basis: str = basis, _urls=_urls
        ) -> str:
            if not _urls or fetch_pdf is None:
                return "skipped: no fetchable PDF"
            from acquisition.openaccess.unpaywall import NotAPdf

            last_exc: Exception | None = None
            for u in _urls:
                try:
                    result = ingest_oa_item(
                        investigation_id=investigation_id,
                        doi=_c.doi, pdf_url=u, resolution=_c.resolution,
                        license_basis=_license_basis, fetch_pdf=fetch_pdf,
                        db_path=db_path,
                    )
                    return f"{result.content_class} ({result.servability})"
                except NotAPdf as exc:
                    # Landing page / corrupt PDF — try the next candidate URL.
                    last_exc = exc
                    continue
                except SourceBanned as exc:
                    # The aggregator got banned mid-ingest: stop trying its URLs
                    # (re-hitting extends the ban) and surface a counted miss.
                    raise ValueError(f"source banned during ingest: {exc}") from exc
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
# Open-textbook discovery (SPR-05). One adapter for the four connectors —
# OpenStax / LibreTexts / DOAB / MIT OCW. Each connector reads its source's own
# license field; the rights decision is classify() (SPR-02) INSIDE
# ingest_textbook, never here. This adapter only normalizes discovery records
# into PlannedCandidates and closes over ingest_textbook for the write.
# ---------------------------------------------------------------------------


# The textbook source key -> (connector module name, discover-kwargs builder).
# ``--source textbooks`` expands to all four (the family sub-selector).
TEXTBOOK_SOURCES = ("openstax", "libretexts", "doab", "mit_ocw")


def _textbook_candidates(
    *, source: str, limit: int, investigation_id: str,
    libretexts_library: str | None = None,
    doab_query: str | None = None,
    ocw_query: str | None = None,
) -> list[PlannedCandidate]:
    """Discover one open-textbook source's candidates as PlannedCandidates.

    The connector reads each item's DECLARED license; ``ingest_textbook``
    routes it through ``classify()`` (SPR-02) and lands it via
    ``ingest_servable_book`` (SPR-01 staging target). Discovery is throttled +
    ban-aware through the shared ``SourceThrottle`` (SPR-03), keyed per source.
    Body is the textbook PDF fetched at ingest, with the SPR-03 PDF-vs-HTML
    extraction gate inside ``ingest_textbook`` — so the gate sees no body at
    discovery and runs metadata-only (``assess_body=False``), exactly like the
    OA path.
    """
    from acquisition.textbooks import (
        SourceError as TextbookSourceError,
    )
    from acquisition.textbooks import (
        ThrottledClient,
        ingest_textbook,
    )
    from substrate.source_throttle import SourceBanned, SourceThrottle

    if source == "openstax":
        from acquisition.textbooks import openstax as connector
        discover_kwargs: dict = {}
    elif source == "libretexts":
        from acquisition.textbooks import libretexts as connector
        discover_kwargs = {"library": libretexts_library}
    elif source == "doab":
        from acquisition.textbooks import doab as connector
        discover_kwargs = {"query": doab_query}
    elif source == "mit_ocw":
        from acquisition.textbooks import mit_ocw as connector
        discover_kwargs = {"query": ocw_query}
    else:  # pragma: no cover - guarded by argparse choices
        raise SystemExit(f"error: unknown textbook source {source!r}")

    persistent = SourceThrottle()
    client = ThrottledClient(persistent=persistent, source=source)
    try:
        works = connector.discover(client, limit=limit, **discover_kwargs)
    except SourceBanned as exc:
        logger.warning("textbook source %s banned; skipping: %s", source, exc)
        return []
    except TextbookSourceError as exc:
        # A transient discovery failure must not abort the multi-source run
        # (identical isolation to the PD/OA discovery paths).
        logger.warning(
            "textbook source %s discovery failed (transient); skipping: %s",
            source, exc,
        )
        return []

    out: list[PlannedCandidate] = []
    for w in works:
        def _ingest(db_path: str, _basis: str, _w=w) -> str:
            outcome = ingest_textbook(
                _w, client, investigation_id=investigation_id, db_path=db_path
            )
            if outcome.ingested:
                return (
                    f"{outcome.content_class} ({outcome.servability}) "
                    f"[{outcome.word_count} words]"
                )
            return f"skipped: {outcome.skipped_reason}"

        out.append(
            PlannedCandidate(
                ref=CandidateRef(
                    ref_id=f"{w.source}:{w.source_id}",
                    # Namespace the source-local id by source so a slug from one
                    # textbook source can't collide with another at the
                    # source-id dedup level.
                    source_id=f"{w.source}:{w.source_id}",
                    isbn=w.isbn,
                    title=w.title,
                    author=w.author,
                ),
                source=w.source,
                # The body is the textbook PDF fetched at ingest, gated there by
                # the SPR-03 extraction-quality check — so discovery has no body
                # to assess and runs metadata-only (like the OA path).
                assessable_text="",
                assess_body=False,
                ingest=_ingest,
                allow_null_author_reason=(
                    "open textbook with no recorded author"
                    if not (w.author and w.author.strip())
                    else None
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Body-quality gate at ingest (M6 wired into the corpus path).
# ---------------------------------------------------------------------------


class BodyQualityRejected(ValueError):
    """The PDF body failed the extraction-quality gate (OCR garbage /
    near-empty). A ValueError subclass so ``execute_plan``'s per-item
    try/except counts it as a per-item failure (the run continues), and the
    reason is carried for the run summary — the body never enters the corpus."""


def _assert_pdf_body_quality(pdf_bytes: bytes, *, ref_id: str) -> None:
    """Gate the REAL extracted PDF body before ingest. This is where M6's
    ``assess_extraction_quality`` becomes load-bearing on the corpus path: the
    bulk arXiv body arrives as a PDF (not text), so corpus_quality's
    discovery-time checks never see it — they ran metadata-only. We extract the
    body with the same ``read_pdf`` the ingest uses and reject OCR garbage /
    near-empty extracts as a counted miss, BEFORE ``ingest_paper_with_rights``
    writes anything. Quality-only: this never touches content_class /
    servability."""
    from acquisition.books.reader import read_pdf
    from substrate.quality_gate import CheckResultKind, assess_extraction_quality

    body = read_pdf(pdf_bytes).markdown
    verdict = assess_extraction_quality(body)
    if verdict.kind is CheckResultKind.FAIL:
        raise BodyQualityRejected(
            f"{ref_id}: extracted PDF body failed quality gate "
            f"({'; '.join(verdict.reasons)})"
        )


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
        choices=(
            "public_domain", "arxiv", "open_access",
            # SPR-05 open-textbook family: four named source values matching
            # the existing flag style. ``--source textbooks`` is the family
            # sub-selector that expands to all four.
            "textbooks", "openstax", "libretexts", "doab", "mit_ocw",
        ),
        help=(
            "source to include (repeatable); default: all selected sources. "
            "'textbooks' selects all four open-textbook connectors "
            "(openstax, libretexts, doab, mit_ocw)"
        ),
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
    p.add_argument(
        "--arxiv-source", choices=("export", "bulk"), default="export",
        help=(
            "arXiv transport: 'export' (the Atom API, for small incremental "
            "pulls) or 'bulk' (the local metadata snapshot, dodging the "
            "export-API 429 for mass volume)"
        ),
    )
    p.add_argument(
        "--arxiv-bulk-snapshot",
        help=(
            "arXiv: path to the local arxiv-metadata-oai-snapshot.json "
            "(JSON-Lines); required when --arxiv-source bulk"
        ),
    )
    # open-access selectors. The first four are the Wave-1 openaccess
    # connectors; the next five (core / semantic_scholar / biorxiv / medrxiv /
    # plos) are the SPR-07 paper aggregators routed through acquisition.papers;
    # 'opt_in' is the SPR-08 §9.10 publisher opt-in lane.
    p.add_argument(
        "--oa-source",
        choices=(
            "openalex", "unpaywall", "pmc", "doaj",
            "core", "semantic_scholar", "biorxiv", "medrxiv", "plos",
            "opt_in",
        ),
        help=(
            "open-access aggregator (incl. SPR-07 paper aggregators core / "
            "semantic_scholar / biorxiv / medrxiv / plos), OR 'opt_in' for the "
            "§9.10 publisher opt-in lane (a publisher's own catalog manifest "
            "submitted with an explicit serving grant). For opt_in, --oa-query "
            "is the path to the catalog manifest JSON."
        ),
    )
    p.add_argument(
        "--oa-query",
        help=(
            "open-access: search query (openalex / core / s2 / plos); for "
            "--oa-source opt_in, the path to the publisher catalog manifest JSON"
        ),
    )
    p.add_argument("--oa-author", help="open-access: openalex author")
    p.add_argument("--oa-dois", help="open-access: comma-separated DOIs")
    # open-textbook selectors (SPR-05)
    p.add_argument(
        "--libretexts-library",
        help="textbooks: LibreTexts library to discover from (e.g. 'chem')",
    )
    p.add_argument("--doab-query", help="textbooks: DOAB/OAPEN search query")
    p.add_argument("--ocw-query", help="textbooks: MIT OCW search query")
    # bioRxiv / medRxiv selectors (SPR-07)
    p.add_argument(
        "--biorxiv-server", choices=("biorxiv", "medrxiv", "both"),
        default="biorxiv",
        help="bioRxiv/medRxiv: which preprint server (default biorxiv)",
    )
    p.add_argument(
        "--biorxiv-interval",
        help="bioRxiv/medRxiv: date range, e.g. 2024-01-01/2024-12-31",
    )
    # shared
    p.add_argument("--limit", type=int, default=25, help="per-source max")
    p.add_argument("--investigation-id", default="inv-corpus", help="investigation id stamped on docs")
    p.add_argument("--db-path", help="target DuckDB (required for a real run)")
    p.add_argument(
        "--staging-db",
        help=(
            "write the ingest to a separate staging DuckDB instead of the live "
            "DB (SPR-01 keystone). The live API keeps serving the live DB during "
            "the ingest; merge the staged rows in with tools/merge_staging.py. "
            "When set, --db-path / --allow-prod-write are not needed."
        ),
    )
    p.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    p.add_argument(
        "--allow-prod-write", action="store_true",
        help="permit writing to the prod substrate default (operator-only; see runbook)",
    )
    p.add_argument(
        "--pd-min-interval", type=float, default=1.0,
        help="public-domain: min seconds between source requests",
    )
    # ---- SPR-09 continuous orchestration -----------------------------------
    p.add_argument(
        "--continuous", action="store_true",
        help=(
            "run the standing, resumable, box-bounded engine: cycle every "
            "selected source, stage off the hot path, merge on a cadence, "
            "checkpoint per source, and pace/halt against the box ceiling. "
            "ONE process, ONE in-process loop — not a daemon, not a fan-out. "
            "Requires --staging-db (or --dry-run)."
        ),
    )
    p.add_argument(
        "--status", action="store_true",
        help=(
            "print a READ-ONLY run-health snapshot reconstructed from the event "
            "log + checkpoint store (per-source counts, reject rate, last-merge, "
            "governor state, banned-until). Never takes the write lock."
        ),
    )
    p.add_argument(
        "--max-rounds", type=int, default=None, dest="max_rounds",
        help="continuous: stop after this many rounds (default: until HALT)",
    )
    p.add_argument(
        "--round-sleep-s", type=float, default=0.0, dest="round_sleep_s",
        help="continuous: seconds to sleep between rounds (default: 0)",
    )
    # Merge-cadence thresholds (M4). Each merge holds the live writer briefly;
    # the merge fires when ANY of these trips (count OR staging-size OR interval).
    p.add_argument(
        "--merge-count", type=int, default=DEFAULT_MERGE_COUNT, dest="merge_count",
        help=(
            f"continuous: merge after this many staged docs "
            f"(default {DEFAULT_MERGE_COUNT})"
        ),
    )
    p.add_argument(
        "--merge-size-bytes", type=int, default=DEFAULT_MERGE_SIZE_BYTES,
        dest="merge_size_bytes",
        help=(
            f"continuous: merge when the staging DB reaches this size in bytes "
            f"(default {DEFAULT_MERGE_SIZE_BYTES})"
        ),
    )
    p.add_argument(
        "--merge-interval-s", type=float, default=DEFAULT_MERGE_INTERVAL_S,
        dest="merge_interval_s",
        help=(
            f"continuous: merge at least this often in seconds "
            f"(default {DEFAULT_MERGE_INTERVAL_S})"
        ),
    )
    p.add_argument(
        "--events-dir", dest="events_dir",
        help="continuous/status: override the event-log directory (tests)",
    )
    return p


def _csv_ints(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(x) for x in value.split(",") if x.strip()]


def _csv_strs(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [x.strip() for x in value.split(",") if x.strip()]


def _arxiv_throttle_key(arxiv_source: str) -> str:
    """The persistent-throttle key whose ban means 'arXiv is unreachable now'.
    The bulk path's reachability is its PDF host (``arxiv_pdf``); the export
    path's is the dedicated ``ArxivThrottle``, which records its ban under the
    ``arxiv_export`` key in the SAME shared sentinel file."""
    return ARXIV_PDF_KEY if arxiv_source == "bulk" else ARXIV_EXPORT_KEY


# The shared-sentinel keys each selected source's reachability hangs on. These
# are the keys the live fetch paths arm via note_response on a 429/503, so a ban
# recorded by one run's fetch is exactly what the NEXT run's rotation reads.
ARXIV_PDF_KEY = "arxiv_pdf"
ARXIV_EXPORT_KEY = "arxiv_export"
GUTENDEX_KEY = "gutendex"
# The §9.10 opt-in lane reads a local manifest (no network), so its rotation
# key is never armed by a 429/503 — it is always available.
OPT_IN_KEY = "opt_in"


@dataclass(frozen=True)
class DiscoveryOutcome:
    """What ``discover_all`` produced. ``candidates`` is the concatenation of
    every NON-banned source's discovery. ``all_banned`` + ``soonest_resume``
    are set only when every selected source's sentinel was active — the clean
    halt the orchestrator surfaces so a resume is informed (M3 criterion 3).
    ``rotation_log`` is the ordered, human-readable record of which sources were
    skipped (banned) and which were attempted (M3 criterion 4)."""

    candidates: tuple[PlannedCandidate, ...]
    rotation_log: tuple[str, ...]
    all_banned: bool = False
    soonest_resume: float = 0.0


def discover_all(args: argparse.Namespace) -> DiscoveryOutcome:
    """Drive discovery THROUGH ban-aware source rotation. A source is selected
    when explicitly named in --source, or (when --source is omitted) when any of
    its selectors is present. The orchestrator then consults the shared
    persistent sentinel and ROTATES over the selected sources in priority order:
    a source whose ban sentinel is active is skipped (recorded in the rotation
    log) instead of being fetched and re-extending its ban; the run pulls the
    remaining non-banned sources. When EVERY selected source is banned, discovery
    returns a clean all-banned halt carrying the soonest resume time, rather than
    spinning. This is the live use of ``next_available_source`` —
    ``discover_all`` is the production caller, not a test.
    """
    from substrate.source_throttle import SourceThrottle, next_available_source

    sources = set(args.sources or [])

    want_pd = "public_domain" in sources or (
        not sources and (args.pd_subject or args.pd_search or args.pd_ids or args.pd_curated)
    )
    want_arxiv = "arxiv" in sources or (
        not sources and (
            args.arxiv_query or args.arxiv_category or args.arxiv_ids
            or args.arxiv_bulk_snapshot
        )
    )
    want_oa = "open_access" in sources or (
        not sources and args.oa_source
    )
    if want_oa and not args.oa_source:
        raise SystemExit("error: open-access needs --oa-source")

    # SPR-05 open-textbook family. ``--source textbooks`` expands to all four;
    # each connector is also individually selectable by its source name. When
    # --source is omitted entirely, a textbook source is selected if any of its
    # selectors is present (libretexts-library / doab-query / ocw-query); OpenStax
    # has no required selector, so it joins only when explicitly named.
    want_textbooks = "textbooks" in sources
    selected_textbooks: list[str] = []
    for ts in TEXTBOOK_SOURCES:
        if want_textbooks or ts in sources:
            selected_textbooks.append(ts)
    if not sources:
        if args.libretexts_library and "libretexts" not in selected_textbooks:
            selected_textbooks.append("libretexts")
        if args.doab_query and "doab" not in selected_textbooks:
            selected_textbooks.append("doab")
        if args.ocw_query and "mit_ocw" not in selected_textbooks:
            selected_textbooks.append("mit_ocw")

    # Map each selected source to (rotation key, discovery thunk), in priority
    # order. The rotation key is the sentinel key whose ban means the source is
    # unreachable right now; the thunk runs that source's discovery adapter.
    runners: list[tuple[str, Callable[[], list[PlannedCandidate]]]] = []
    if want_pd:
        runners.append((
            GUTENDEX_KEY,
            lambda: _public_domain_candidates(
                subject=args.pd_subject, search_term=args.pd_search,
                ids=_csv_ints(args.pd_ids), curated=args.pd_curated,
                limit=args.limit, investigation_id=args.investigation_id,
                min_interval_s=args.pd_min_interval,
            ),
        ))
    if want_arxiv:
        runners.append((
            _arxiv_throttle_key(args.arxiv_source),
            lambda: _arxiv_candidates(
                query=args.arxiv_query, category=args.arxiv_category,
                ids=_csv_strs(args.arxiv_ids), limit=args.limit,
                investigation_id=args.investigation_id,
                arxiv_source=args.arxiv_source,
                bulk_snapshot=args.arxiv_bulk_snapshot,
            ),
        ))
    if want_oa and args.oa_source == "opt_in":
        # The §9.10 publisher-opt-in lane (SPR-08) reads a LOCAL catalog
        # manifest and reaches no network, so it has no ban sentinel — it is
        # keyed on its own always-available rotation key. --oa-query carries
        # the manifest path.
        runners.append((
            OPT_IN_KEY,
            lambda: _opt_in_candidates(
                manifest_path=args.oa_query, limit=args.limit,
                investigation_id=args.investigation_id,
            ),
        ))
    elif want_oa and args.oa_source in PAPER_AGGREGATOR_OA_SOURCES:
        # SPR-07 paper aggregator (CORE / S2 / bioRxiv-medRxiv / PLOS) —
        # routed through acquisition.papers, not the openaccess connectors.
        # Rotation key is the source's own throttle key so its ban sentinel
        # participates in rotation like every other source.
        paper_key = (
            f"biorxiv_{args.biorxiv_server}"
            if args.oa_source in ("biorxiv", "medrxiv")
            else args.oa_source
        )
        runners.append((
            paper_key,
            lambda: _paper_aggregator_candidates(
                source=args.oa_source, query=args.oa_query,
                limit=args.limit, investigation_id=args.investigation_id,
                biorxiv_server=args.biorxiv_server,
                biorxiv_interval=args.biorxiv_interval,
            ),
        ))
    elif want_oa:
        runners.append((
            f"oa_{args.oa_source}",
            lambda: _open_access_candidates(
                source=args.oa_source, query=args.oa_query, author=args.oa_author,
                dois=_csv_strs(args.oa_dois), limit=args.limit,
                investigation_id=args.investigation_id,
            ),
        ))
    for ts in selected_textbooks:
        # The rotation key is the source name — the SAME key the textbook
        # ThrottledClient arms on a 429/503, so a ban recorded by one run's
        # fetch is what the next run's rotation reads. ``ts=ts`` binds the loop
        # variable into each lambda (else all four would capture the last ts).
        runners.append((
            ts,
            lambda ts=ts: _textbook_candidates(
                source=ts, limit=args.limit,
                investigation_id=args.investigation_id,
                libretexts_library=args.libretexts_library,
                doab_query=args.doab_query, ocw_query=args.ocw_query,
            ),
        ))

    throttle = SourceThrottle()
    keys = [k for k, _ in runners]
    by_key = dict(runners)
    candidates: list[PlannedCandidate] = []
    rotation_log: list[str] = []

    # Rotate left-to-right: each pass picks the next non-banned source, runs it,
    # then re-evaluates the REMAINING sources (a source can get banned mid-run by
    # its own fetch, so the next pass re-reads the sentinel). Sources skipped as
    # banned in a pass are dropped from the remaining set too — they've been
    # logged and must not be re-picked or trigger a spurious all-banned once a
    # real source was pulled. The skipped/next decision is logged so rotation is
    # observable — not silent dead code. The all-banned halt fires only when the
    # remaining set is exhausted with NO source ever pulled.
    remaining = list(keys)
    pulled_any = False
    while remaining:
        decision = next_available_source(throttle, remaining)
        if decision.skipped:
            line = decision.render()
            rotation_log.append(line)
            logger.info("rotation: %s", line)
        if decision.all_banned:
            if pulled_any:
                # Some sources ran; the rest are banned — that is a partial run,
                # not an all-banned halt. The skip is logged above; stop here.
                break
            return DiscoveryOutcome(
                candidates=tuple(candidates),
                rotation_log=tuple(rotation_log),
                all_banned=True,
                soonest_resume=decision.soonest_banned_until,
            )
        chosen = decision.next_source
        assert chosen is not None  # not all_banned => a source was chosen
        candidates += by_key[chosen]()
        pulled_any = True
        # Drop the chosen source AND the banned ones we just skipped past it.
        skipped_keys = {s for s, _ in decision.skipped}
        remaining = [k for k in remaining if k != chosen and k not in skipped_keys]

    return DiscoveryOutcome(
        candidates=tuple(candidates),
        rotation_log=tuple(rotation_log),
    )


# ===========================================================================
# SPR-09 — Continuous orchestration (box-bounded, resumable).
#
# A SINGLE resumable in-process loop, NOT a daemon and NOT a fan-out. It reuses
# the EXACT discovery + plan + execute spine above (discover_all / plan_corpus /
# execute_plan) and the EXACT staging->merge function (tools.merge_staging) and
# the EXACT throttle/banned_until rotation (substrate.source_throttle). It adds
# only the standing-engine concerns the one-shot path lacks: a budget governor
# that PACEs/HALTs against the box ceiling, per-source checkpoints so a kill +
# restart resumes without re-ingesting, a merge CADENCE (count/size/interval)
# so the live API sees brief windows, and per-source observability to the event
# log + a read-only --status snapshot. The orchestrator only SCHEDULES; it never
# reclassifies (classify() stays the sole rights authority) and never reimple-
# ments merge/throttle/dedup.
# ===========================================================================

import json as _json  # noqa: E402
import time as _time  # noqa: E402
from datetime import UTC  # noqa: E402

# The investigation_id every continuous-engine event is filed under. A standing
# corpus ingest is a system sweep, not a single user investigation, so it uses
# the SYSTEM sentinel so `investigation_id = 'system'` lifts the whole run from
# the event log (the same convention the substrate's bulk sweeps use).
from substrate.constants import SYSTEM_INVESTIGATION_ID  # noqa: E402
from substrate.event_log.events import log_event, trajectory  # noqa: E402
from substrate.ingest_budget import (  # noqa: E402
    BudgetGovernor,
    BudgetState,
)
from substrate.ingest_checkpoint import CheckpointStore  # noqa: E402

# Typed (free-form) event action_types for the continuous engine. The event log
# accepts free-form action_type strings on the legacy log_event path (the typed
# schema union is for the role pipeline); these are the ingest-engine vocabulary
# the --status snapshot reconstructs from after a restart (M6).
EVT_ROUND = "corpus.ingest.round"        # one rotation round summary
EVT_SOURCE = "corpus.ingest.source"      # one source's per-round counts
EVT_MERGE = "corpus.ingest.merge"        # one staging->merge (window_s, rows)
EVT_GOVERNOR = "corpus.ingest.governor"  # a governor state change / decision
EVT_HALT = "corpus.ingest.halt"          # clean halt (budget / all-banned)

# Merge-cadence defaults (M4). Each merge holds the live writer for `window_s`
# (seconds), so the cadence is tuned to keep windows brief + frequent enough
# that staged work is not lost on a crash, while not merging so often that the
# live writer is contended. Configurable via flags; rationale per value:
DEFAULT_MERGE_COUNT = 200      # docs: ~one curated spine; a few-seconds merge.
DEFAULT_MERGE_SIZE_BYTES = 256 * 1024 * 1024  # 256 MiB staged -> bounded window.
DEFAULT_MERGE_INTERVAL_S = 15 * 60.0          # 15 min: a floor so a slow trickle
#                                               still merges (staged work is not
#                                               left unmerged indefinitely).

# PACE-band throughput reduction (M5). In the PACE band the per-source limit is
# scaled by this factor (fewer docs/round) so throughput measurably drops vs OK.
PACE_LIMIT_FACTOR = 0.25


@dataclass
class _StagingAccumulator:
    """Tracks staged-but-unmerged work so the cadence (M4) can decide WHEN to
    fire SPR-01's merge. ``count`` is staged docs since the last merge;
    ``staging_db`` is the path whose on-disk size is the size trigger;
    ``last_merge_ts`` is when the last merge completed (epoch). Pure bookkeeping
    — it never writes the DB."""

    staging_db: str
    count: int = 0
    last_merge_ts: float = 0.0

    def staging_size_bytes(self) -> int:
        try:
            return int(os.path.getsize(self.staging_db))
        except OSError:
            return 0

    def should_merge(
        self, *, count_threshold: int, size_threshold: int,
        interval_threshold: float, now: float,
    ) -> str | None:
        """Return the FIRST tripped trigger name (count|size|interval) or None.
        Order is count, then size, then interval — whichever trips first; a
        single call returns one reason so the caller fires exactly one merge."""
        if self.count >= count_threshold and self.count > 0:
            return "count"
        if self.staging_size_bytes() >= size_threshold and self.count > 0:
            return "size"
        if (
            self.count > 0
            and self.last_merge_ts > 0
            and (now - self.last_merge_ts) >= interval_threshold
        ):
            return "interval"
        return None


def _emit(action_type: str, payload: dict, *, events_dir: str | None = None) -> None:
    """Emit one continuous-engine event under the SYSTEM investigation. Filed on
    the legacy free-form log_event path (no typed schema needed); telemetry is
    best-effort and never breaks the run (log_event swallows write errors)."""
    log_event(
        SYSTEM_INVESTIGATION_ID, action_type,
        payload=payload, role="corpus_ingest",
        policy_id="orchestrator-deterministic", events_dir=events_dir,
    )


@dataclass
class SourceRoundResult:
    """Per-source outcome of one round (the M6 honesty unit): how many were
    discovered, ingested-to-staging, and rejected, with the reject rate computed
    HONESTLY (rejected / discovered) — never a hidden drop."""

    source: str
    discovered: int = 0
    ingested: int = 0
    rejected: int = 0
    skipped_seen: int = 0  # already-ingested (resume dedup) — not a rejection
    banned_until: float = 0.0

    @property
    def reject_rate(self) -> float:
        denom = self.ingested + self.rejected
        return (self.rejected / denom) if denom else 0.0

    def to_payload(self) -> dict:
        return {
            "source": self.source,
            "discovered": self.discovered,
            "ingested": self.ingested,
            "rejected": self.rejected,
            "skipped_seen": self.skipped_seen,
            "reject_rate": round(self.reject_rate, 4),
            "banned_until": self.banned_until,
        }


class ContinuousRunner:
    """The standing engine. ONE process, ONE in-process loop. Composes the
    existing spine; mints no new merge/rate/dedup/rights logic.

    Lifecycle of one round:
      1. governor.check() — if HALT, persist checkpoint state is already durable
         (it is written per-source as we go), emit a halt event, stop scheduling.
      2. discover_all(args) — ban-aware rotation (SPR-03) picks non-banned
         sources; a banned source is skipped this round and others advance.
      3. For each discovered candidate, consult the checkpoint's dedup-basis
         seen-set; skip an already-ingested basis (resume dedup, SPR-04 key).
      4. plan_corpus + execute_plan stage the survivors (off the live writer).
      5. record_unit() atomically advances each source's cursor + seen-set.
      6. cadence check -> SPR-01 merge_staging when count/size/interval trips.
      7. emit per-source + round + merge events (M6).

    A SIGTERM/SIGKILL at any step loses at most the in-flight unit, which the
    dedup basis (in the checkpoint + SPR-01's idempotent merge) makes a no-op on
    restart. The cursor only ever advances.
    """

    def __init__(
        self,
        args: argparse.Namespace,
        *,
        checkpoint: CheckpointStore | None = None,
        governor: BudgetGovernor | None = None,
        now: Callable[[], float] = _time.time,
        sleep: Callable[[float], None] = _time.sleep,
    ) -> None:
        self.args = args
        self.dry_run = bool(args.dry_run)
        self.checkpoint = checkpoint or CheckpointStore()
        # In dry-run there is no staging file; the live DB path is only read by
        # the governor (size) — never written. Resolve the live DB for governor
        # readings (size + the filesystem free space), defaulting safely.
        self._live_db = args.db_path or ""
        self.governor = governor or BudgetGovernor(
            db_path=self._live_db, staging_dir=(
                os.path.dirname(os.path.abspath(args.staging_db))
                if args.staging_db else None
            ),
        )
        self._now = now
        self._sleep = sleep
        self.events_dir = getattr(args, "events_dir", None)
        # Cadence thresholds (M4) — flags with the documented defaults.
        self.merge_count = int(getattr(args, "merge_count", DEFAULT_MERGE_COUNT))
        self.merge_size = int(getattr(args, "merge_size_bytes", DEFAULT_MERGE_SIZE_BYTES))
        self.merge_interval = float(
            getattr(args, "merge_interval_s", DEFAULT_MERGE_INTERVAL_S)
        )
        self.max_rounds = getattr(args, "max_rounds", None)
        self.round_sleep_s = float(getattr(args, "round_sleep_s", 0.0))
        self._accum: _StagingAccumulator | None = None
        if args.staging_db and not self.dry_run:
            self._accum = _StagingAccumulator(
                staging_db=os.path.abspath(os.path.expanduser(args.staging_db)),
                last_merge_ts=self._now(),
            )

    # -- per-round scheduling ------------------------------------------------

    def _candidate_basis(self, pc: PlannedCandidate) -> str:
        """The SPR-04 content-stable dedup basis for a candidate — the SAME
        value the cross-source dedup keyed on and SPR-01 turns into the
        document_id. NOT re-derived here: it calls substrate.dedup."""
        return identity_basis(pc.ref.identity_record())

    def _effective_limit(self, governor_state: BudgetState) -> int:
        """The per-source discovery limit for this round. In the PACE band it is
        scaled down so throughput measurably drops vs OK (M5)."""
        base = int(self.args.limit)
        if governor_state is BudgetState.PACE:
            return max(1, int(base * PACE_LIMIT_FACTOR))
        return base

    def run_round(self, round_index: int) -> dict:
        """Run ONE scheduling round. Returns a structured round summary (also
        emitted to the event log). Does not loop — `run()` loops over this so a
        test can drive a single round deterministically."""
        verdict = self.governor.check()

        if verdict.state is BudgetState.HALT:
            # Clean halt: per-source checkpoints are ALREADY durable (written as
            # each unit completed). Do NOT start a new merge or schedule new
            # work. Emit the halt reason so the operator/status sees WHY.
            _emit(EVT_HALT, {
                "round": round_index, "reason": "budget",
                "governor": verdict.render(),
            }, events_dir=self.events_dir)
            _emit(EVT_GOVERNOR, {
                "round": round_index, "state": verdict.state.value,
                "reasons": list(verdict.reasons),
            }, events_dir=self.events_dir)
            return {
                "round": round_index, "halted": True, "reason": "budget",
                "governor_state": verdict.state.value,
                "governor_reasons": list(verdict.reasons),
                "sources": [], "merged": None,
            }

        # PACE/OK both schedule; PACE shrinks the per-source limit.
        eff_limit = self._effective_limit(verdict.state)
        # discover_all reads args.limit; pass the paced limit by a shallow copy
        # so the source rotation + connector dispatch are reused UNCHANGED.
        round_args = argparse.Namespace(**vars(self.args))
        round_args.limit = eff_limit
        outcome = discover_all(round_args)

        _emit(EVT_GOVERNOR, {
            "round": round_index, "state": verdict.state.value,
            "reasons": list(verdict.reasons),
            "free_disk_bytes": verdict.reading.free_disk_bytes,
            "db_size_bytes": verdict.reading.db_size_bytes,
            "rss_bytes": verdict.reading.rss_bytes,
            "effective_limit": eff_limit,
        }, events_dir=self.events_dir)

        if outcome.all_banned:
            _emit(EVT_HALT, {
                "round": round_index, "reason": "all_banned",
                "soonest_resume": outcome.soonest_resume,
            }, events_dir=self.events_dir)
            return {
                "round": round_index, "halted": True, "reason": "all_banned",
                "soonest_resume": outcome.soonest_resume,
                "governor_state": verdict.state.value, "sources": [], "merged": None,
            }

        # Group discovered candidates by source, filtering already-seen bases
        # (resume dedup, SPR-04 key) BEFORE planning so a re-ingest never even
        # reaches staging. The cursor advances regardless (we made progress).
        per_source: dict[str, SourceRoundResult] = {}
        fresh: list[PlannedCandidate] = []
        fresh_bases_by_source: dict[str, set[str]] = {}
        for pc in outcome.candidates:
            res = per_source.setdefault(pc.source, SourceRoundResult(source=pc.source))
            res.discovered += 1
            basis = self._candidate_basis(pc)
            if self.checkpoint.has_seen(pc.source, basis):
                res.skipped_seen += 1
                continue
            fresh.append(pc)
            fresh_bases_by_source.setdefault(pc.source, set()).add(basis)

        # Plan + execute the FRESH survivors through the unchanged spine. The
        # plan is pure; execute_plan stages (or, in dry-run, writes nothing).
        merged_summary: dict | None = None
        if fresh:
            plan = plan_corpus(fresh)
            # Map kept candidate -> its source so per-source ingested counts are
            # honest (plan dedups across sources; the kept set is what stages).
            kept_sources = [pc.source for pc in plan.to_ingest]
            write_target = None
            if not self.dry_run and self.args.staging_db:
                from runtime.staging_db import resolve_ingest_target
                write_target = resolve_ingest_target(
                    db_path=self.args.db_path, staging_db=self.args.staging_db
                )
            report = execute_plan(plan, db_path=write_target, dry_run=self.dry_run)

            # Attribute ingested/rejected per source. In dry-run nothing is
            # written, so "ingested" is the planned-to-ingest count (what WOULD
            # stage) — the dry-run reports the same plan a real run executes.
            planned_ct = len(plan.to_ingest)
            ingested_ct = planned_ct if self.dry_run else report.ingested
            # Quality-rejected candidates, per source (honest reject rate, M6).
            for pc, _verdict in plan.quality_rejected:
                r = per_source.setdefault(pc.source, SourceRoundResult(source=pc.source))
                r.rejected += 1
            # Distribute ingested across the kept set's sources.
            for src in kept_sources[:ingested_ct]:
                per_source.setdefault(src, SourceRoundResult(source=src)).ingested += 1
            if self._accum is not None:
                self._accum.count += ingested_ct

        # Advance each source's checkpoint ATOMICALLY (cursor + seen bases).
        # The cursor is round-monotonic per source (we made progress this
        # round); the seen-set unions the bases we just staged so a restart
        # mid-round re-discovers but skips them.
        for src, res in per_source.items():
            new_bases = fresh_bases_by_source.get(src, set())
            cur = self.checkpoint.cursor(src)
            next_cursor = self._advance_cursor(cur)
            self.checkpoint.record_unit(src, cursor=next_cursor, new_bases=new_bases)
            res.banned_until = self._banned_until(src)
            _emit(EVT_SOURCE, {"round": round_index, **res.to_payload()},
                  events_dir=self.events_dir)

        # Cadence (M4): fire SPR-01's merge if a trigger tripped. Exactly one
        # merge per trip — should_merge returns one reason, we merge once.
        if self._accum is not None:
            trigger = self._accum.should_merge(
                count_threshold=self.merge_count,
                size_threshold=self.merge_size,
                interval_threshold=self.merge_interval,
                now=self._now(),
            )
            if trigger:
                merged_summary = self._do_merge(round_index, trigger)

        round_summary = {
            "round": round_index,
            "halted": False,
            "governor_state": verdict.state.value,
            "governor_reasons": list(verdict.reasons),
            "effective_limit": eff_limit,
            "rotation_log": list(outcome.rotation_log),
            "sources": [res.to_payload() for res in per_source.values()],
            "corpus_size_docs": self._corpus_size_docs(),
            "last_merge_ts": (self._accum.last_merge_ts if self._accum else 0.0),
            "merged": merged_summary,
        }
        _emit(EVT_ROUND, round_summary, events_dir=self.events_dir)
        return round_summary

    def _advance_cursor(self, current: str | None) -> str:
        """Advance a source's opaque cursor. We use a monotonic round counter so
        the cursor strictly advances (never resets) across restarts — the
        contract the resume test asserts. (Per-source pagination tokens are an
        orchestration detail the connectors own; this engine's cursor records
        rounds completed so resume never rewinds.)"""
        try:
            n = int(current) if current is not None else 0
        except (TypeError, ValueError):
            n = 0
        return str(n + 1)

    def _banned_until(self, source: str) -> float:
        """Read SPR-03's banned_until sentinel for a source (read-only)."""
        try:
            from substrate.source_throttle import SourceThrottle
            return SourceThrottle().banned_until(source)
        except Exception:
            return 0.0

    def _corpus_size_docs(self) -> int:
        """Live corpus document count, read-only (connect_read; never the write
        lock). 0 / -1-safe when the DB is absent (dry-run / fresh box)."""
        if not self._live_db or not os.path.exists(self._live_db):
            return 0
        try:
            from runtime.db_lock import connect_read
            con = connect_read(self._live_db)
            try:
                return int(con.execute("SELECT count(*) FROM documents").fetchone()[0])
            finally:
                con.close()
        except Exception:
            return 0

    def _do_merge(self, round_index: int, trigger: str) -> dict:
        """Fire SPR-01's merge_staging UNCHANGED. The budget governor is
        re-checked first: if HALT, the merge is NOT started (the in-flight-merge
        safety contract — never begin an endangering INSERT...SELECT). On
        success, reset the staging accumulator + stamp last_merge_ts."""
        assert self._accum is not None
        pre = self.governor.check()
        if pre.state is BudgetState.HALT:
            _emit(EVT_HALT, {
                "round": round_index, "reason": "budget_pre_merge",
                "governor": pre.render(),
            }, events_dir=self.events_dir)
            return {"trigger": trigger, "skipped": "budget_halt",
                    "governor": pre.render()}
        if not self.args.db_path:
            # No live DB to merge into (e.g. staging-only smoke). Reset the
            # accumulator so the cadence does not re-fire every round.
            self._accum.count = 0
            self._accum.last_merge_ts = self._now()
            return {"trigger": trigger, "skipped": "no_live_db"}

        from tools.merge_staging import merge_staging
        result = merge_staging(
            live_db=self.args.db_path, staging_db=self._accum.staging_db
        )
        self._accum.count = 0
        self._accum.last_merge_ts = self._now()
        summary = {
            "trigger": trigger,
            "window_s": round(result.window_s, 4),
            "total_inserted": result.total_inserted,
            "tables": [
                {"table": t.table, "inserted": t.inserted, "skipped": t.skipped}
                for t in result.tables
            ],
        }
        _emit(EVT_MERGE, {"round": round_index, **summary}, events_dir=self.events_dir)
        return summary

    # -- the loop ------------------------------------------------------------

    def run(self) -> int:
        """Drive rounds until HALT, all-banned, or max_rounds. The ONLY loop —
        one process, one box. Returns a process exit code."""
        round_index = 0
        while True:
            round_index += 1
            summary = self.run_round(round_index)
            print(_json.dumps(summary, default=str))
            if summary.get("halted"):
                reason = summary.get("reason")
                print(f"continuous: halted cleanly ({reason})", file=sys.stderr)
                return 0 if reason == "all_banned" else 0
            if self.max_rounds and round_index >= self.max_rounds:
                print(
                    f"continuous: reached max_rounds={self.max_rounds}; stopping",
                    file=sys.stderr,
                )
                return 0
            if self.round_sleep_s > 0:
                self._sleep(self.round_sleep_s)


# ---------------------------------------------------------------------------
# --status — a READ-ONLY snapshot reconstructed from persisted state (M6).
# ---------------------------------------------------------------------------


def status_snapshot(
    *,
    checkpoint: CheckpointStore | None = None,
    events_dir: str | None = None,
    db_path: str | None = None,
) -> dict:
    """Reconstruct the run-health snapshot from PERSISTED state only — the event
    log (per-source counts, reject rates, last-merge, governor state) + the
    checkpoint store (cursors, seen-id counts) + the throttle sentinel
    (banned_until). It survives a restart because it reads files, not in-memory
    counters (M6 criterion 3).

    READ-ONLY: it opens the live DB read-only (connect_read) at most for a
    corpus-size count and NEVER calls connect_write — it cannot contend for the
    single-writer lock while the API serves (M6 criterion 2 + SPR-10 read-only).
    """
    cp = checkpoint or CheckpointStore()

    # Reconstruct per-source aggregates from the event log's source events.
    rows = trajectory(SYSTEM_INVESTIGATION_ID, events_dir=events_dir)
    per_source: dict[str, dict] = {}
    last_merge_ts = 0.0
    last_governor: dict | None = None
    for r in rows:
        at = r.get("action_type")
        payload = r.get("payload") or {}
        if at == EVT_SOURCE:
            src = payload.get("source")
            if not src:
                continue
            agg = per_source.setdefault(src, {
                "source": src, "discovered": 0, "ingested": 0,
                "rejected": 0, "skipped_seen": 0, "banned_until": 0.0,
            })
            for k in ("discovered", "ingested", "rejected", "skipped_seen"):
                agg[k] += int(payload.get(k, 0) or 0)
            agg["banned_until"] = max(
                agg["banned_until"], float(payload.get("banned_until", 0.0) or 0.0)
            )
        elif at == EVT_MERGE:
            # last_merge_ts is the emission time of the most recent merge event.
            last_merge_ts = r.get("emitted_at") or last_merge_ts
        elif at == EVT_GOVERNOR:
            last_governor = payload

    # Honest reject rate per source (rejected / (ingested + rejected)).
    sources_out = []
    for src, agg in sorted(per_source.items()):
        denom = agg["ingested"] + agg["rejected"]
        agg["reject_rate"] = round(agg["rejected"] / denom, 4) if denom else 0.0
        # Cursor + seen-count come from the checkpoint store (survives restart).
        scp = cp.get(src)
        agg["cursor"] = scp.cursor
        agg["ingested_ids_seen"] = len(scp.ingested_ids_seen)
        # Live banned_until from the sentinel (read-only) overrides the stale
        # event value when present.
        try:
            from substrate.source_throttle import SourceThrottle
            agg["banned_until"] = SourceThrottle().banned_until(src)
        except Exception:
            pass
        sources_out.append(agg)

    # Corpus size — read-only count, 0 when no live DB available.
    corpus_size = 0
    resolved_db = db_path or os.environ.get("ANTIEK_DUCKDB_PATH")
    if resolved_db and os.path.exists(resolved_db):
        try:
            from runtime.db_lock import connect_read
            con = connect_read(resolved_db)
            try:
                corpus_size = int(
                    con.execute("SELECT count(*) FROM documents").fetchone()[0]
                )
            finally:
                con.close()
        except Exception:
            corpus_size = 0

    return {
        "sources": sources_out,
        "corpus_size_docs": corpus_size,
        "last_merge_ts": last_merge_ts,
        "governor": last_governor,
        "checkpointed_sources": sorted(cp.all_sources().keys()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    # --status: read-only snapshot (M6). Reconstructs from the event log +
    # checkpoint; never opens the write lock. Operator note: a prod --status
    # against the live DB additionally reads the live corpus size read-only;
    # offline (no live DB) it reports corpus_size_docs=0 with everything else
    # reconstructed from persisted state.
    if getattr(args, "status", False):
        snap = status_snapshot(
            events_dir=getattr(args, "events_dir", None),
            db_path=args.db_path,
        )
        print(_json.dumps(snap, indent=2, default=str))
        return 0

    # --continuous: the standing engine (M2–M6). One process, one in-process
    # loop. Composes discover_all + plan_corpus + execute_plan + merge_staging.
    if getattr(args, "continuous", False):
        if not args.dry_run and not args.staging_db:
            print(
                "error: --continuous requires --staging-db (the engine stages "
                "off the live hot path and merges on a cadence; a direct live "
                "write per round would defeat the brief-window contract). Use "
                "--dry-run to plan without writing.",
                file=sys.stderr,
            )
            return 2
        runner = ContinuousRunner(args)
        return runner.run()

    # Staging mode (SPR-01 keystone): the ingest writes to a separate staging
    # DuckDB off the live hot path. The live API keeps serving the live DB
    # throughout; tools/merge_staging.py later copies the staged rows in
    # through one bounded connect_write. The prod-write guard and lock pre-
    # flight do NOT apply — staging is never the prod substrate, and the live
    # writer is not held during the ingest.
    write_target = args.db_path
    if args.staging_db and not args.dry_run:
        from runtime.staging_db import resolve_ingest_target

        write_target = resolve_ingest_target(
            db_path=args.db_path, staging_db=args.staging_db
        )

    if not args.dry_run and not args.staging_db:
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
        outcome = discover_all(args)
    except SystemExit:
        raise
    except Exception as exc:  # network / parse failure during discovery
        print(f"error: discovery failed: {exc}", file=sys.stderr)
        return 1

    # Surface the rotation decisions so a skip is observable, not silent.
    for line in outcome.rotation_log:
        print(f"rotation: {line}", file=sys.stderr)

    # All configured sources banned -> clean halt recording the soonest resume,
    # NOT a generic 'no candidates' (M3 criterion 3): the operator/SPR-09
    # scheduler reads this to time a resume instead of re-hitting banned sources.
    if outcome.all_banned:
        from datetime import datetime

        resume = outcome.soonest_resume
        when = (
            datetime.fromtimestamp(resume, tz=UTC).isoformat()
            if resume > 0 else "unknown"
        )
        print(
            f"all configured sources are banned; halting cleanly. soonest "
            f"resume at banned_until={resume:.0f} ({when}) — re-run after then.",
            file=sys.stderr,
        )
        return 3

    candidates = list(outcome.candidates)
    if not candidates:
        print("no candidates discovered (check your selectors)", file=sys.stderr)
        return 1

    plan = plan_corpus(candidates)
    if args.dry_run:
        header = "DRY RUN — nothing written\n"
    elif args.staging_db:
        header = f"STAGING INGEST → {write_target}\n"
    else:
        header = "INGEST PLAN\n"
    print(header + plan.render())

    report = execute_plan(plan, db_path=write_target, dry_run=args.dry_run)
    if report.dry_run:
        print(f"\ndry-run: {report.planned} would be ingested; wrote nothing")
    elif args.staging_db:
        print(
            f"\nstaged {report.ingested} / {report.planned} planned; "
            f"{report.failed} failed — now merge with "
            f"`python -m tools.merge_staging --live-db <live> --staging-db {write_target}`"
        )
    else:
        print(
            f"\ningested {report.ingested} / {report.planned} planned; "
            f"{report.failed} failed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    *, snapshot_path: str, category: Optional[str], limit: int,
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
    *, query: Optional[str], category: Optional[str],
    ids: Optional[Sequence[str]], limit: int, investigation_id: str,
    arxiv_source: str = "export", bulk_snapshot: Optional[str] = None,
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
    # This does NOT let arXiv ingest SUCCEED while the ban is active; it only
    # stops extending the ban and stops aborting PD+OA. arXiv resumes once
    # banned_until elapses. (S2 metadata fallback is deliberately NOT used: S2
    # omits the arXiv license element, so it would deny-gate every CC-BY paper.)
    try:
        if ids:
            for pid in ids:
                throttle.wait_if_needed()
                p = _request_with_429_sentinel(
                    throttle, lambda pid=pid: fetch_by_id(pid)
                )
                if p is not None:
                    papers.append(p)
        else:
            throttle.wait_if_needed()
            papers = list(
                _request_with_429_sentinel(
                    throttle,
                    lambda: search(query=query, category=category, max_results=limit),
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

    def get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
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
    from substrate.source_throttle import SourceBanned, SourceThrottle
    from tools.ingest_public_domain import CURATED_GUTENBERG_IDS

    # SHARED persistent ban sentinel for gutendex (the 2026-05-29 503 source).
    # A 429/503 now survives a process restart; an already-banned gutendex
    # raises SourceBanned and PD self-skips instead of re-hitting the source.
    persistent = SourceThrottle()
    client = _BodyCachingClient(
        SourceClient(min_interval_s=min_interval_s, persistent=persistent)
    )
    selected_ids: Optional[Sequence[int]] = ids
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
    *, source: str, query: Optional[str], limit: int, investigation_id: str,
    biorxiv_server: str = "biorxiv", biorxiv_interval: Optional[str] = None,
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
    *, source: str, query: Optional[str], limit: int, throttle,
    biorxiv_server: str, biorxiv_interval: Optional[str],
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
    with httpx.Client(follow_redirects=True) as c:
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


def _open_access_candidates(
    *, source: str, query: Optional[str], author: Optional[str],
    dois: Optional[Sequence[str]], limit: int, investigation_id: str,
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

            last_exc: Optional[Exception] = None
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
    libretexts_library: Optional[str] = None,
    doab_query: Optional[str] = None,
    ocw_query: Optional[str] = None,
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
    # connectors; the last five (core / semantic_scholar / biorxiv / medrxiv /
    # plos) are the SPR-07 paper aggregators routed through acquisition.papers.
    p.add_argument(
        "--oa-source",
        choices=(
            "openalex", "unpaywall", "pmc", "doaj",
            "core", "semantic_scholar", "biorxiv", "medrxiv", "plos",
        ),
        help="open-access aggregator (incl. SPR-07 paper aggregators)",
    )
    p.add_argument("--oa-query", help="open-access: search query (openalex / core / s2 / plos)")
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
    return p


def _csv_ints(value: Optional[str]) -> Optional[list[int]]:
    if not value:
        return None
    return [int(x) for x in value.split(",") if x.strip()]


def _csv_strs(value: Optional[str]) -> Optional[list[str]]:
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
    if want_oa:
        if args.oa_source in PAPER_AGGREGATOR_OA_SOURCES:
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
        else:
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

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
        from datetime import datetime, timezone

        resume = outcome.soonest_resume
        when = (
            datetime.fromtimestamp(resume, tz=timezone.utc).isoformat()
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

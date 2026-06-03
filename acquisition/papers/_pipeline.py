"""Shared paper-connector core (SPR-07): one record shape + the
discover → resolve-stable-id → dedup-ref → classify → stage pipeline that
CORE / Semantic Scholar / bioRxiv / PLOS / arXiv-bulk all reuse.

THE BINDING (the reason this sprint exists): every connector derives a paper's
``content_class`` ONLY by calling :func:`classify_paper`, which delegates to the
single chokepoint ``acquisition.licenses_core.classify``. No connector ever
hard-codes / assigns a content_class by any other route. The legacy
``acquisition.books.public_domain`` style of passing a literal
``content_class="public_domain"`` straight to ingest is exactly what this wave
retires — the source declares a license *string*, the chokepoint decides the
class, and that decision (class + license_basis) is what reaches ingest.

§9.0 deny-by-default flows for free: ``classify`` resolves an unknown / NC / ND
/ closed / missing license to ``GATED_DEFAULT_CONTENT_CLASS`` with
``servable=False``; only a positively-resolved redistribution license lands a
servable class (membership in ``substrate.constants.SERVABLE_CONTENT_CLASSES``).
A servable result NEVER carries an empty ``license_basis`` (impossible by
construction). The connectors then NAME the source field in the basis so the
SPR-10 audit can answer "why is this servable?" from the row alone.

§16 box-bounded: this module is pure in-process logic + a thin ingest wrapper
over the shared ``ingest_servable_book`` (which funnels through the single
``runtime.db_lock.connect_write`` writer). No new runtime, no new DB engine, no
network — discovery + fetch live in the per-source modules, themselves behind
the shared ``SourceThrottle``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from acquisition.corpus_quality import CandidateRef
from acquisition.licenses_core import ClassificationResult, classify

# ---------------------------------------------------------------------------
# The connector-agnostic paper record.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperRecord:
    """One paper as a source surfaced it, reduced to the fields the pipeline
    needs. Every source maps its native record into one of these.

    Identity precedence is the single ``substrate.dedup`` ladder: a paper is
    keyed by its DOI first, then its arXiv id, then its source-local id — never
    title+author (a generic-title false-merge hazard). ``license`` is the RAW
    declared license string the source carried for THIS record (a CC URI, a
    compact code, an arXiv terms URI, ``None`` when the source declared none) —
    it is passed verbatim to the chokepoint; the connector never interprets it.
    ``source_declaration`` carries non-license positive signals (e.g.
    ``{"public_domain": ...}`` or a ``{"rights_holder": ...}`` accrual hint).

    ``has_servable_body`` records whether the source can actually surface a
    real full-text body (e.g. S2's ``openAccessPdf``). When False the work is
    handled metadata+abstract only — even if its license would be servable —
    because we cannot serve a body we cannot fetch; the license still flows
    through ``classify`` so the recorded class is honest.
    """

    source: str  # provenance: "core" | "semantic_scholar" | "biorxiv" | ...
    source_id: str  # source-local id (CORE id / S2 corpusId / arXiv id / DOI)
    title: str
    license: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    pdf_url: str | None = None  # a fetchable full-text PDF, when offered
    has_servable_body: bool = False
    legitimate_source: bool = True  # public API / open dump -> always legitimate
    source_declaration: Mapping[str, Any] = field(default_factory=dict)
    license_field: str | None = None  # WHICH source field carried the license
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def primary_author(self) -> str | None:
        return self.authors[0] if self.authors else None


# ---------------------------------------------------------------------------
# The classification step — the one route to a content_class.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperClassification:
    """The rights decision for one paper, plus the source-specific audit basis.

    ``result`` is the ClassificationResult straight from the chokepoint; the
    connector reads ``content_class`` / ``servable`` / ``ingest`` off it and
    never re-derives them. ``license_basis`` is the chokepoint's basis PREFIXED
    with the source + the exact field that justified it (e.g. ``"S2
    openAccessPdf.license"``), so a servable row names *why* it is servable for
    the SPR-10 audit. ``serve_body`` is the final "fetch + serve full text"
    answer: servable AND the source actually offers a body — deny-by-default
    composes with "we can't serve a body we can't fetch".
    """

    result: ClassificationResult
    license_basis: str
    serve_body: bool

    @property
    def content_class(self) -> str:
        return self.result.content_class

    @property
    def servable(self) -> bool:
        return self.result.servable

    @property
    def ingest(self) -> bool:
        return self.result.ingest


def classify_paper(record: PaperRecord) -> PaperClassification:
    """Resolve ONE paper's content_class via the single chokepoint.

    This is the only place the papers connectors decide servable-vs-gated. It
    hands ``record.license`` (the raw declared string) + ``source_declaration``
    + the legitimacy judgment to ``acquisition.licenses_core.classify`` and
    reads the class back — it interprets no license itself (no inline CC
    parsing anywhere in this package). The returned ``license_basis`` is the
    chokepoint's basis annotated with the source + the field name so the audit
    can trace the servability to a concrete source field.

    ``serve_body`` is True only when the chokepoint resolved a servable class
    AND the source offers a fetchable body; a servable-licensed record with no
    body (we can describe its rights but cannot fetch its full text) is staged
    metadata+abstract only, exactly like a gated one — but with its honest
    (servable) class recorded.
    """
    result = classify(
        record.license,
        record.source_declaration,
        legitimate_source=record.legitimate_source,
    )
    basis = _source_basis(record, result)
    serve_body = result.servable and record.has_servable_body and bool(record.pdf_url)
    return PaperClassification(result=result, license_basis=basis, serve_body=serve_body)


def _source_basis(record: PaperRecord, result: ClassificationResult) -> str:
    """Compose the source-specific ``license_basis``: name the source + the
    exact field the license was read from, then the chokepoint's own basis.

    Defensibility (rigor #5): a servable paper's basis must name the source
    field that justified it — never a bare "open". The chokepoint already
    guarantees a non-empty basis for a servable result; we only prepend the
    provenance the audit needs ("which source, which field")."""
    field_tag = f".{record.license_field}" if record.license_field else ""
    return f"{record.source}{field_tag}; {result.license_basis}"


def paper_candidate_ref(record: PaperRecord, *, body: str | None = None) -> CandidateRef:
    """Project a paper into the orchestrator's dedup ref so cross-source
    collapse keys through the single ``substrate.dedup`` ladder.

    The ref carries the identity-bearing fields in precedence order: DOI first,
    then arXiv id, then the source-local id (namespaced by source so a CORE id
    and an arXiv id cannot collide). ``ref_id`` is an opaque, source-namespaced
    handle. The same paper surfaced by CORE + S2 + arXiv-bulk under one DOI
    therefore resolves to ONE identity key and collapses to one document.
    ``body`` (when a real extracted body is available) lets a DOI-less record
    key on its content hash rather than the LOW title fallback."""
    return CandidateRef(
        ref_id=f"{record.source}:{record.source_id}",
        doi=record.doi,
        arxiv_id=record.arxiv_id,
        # Namespaced source id so two sources' local ids never collide at the
        # source-id precedence level.
        source_id=f"{record.source}:{record.source_id}",
        title=record.title or None,
        author=record.primary_author,
        body=body or None,
    )


# ---------------------------------------------------------------------------
# The servable/gated ingest step — composes the shared servable-book path.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperIngestResult:
    """What :func:`ingest_servable_paper` returns. ``content_class`` +
    ``license_basis`` are echoed so a dry-run can report the decision without
    re-querying the substrate; ``servable_full_text`` is the DERIVED
    deny-by-default answer the substrate computed from the class."""

    document_id: str
    content_class: str
    license_basis: str
    servable_full_text: bool
    served_body: bool


def ingest_servable_paper(
    record: PaperRecord,
    classification: PaperClassification,
    *,
    investigation_id: str,
    pdf_bytes: bytes,
    source_tier: int = 2,
    db_path: str | None = None,
    embedder: Any = None,
) -> PaperIngestResult:
    """Stage a SERVABLE paper's full text through the shared servable-book path.

    Only called for ``classification.serve_body`` records — a servable license
    AND a fetchable body. The resolved ``content_class`` + ``license_basis``
    from the chokepoint are passed EXPLICITLY to ``ingest_servable_book`` so the
    servable decision is an auditable row, not a silent default. The body write
    funnels through that path's single ``runtime.db_lock.connect_write`` writer
    (§16). Gated records do NOT come here — their body is never fetched/served;
    they take the metadata+abstract path in the per-source connector.
    """
    from acquisition.books.adapter import ingest_servable_book

    if not classification.serve_body:
        raise ValueError(
            f"ingest_servable_paper called for a non-servable record "
            f"({record.source}:{record.source_id}, class="
            f"{classification.content_class}); gated bodies are never served"
        )
    if not pdf_bytes:
        raise ValueError(
            f"empty PDF bytes for {record.doi or record.source_id} — fetch "
            "failed or the URL was a landing page, not a PDF"
        )

    result = ingest_servable_book(
        pdf_bytes,
        investigation_id=investigation_id,
        content_class=classification.content_class,
        license_basis=classification.license_basis,
        source_uri=record.pdf_url or (f"https://doi.org/{record.doi}" if record.doi else None),
        source_tier=int(source_tier),
        provenance=record.pdf_url or record.source,
        db_path=db_path,
        embedder=embedder,
    )
    return PaperIngestResult(
        document_id=result.document_id,
        content_class=classification.content_class,
        license_basis=classification.license_basis,
        servable_full_text=result.servable_full_text,
        served_body=True,
    )

"""arXiv → Antiek substrate adapter.

Converts an ``ArxivPaper`` into typed substrate events + graph rows:

1. Emit ``document.loaded`` with the abstract as ``markdown``
   media_type. ``source_uri`` = abs URL; ``content_hash`` = sha256
   of the abstract.
2. Insert a ``documents`` row with stable doc id
   ``doc-arxiv-<sanitized_id>``. arXiv preprints default to source
   tier 3 (academic but not peer-reviewed); caller can override.
3. Chunk the abstract via ``processing.chunking.chunk_markdown``.
   Insert each chunk into the ``chunks`` table; insert one
   ``substrate/graph`` node per chunk (label = truncated text).

Result: ``IngestResult`` with ``document_id``, ``chunk_ids``,
``node_ids``, and the emitted ``document.loaded`` event id.

**Idempotency:** the doc id is content-stable (derived from the
arxiv id), and ``insert_document`` / ``insert_chunk`` / ``insert_node``
all use ``on_conflict='ignore'`` so re-ingesting the same paper
no-ops on the DB side. The ``document.loaded`` event still fires
each time — the trajectory log is append-only by design.

Two ingest paths live here:

- ``ingest_paper`` — the ORIGINAL abstract-only / metadata path. It is
  license-blind by design (an abstract is short and factual; this path
  predates the rights layer). Kept for callers that only want the
  abstract landed as a source. It does NOT serve full text.
- ``ingest_paper_with_rights`` (SPR-02) — the FULL-TEXT path. It resolves
  ``paper.license_uri`` to a servable content_class via
  ``acquisition.arxiv.licenses``, fetches the PDF, and routes through the
  shared ``acquisition.books.ingest_servable_book`` so the legal-gate /
  deny-by-default classification has exactly one home. This is the path
  the SPR-02 CLI uses. The two paths are deliberately distinct (abstract
  vs full text) — they are NOT silently-diverging copies of the same
  ingest.

**What this does NOT do:**
- Run the ``parameter_extractor`` role to mint nodes + edges from the
  abstract. That's the Loop 1 orchestrator's job; this adapter just lands
  the source.
- Re-derive full text from LaTeX. The full-text path ingests the PDF
  bytes; a LaTeX renderer is out of scope.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger("acquisition.arxiv.adapter")

# Repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    Chunk,
    chunk_markdown,
    content_hash,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    insert_chunk,
    insert_document,
    insert_node,
)
from substrate.rights.register import (  # noqa: E402
    SourceKind,
    register_source_document,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

from .client import ArxivPaper  # noqa: E402  # sys.path bootstrap
from .html_fetch import FetchedHtml  # noqa: E402  # sys.path bootstrap
from .licenses import (  # noqa: E402  # sys.path bootstrap
    LicenseResolution,
    license_basis_string,
    resolve_license,
)

# Tier policy: arXiv preprints are academic but unrefereed → tier 3.
# Tier 1 = peer-reviewed primary; Tier 5 = uncited social. The
# operator can override via ``ingest_paper(..., source_tier=N)``.
DEFAULT_ARXIV_SOURCE_TIER = 3

# Cap on node label length. The full title would blow past graph
# search ergonomics; truncated with ellipsis matches the
# wrestling-bridge convention.
_NODE_LABEL_MAX = 160


# ---------------------------------------------------------------------------
# Stable document id
# ---------------------------------------------------------------------------


_ARXIV_ID_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9.\-]")


def arxiv_doc_id(arxiv_id: str) -> str:
    """Stable Antiek doc id for an arXiv paper.

    Same arXiv id → same doc id across sessions, so a paper
    resurfacing in a new search dedups against prior ingestion.
    Sanitization keeps only ``[A-Za-z0-9.-]`` so DuckDB string
    handling stays simple."""
    sanitized = _ARXIV_ID_SANITIZE_RE.sub("-", arxiv_id.strip())
    if not sanitized:
        raise ValueError(f"empty/unrepresentable arxiv_id: {arxiv_id!r}")
    return f"doc-arxiv-{sanitized}"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestResult:
    """What ``ingest_paper`` returns. ``document_loaded_event_id`` is
    ``None`` when the event log is disabled
    (``ANTIEK_EVENTS_DISABLED``); the DB writes still happen."""

    document_id: str
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _format_abstract_markdown(paper: ArxivPaper) -> str:
    """Compose the abstract + light header so the chunker's
    heading-aware splitter has anchor metadata in the body.

    Authors + categories ride along so downstream nodes mint by
    parameter_extractor have access to provenance without re-fetch."""
    lines = [
        f"# {paper.title}",
        "",
        f"_arXiv {paper.arxiv_id}{paper.version} · {paper.abs_url}_",
        "",
    ]
    if paper.authors:
        lines.append("**Authors:** " + ", ".join(paper.authors))
        lines.append("")
    if paper.categories:
        lines.append("**Categories:** " + ", ".join(paper.categories))
        lines.append("")
    lines.append("## Abstract")
    lines.append("")
    lines.append(paper.abstract)
    return "\n".join(lines)


def ingest_paper(
    paper: ArxivPaper,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_ARXIV_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> IngestResult:
    """Ingest one arXiv abstract into the substrate.

    Emits ``document.loaded`` (typed), writes a ``documents`` row,
    chunks the abstract, writes chunks + per-chunk nodes. All DB
    writes are idempotent on the doc id; re-ingesting the same
    arXiv id is a no-op for the graph rows (the event still fires).

    ``investigation_id`` scopes the event + the node's
    ``investigation_id`` foreign key. For corpus-scoped sweeps not
    tied to a single investigation, callers can pass
    ``substrate.constants.SYSTEM_INVESTIGATION_ID``."""

    text = _format_abstract_markdown(paper)
    chash = "sha256:" + content_hash(text)
    document_id = arxiv_doc_id(paper.arxiv_id)

    # Emit document.loaded first so the trajectory carries the
    # ingestion signal before the graph rows land. The reading-UI
    # surface follows this ordering too.
    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(text.encode("utf-8")),
        title=paper.title,
        page_count=None,
        source_uri=paper.abs_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/arxiv",
    )

    # Open the DB. ensure_initialized creates the file + schema if
    # this is the operator's first ingest.
    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: list[Chunk] = chunk_markdown(text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
    chunks_written = 0

    emb = embedder or default_embedding_provider()

    # The graph schema requires LockedConnection. Open via the
    # write-lock helper so concurrent ingests serialize correctly.
    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/arxiv") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="academic_paper",
            source_uri=paper.abs_url,
            title=paper.title,
            author=", ".join(paper.authors) if paper.authors else None,
            published_at=paper.published_at,
            investigation_id=investigation_id,
            raw_text=text,
            metadata={
                "arxiv_id": paper.arxiv_id,
                "version": paper.version,
                "categories": list(paper.categories),
                "primary_category": paper.primary_category,
                "updated_at": paper.updated_at.isoformat(),
                "pdf_url": paper.pdf_url,
            },
            on_conflict="ignore",
        )
        register_source_document(
            con,
            document_id=document_id,
            source_kind=SourceKind.ACADEMIC_PREPRINT,
        )

        for i, chunk in enumerate(chunks):
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(chunk_id)
            chunks_written += 1

            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{paper.arxiv_id}#{i}"

            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "arxiv",
                    "arxiv_id": paper.arxiv_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
    )


# ---------------------------------------------------------------------------
# Rights-aware full-text ingest (SPR-02)
# ---------------------------------------------------------------------------

# arXiv preprints stay tier 3 even as full text — academic but unrefereed.
DEFAULT_ARXIV_FULLTEXT_SOURCE_TIER = 3

# Type of the injectable PDF fetcher: arxiv_id -> pdf bytes. Tests pass a
# stub that returns fixture bytes so CI never hits the network.
PdfFetcher = Callable[[str], bytes]

# Type of the injectable HTML fetcher: arxiv_id -> FetchedHtml | None.
# Tests pass a stub that returns a FetchedHtml fixture or None so CI never
# hits the network.  The default (``_default_fetch_html``) goes through the
# host-global rate governor — same discipline as the PDF path.
HtmlFetcher = Callable[[str], FetchedHtml | None]


@dataclass(frozen=True)
class IngestPaperWithRightsResult:
    """What ``ingest_paper_with_rights`` returns.

    ``servable_full_text`` is the derived "may we serve this paper's full
    text" answer — deny-by-default, so a default-arXiv-terms or
    unknown-license paper comes back False. ``content_class`` and
    ``license_basis`` are echoed so the caller (CLI dry-run) can report the
    rights decision without re-querying the substrate."""

    document_id: str
    content_class: str
    redistributable: bool
    servability: str
    servable_full_text: bool
    license_uri: str | None
    license_basis: str


def _default_fetch_pdf(arxiv_id: str) -> bytes:
    """Fetch a paper's PDF bytes from arxiv.org/pdf/<id>, host-rate-governed.

    Reuses the client's httpx + User-Agent convention. The HTTP send is routed
    through ``acquisition.arxiv.rate_governor.governed_request`` (SPR-09 M1) so
    this fallback fetcher honors the SAME host-global >= 3s spacing + 429
    ban-sentinel as the OAI harvest and the on-demand ``pdf_fetch`` path —
    closing the previously-ungoverned arxiv.org egress this function used to
    be (its throttle was nominally "the caller's responsibility", which a future
    caller of the adapter could forget). ``ArxivBanned`` propagates so an active
    ban PAUSES the batch rather than re-hitting the endpoint; network / HTTP
    errors propagate so the batch records a per-item failure and continues
    rather than ingesting an empty document.
    """
    from .client import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
    from .rate_governor import (
        arxiv_governed_client,
        canonical_arxiv_throttle,
        governed_request,
    )

    url = f"https://arxiv.org/pdf/{arxiv_id}"
    # REDIRECT-SAFE (SPR-09 round-5): arxiv.org/pdf 302-redirects (e.g. to a
    # versioned ``/pdf/<id>vN`` or ``.pdf`` URL, still an arXiv host). The client
    # carries the per-hop hooks so each arXiv redirect hop is governed too; the
    # outer ``governed_request`` governs the initial hop (the hooks defer to it).
    # BOTH must use the SAME throttle instance so the initial-hop claim handshake
    # matches (else the initial hop would be double-waited) — pin the canonical.
    throttle = canonical_arxiv_throttle()
    with arxiv_governed_client(throttle=throttle) as c:
        def _send() -> httpx.Response:
            return c.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=DEFAULT_TIMEOUT_S,
            )

        # Host-global rate gate: the send happens inside the governor's flock so
        # this fetch serializes against every other arXiv job on the box.
        # ``governed_request`` is generic over the send's response type, so ``r``
        # keeps the concrete ``httpx.Response`` for ``.content`` / status reads.
        r = governed_request(_send, throttle=throttle)
    r.raise_for_status()
    return r.content


def _default_fetch_html(arxiv_id: str) -> FetchedHtml | None:
    """Fetch a paper's HTML rendering from arxiv.org/html/<id>, host-rate-governed.

    Thin wrapper around :func:`acquisition.arxiv.html_fetch.fetch_html` that
    supplies the canonical throttle so callers that omit ``fetch_html`` still
    honour the host-global >= 3s spacing + 429 ban-sentinel.  ``ArxivBanned``
    propagates — same contract as :func:`_default_fetch_pdf`.
    """
    from .html_fetch import fetch_html as _fetch_html
    from .rate_governor import canonical_arxiv_throttle

    throttle = canonical_arxiv_throttle()
    return _fetch_html(arxiv_id, throttle=throttle)


def _record_fetch_audit(
    *,
    db_path: str | None,
    arxiv_id: str,
    document_id: str,
    source_url: str,
    pdf_bytes: bytes,
) -> None:
    """SPR-09 M4 — emit the ``arxiv.fetch`` leg at the REAL production boundary.

    This is the on-demand T1 full-text path the operator CLIs actually run
    (``ingest_paper_with_rights`` → ``ingest_servable_book``), where the arXiv PDF
    bytes are fetched and a servable T1 body is landed. The round-2 fetch-audit
    lived in ``store.store_pdf_for_arxiv_row``, which has ZERO production callers
    (tests only) — so ``trace(con, arxiv_id)`` never showed a fetch leg in
    production and the "full fetch→serve→accrue trace" criterion was UNMET. This
    is the production wiring.

    Defensively isolated: a failure here must NEVER break the fetch / ingest, so
    the whole body is wrapped + logged (exactly like the serve leg in
    ``interfaces/research/api/books.py`` and the accrue leg in
    ``book_escrow.py``). The audit takes its OWN write lock (the ingest's own
    locks are already closed by the time we get the servable result back). §9.0:
    provenance refs ONLY (source_url / sha256 / byte_size) — never the body."""
    try:
        from runtime.db_lock import connect_write
        from substrate.audit.arxiv_audit import ARXIV_FETCH, record_event
        from substrate.graph import default_db_path, ensure_initialized

        resolved = ensure_initialized(db_path or default_db_path())
        con = connect_write(resolved, purpose="arxiv_fetch_audit")
        try:
            record_event(
                con,
                arxiv_id=arxiv_id,
                document_id=document_id,
                kind=ARXIV_FETCH,
                detail={
                    "source_url": source_url,
                    "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                    "byte_size": len(pdf_bytes),
                },
            )
        finally:
            con.close()
    except Exception:
        logger.exception(
            "arxiv_audit fetch-leg failed for arxiv_id=%s; fetch/ingest unaffected",
            arxiv_id,
        )


def _record_html_fetch_audit(
    *,
    db_path: str | None,
    arxiv_id: str,
    document_id: str,
    fetched: FetchedHtml,
) -> None:
    """SPR-09 M4 — emit the ``arxiv.fetch`` leg for an HTML-first ingest.

    Same defensive isolation as :func:`_record_fetch_audit`: a failure here
    must never break the fetch / ingest.  ``§9.0``: provenance refs only —
    source_url, sha256, byte_size — never the body.
    """
    try:
        from runtime.db_lock import connect_write
        from substrate.audit.arxiv_audit import ARXIV_FETCH, record_event
        from substrate.graph import default_db_path, ensure_initialized

        resolved = ensure_initialized(db_path or default_db_path())
        con = connect_write(resolved, purpose="arxiv_html_fetch_audit")
        try:
            record_event(
                con,
                arxiv_id=arxiv_id,
                document_id=document_id,
                kind=ARXIV_FETCH,
                detail={
                    "source_url": fetched.source_url,
                    "sha256": fetched.sha256,
                    "byte_size": fetched.byte_size,
                    "format": "html",
                },
            )
        finally:
            con.close()
    except Exception:
        logger.exception(
            "arxiv_audit html-fetch-leg failed for arxiv_id=%s; fetch/ingest unaffected",
            arxiv_id,
        )


def _ingest_html_with_rights(
    paper: ArxivPaper,
    *,
    fetched_html: FetchedHtml,
    investigation_id: str,
    resolution: LicenseResolution,
    basis: str,
    source_tier: int,
    db_path: str | None,
    embedder: EmbeddingProvider | None,
) -> IngestPaperWithRightsResult:
    """Store sanitized arXiv HTML through the trusted sanitizer + register rights.

    This is the HTML-first counterpart of the PDF ``ingest_servable_book``
    path.  The HTML body is sanitized via ``sanitize_book_html`` (the same
    allowlist parser the books lane uses) and the sanitizer provenance is
    stamped into ``documents.metadata`` at the SAME write — the
    version-provenance contract that gates ``content_format="html"`` on the
    serve side.

    The document id is ``arxiv_doc_id(paper.arxiv_id)`` (content-stable,
    dedup-safe) — NOT a hash of the HTML bytes, because the same paper's
    HTML rendering can change across arXiv versions while the paper identity
    stays the same.
    """
    from substrate.books.html_sanitizer import (
        sanitize_book_html,
        sanitized_html_provenance,
    )
    from substrate.books.ingest import register_book

    sanitized = sanitize_book_html(fetched_html.html)
    provenance_bits = sanitized_html_provenance()

    document_id = arxiv_doc_id(paper.arxiv_id)

    chash = "sha256:" + content_hash(sanitized)
    payload = DocumentLoadedPayload(
        media_type="html",
        content_hash=chash,
        size_bytes=len(sanitized.encode("utf-8")),
        title=paper.title,
        page_count=None,
        source_uri=paper.abs_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/arxiv",
    )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    emb = embedder or default_embedding_provider()
    chunks: list[Chunk] = chunk_markdown(sanitized)

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/arxiv") as con:
        # Merge sanitizer provenance into the document metadata so the
        # serve-side ``is_trusted_sanitized`` gate recognizes this body as
        # safe-to-render-as-HTML.  The metadata also carries arxiv-specific
        # provenance for the fetch audit trail.
        doc_metadata: dict[str, object] = {
            "arxiv_id": paper.arxiv_id,
            "version": paper.version,
            "categories": list(paper.categories),
            "primary_category": paper.primary_category,
            "updated_at": paper.updated_at.isoformat(),
            "pdf_url": paper.pdf_url,
            "html_source_url": fetched_html.source_url,
            "html_sha256": fetched_html.sha256,
        }
        doc_metadata.update(provenance_bits)

        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="academic_paper",
            source_uri=paper.abs_url,
            title=paper.title,
            author=", ".join(paper.authors) if paper.authors else None,
            published_at=paper.published_at,
            investigation_id=investigation_id,
            raw_text=sanitized,
            metadata=doc_metadata,
            on_conflict="ignore",
        )
        register_source_document(
            con,
            document_id=document_id,
            source_kind=SourceKind.ACADEMIC_PREPRINT,
        )

        chunk_ids: list[str] = []
        node_ids: list[str] = []
        for i, chunk in enumerate(chunks):
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(chunk_id)

            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{paper.arxiv_id}#{i}"

            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "arxiv",
                    "arxiv_id": paper.arxiv_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

        # Register the document as a servable book so the rights/servability
        # machinery (deny-by-default, content_class) applies identically to
        # the HTML path and the PDF path.
        asset = register_book(
            con,
            document_id=document_id,
            content_class=resolution.content_class,
            toc=[],
            page_count=0,
            cover_uri=None,
            provenance=fetched_html.source_url,
            license_basis=basis,
        )

    return IngestPaperWithRightsResult(
        document_id=document_id,
        content_class=resolution.content_class,
        redistributable=resolution.redistributable,
        servability=asset.servability.value,
        servable_full_text=asset.servable_full_text,
        license_uri=paper.license_uri,
        license_basis=basis,
    )


def ingest_paper_with_rights(
    paper: ArxivPaper,
    *,
    investigation_id: str,
    pdf_bytes: bytes | None = None,
    fetch_pdf: PdfFetcher | None = None,
    fetch_html: HtmlFetcher | None = None,
    prefer_html: bool = False,
    source_tier: int = DEFAULT_ARXIV_FULLTEXT_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> IngestPaperWithRightsResult:
    """Ingest a paper's FULL TEXT through the shared servable-book path,
    gated on the paper's declared license.

    The rights flow:

      1. Resolve ``paper.license_uri`` via ``acquisition.arxiv.licenses``.
         CC-BY / CC-BY-SA -> ``source_declared_open`` and CC0 ->
         ``public_domain`` (both servable; 2026-05-29 remap — neither is a
         §9.10 publisher opt-in). arXiv default terms / NC / ND / unknown /
         missing -> gated. The unknown-fallback is deny-by-default — never
         guessed servable.
      2. Build a ``license_basis`` audit string (license name + URI for
         servable; a "why gated" string otherwise).
      3. When ``prefer_html`` is True, attempt the HTML-first path: fetch
         via ``fetch_html`` (or the default rate-governed fetcher), sanitize
         through the trusted allowlist sanitizer, and store with
         ``content_format="html"`` (provenance-stamped).  If the paper has
         no HTML rendering (``fetch_html`` returns ``None``), fall through
         to the PDF path.
      4. Otherwise (or as fallback), fetch the PDF (injected ``pdf_bytes``
         in tests; ``fetch_pdf`` or the default network fetcher in prod)
         and route through ``acquisition.books.ingest_servable_book``.

    ``pdf_bytes`` short-circuits the PDF fetch (CI passes fixture bytes so
    no network).  When omitted, ``fetch_pdf`` (default: arxiv.org/pdf) is
    used.  ``fetch_html`` is the injectable HTML fetcher (tests pass a
    stub).  ``prefer_html`` enables the HTML-first path; when False the
    function behaves exactly as before (PDF only).
    """
    from acquisition.books.adapter import ingest_servable_book

    resolution = resolve_license(paper.license_uri)
    basis = license_basis_string(resolution)

    # --- HTML-first path (new) ---
    if prefer_html:
        html_fetcher = fetch_html or _default_fetch_html
        fetched = html_fetcher(paper.arxiv_id)
        if fetched is not None:
            result = _ingest_html_with_rights(
                paper,
                fetched_html=fetched,
                investigation_id=investigation_id,
                resolution=resolution,
                basis=basis,
                source_tier=source_tier,
                db_path=db_path,
                embedder=embedder,
            )
            # Record the HTML fetch audit — same defensive pattern as the
            # PDF leg below.  Only for servable bodies (§9.0).
            if result.servable_full_text:
                _record_html_fetch_audit(
                    db_path=db_path,
                    arxiv_id=paper.arxiv_id,
                    document_id=result.document_id,
                    fetched=fetched,
                )
            return result

    # --- PDF fallback path (unchanged) ---
    if pdf_bytes is None:
        fetcher = fetch_pdf or _default_fetch_pdf
        pdf_bytes = fetcher(paper.arxiv_id)
    if not pdf_bytes:
        # An empty PDF would land a 0-word document and silently gate it on
        # low_word_count; surface the fetch failure instead of ingesting a
        # husk that looks like a rights decision.
        raise ValueError(
            f"empty PDF bytes for {paper.arxiv_id} — fetch failed or paper "
            "has no PDF"
        )

    # Distinct name from the early-return HTML path's ``result``
    # (IngestPaperWithRightsResult) — this is an IngestServableBookResult, so
    # reusing the name would be a mypy assignment conflict.
    book_result = ingest_servable_book(
        pdf_bytes,
        investigation_id=investigation_id,
        # None content_class would deny-by-default in ingest_servable_book,
        # but we pass the resolved class explicitly so the gated case is an
        # auditable decision (basis names the license) rather than a silent
        # omission.
        content_class=resolution.content_class,
        license_basis=basis,
        source_uri=paper.abs_url,
        source_tier=int(source_tier),
        provenance=paper.pdf_url,
        db_path=db_path,
        embedder=embedder,
    )

    # SPR-09 M4 — emit the FETCH leg of the compliance trace at the REAL
    # production boundary. The arXiv PDF bytes were just fetched and a body was
    # landed; we record the fetch leg ONLY when the body is genuinely servable
    # (a T1/redistributable store) so the fetch leg tracks a stored T1 body, not a
    # gated attempt — mirroring the store path's "refused → no fetch leg" guard.
    # Defensively isolated so a hook failure can never break the fetch/ingest;
    # §9.0 records provenance refs only.
    if book_result.servable_full_text:
        _record_fetch_audit(
            db_path=db_path,
            arxiv_id=paper.arxiv_id,
            document_id=book_result.document_id,
            source_url=paper.pdf_url,
            pdf_bytes=pdf_bytes,
        )

    return IngestPaperWithRightsResult(
        document_id=book_result.document_id,
        content_class=resolution.content_class,
        redistributable=resolution.redistributable,
        servability=book_result.servability,
        servable_full_text=book_result.servable_full_text,
        license_uri=paper.license_uri,
        license_basis=basis,
    )

"""Universal-library ingestion pipeline (M7).

After content-type detection + extraction, every URL — regardless of
type — ends in this pipeline. We write one ``documents`` row, run the
existing chunker against the extracted text + synthesized pages,
embed each chunk, and write per-chunk nodes via the existing
``substrate/graph/ops``. The edge-builder runs as today (each chunk
gets its node, the cross-doc linker mints edges later in the loop).

Transactional ingest: every write for a given document happens inside
a single ``connect_write`` context. A failure mid-pipeline raises;
nothing partial commits. The job log update lives in its own write
context so failure reporting itself is robust.

Idempotency: doc id is content-stable (see ``_doc_id_for``). Repeat
ingests of the same URL no-op on the graph rows; the
``document.loaded`` event still fires (append-only trajectory).
"""

from __future__ import annotations

import hashlib
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.ingestion import content_type as ct
from services.ingestion import fetcher as fetcher_mod
from services.ingestion import jobs as jobs_mod
from services.ingestion.extractors import (  # noqa: E402
    arxiv as arxiv_extractor,
    epub as epub_extractor,
    html_article as html_extractor,
    pdf as pdf_extractor,
)


# ---------------------------------------------------------------------------
# ExtractedDocument — the uniform envelope each extractor maps to
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedDocument:
    """What the pipeline gets after extraction, regardless of source."""

    source_url: str          # what the caller asked for
    final_url: str           # post-redirect canonical URL
    content_type: str        # pdf | html_article | epub | arxiv
    document_type: str       # documents.document_type value
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[datetime]
    text: str                # full text or markdown — what the chunker eats
    pages: Optional[list[str]] = None  # per-page text for PDF/EPUB; None otherwise
    paywalled: bool = False
    ocr_required: bool = False
    metadata: dict = field(default_factory=dict)
    # 2026-05-22: PDFs carry through the full PdfExtraction so the
    # page-tagging chunker (processing/chunking/pdf_chunker.py) can
    # stamp page+bbox onto every chunk. None for non-PDF formats.
    pdf_extraction: Optional[object] = None
    # 2026-05-22: raw source bytes if the fetcher had them. The
    # pipeline routes these through services/library/raw_bytes_store
    # and stamps documents.raw_bytes_path. None when the source was
    # extracted from an already-text format (e.g., pasted markdown).
    raw_bytes: Optional[bytes] = None
    raw_bytes_ext: Optional[str] = None


@dataclass(frozen=True)
class IngestResult:
    """What the pipeline returns to the API/CLI caller."""

    job_id: str
    document_id: Optional[str]
    status: str           # "succeeded" | "failed" | "skipped"
    error: Optional[str] = None
    content_type: Optional[str] = None
    paywalled: bool = False
    via_cache: bool = False


# ---------------------------------------------------------------------------
# Stable document id
# ---------------------------------------------------------------------------


def _doc_id_for(content_type_label: str, canonical_key: str) -> str:
    """Compose a stable doc id. arXiv keeps its existing
    ``doc-arxiv-<id>`` shape (compat with prior ingests); other types
    use a sha256-truncated hash so the id is stable across sessions."""
    if content_type_label == ct.ARXIV:
        # Caller passes the arxiv_id as canonical_key; reuse the
        # existing sanitizer from the adapter.
        from acquisition.arxiv.adapter import arxiv_doc_id
        return arxiv_doc_id(canonical_key)
    h = hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()[:16]
    if content_type_label == ct.PDF:
        return f"doc-pdf-{h}"
    if content_type_label == ct.EPUB:
        return f"doc-epub-{h}"
    return f"doc-url-{h}"


# ---------------------------------------------------------------------------
# Extraction dispatch
# ---------------------------------------------------------------------------


def _extract_arxiv(
    url: str,
    *,
    client: Optional[httpx.Client],
    db_path: Optional[str],
) -> ExtractedDocument:
    extraction = arxiv_extractor.extract_arxiv(url, client=client, db_path=db_path)
    text = arxiv_extractor.format_as_markdown(extraction)
    return ExtractedDocument(
        source_url=url,
        final_url=extraction.abs_url,
        content_type=ct.ARXIV,
        document_type="academic_paper",
        title=extraction.title,
        author=", ".join(extraction.authors) if extraction.authors else None,
        published_at=extraction.published_at,
        text=text,
        metadata={
            "arxiv_id": extraction.arxiv_id,
            "version": extraction.version,
            "categories": extraction.categories,
            "primary_category": extraction.primary_category,
            "pdf_url": extraction.pdf_url,
        },
    )


def _extract_html(
    url: str,
    *,
    fetched: fetcher_mod.FetchResult,
) -> ExtractedDocument:
    extraction = html_extractor.extract_html(
        html_body=fetched.body, final_url=fetched.final_url,
    )
    return ExtractedDocument(
        source_url=url,
        final_url=fetched.final_url,
        content_type=ct.HTML_ARTICLE,
        document_type="web_article",
        title=extraction.title,
        author=extraction.byline,
        published_at=extraction.published_at,
        text=extraction.content_text,
        paywalled=extraction.paywalled,
        metadata={
            "word_count": extraction.word_count,
            "content_type_header": fetched.content_type,
            "status_code": fetched.status_code,
        },
        raw_bytes=fetched.body,
        raw_bytes_ext="html",
    )


def _extract_pdf(
    url: str,
    *,
    fetched: fetcher_mod.FetchResult,
) -> ExtractedDocument:
    extraction = pdf_extractor.extract_pdf(pdf_bytes=fetched.body)
    pages = [p.text for p in extraction.pages]
    md_text = "\n\n".join(
        f"## Page {p.page_index}\n\n{p.text}" for p in extraction.pages if p.text
    ) or extraction.text
    return ExtractedDocument(
        source_url=url,
        final_url=fetched.final_url,
        content_type=ct.PDF,
        document_type="pdf",
        title=extraction.title,
        author=extraction.author,
        published_at=None,
        text=md_text,
        pages=pages,
        ocr_required=extraction.ocr_required,
        metadata={
            "page_count": len(extraction.pages),
            "word_count": extraction.word_count,
        },
        # PDF extraction is preserved so the chunker can stamp
        # page+bbox geometry per-chunk (added 2026-05-22).
        pdf_extraction=extraction,
        # The raw PDF bytes also ride through so the pipeline can
        # store them in the content-addressed raw-bytes store and
        # populate documents.raw_bytes_path.
        raw_bytes=fetched.body,
        raw_bytes_ext="pdf",
    )


def _extract_epub(
    url: str,
    *,
    fetched: fetcher_mod.FetchResult,
) -> ExtractedDocument:
    extraction = epub_extractor.extract_epub(epub_bytes=fetched.body)
    pages = [p.text for p in extraction.pages]
    md_text_parts = ["# " + (extraction.title or "Untitled EPUB"), ""]
    if extraction.author:
        md_text_parts.append(f"_by {extraction.author}_")
        md_text_parts.append("")
    last_chapter = -1
    for p in extraction.pages:
        if p.chapter_index != last_chapter:
            md_text_parts.append(f"## {p.chapter_title or f'Chapter {p.chapter_index + 1}'}")
            md_text_parts.append("")
            last_chapter = p.chapter_index
        md_text_parts.append(p.text)
        md_text_parts.append("")
    md_text = "\n".join(md_text_parts).strip()
    return ExtractedDocument(
        source_url=url,
        final_url=fetched.final_url,
        content_type=ct.EPUB,
        document_type="ebook",
        title=extraction.title,
        author=extraction.author,
        published_at=extraction.published_at,
        text=md_text,
        pages=pages,
        metadata={
            "page_count": len(extraction.pages),
            "chapter_count": len(extraction.chapters),
            "chapters": extraction.chapters,
            "language": extraction.language,
        },
        raw_bytes=fetched.body,
        raw_bytes_ext="epub",
    )


# ---------------------------------------------------------------------------
# Pipeline write — the substrate-touching side
# ---------------------------------------------------------------------------


def _write_to_substrate(
    *,
    doc: ExtractedDocument,
    document_id: str,
    investigation_id: str,
    user_id: str,
    source_tier: int,
    db_path: Optional[str],
    embedder: object = None,
) -> tuple[str, int]:
    """Write the documents/chunks/nodes rows + emit document.loaded.

    Returns (document_loaded_event_id, chunks_written). All writes
    happen inside one ``connect_write`` — transactional per the spec.
    """
    from processing.chunking.chunker import Chunk, chunk_markdown, content_hash
    from processing.embedding.embed import default_embedding_provider
    from runtime.db_lock import connect_write
    from substrate.event_log import emit_typed
    from substrate.graph import default_db_path, ensure_initialized
    from substrate.graph.ops import insert_chunk, insert_document, insert_node
    from substrate.schemas import DocumentLoadedPayload

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    text = doc.text
    chash = "sha256:" + content_hash(text)

    # Map content_type to the typed DocumentLoadedPayload media_type.
    # The schema's literal set is {pdf, pasted_text, url_extracted,
    # markdown} (substrate.schemas.events.DocumentLoadedPayload). EPUB
    # maps to ``markdown`` because we serialize the EPUB body to
    # markdown for the chunker; the original content_type ("epub")
    # rides in document.metadata so consumers can still discriminate.
    media_type_map = {
        ct.PDF: "pdf",
        ct.HTML_ARTICLE: "url_extracted",
        ct.EPUB: "markdown",
        ct.ARXIV: "markdown",
    }
    media_type = media_type_map.get(doc.content_type, "url_extracted")

    payload = DocumentLoadedPayload(
        media_type=media_type,
        content_hash=chash,
        size_bytes=len(text.encode("utf-8")),
        title=doc.title,
        page_count=len(doc.pages) if doc.pages else None,
        source_uri=doc.final_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id=f"services/ingestion/{doc.content_type}",
    )

    # PDF content gets routed through the page-tagging chunker decorator
    # so chunks land with chunks.page + chunks.bbox populated (SPR-02
    # voice anchor + SPR-07 gutter cite-jump both depend on this). Non-PDF
    # content still uses chunk_markdown — those formats don't have a
    # native page concept, so page=None / bbox=None is honest.
    page_tagged: list = []
    chunks: list[Chunk] = []
    if doc.content_type == ct.PDF and doc.pdf_extraction is not None:
        from processing.chunking.pdf_chunker import chunk_pdf_extraction
        page_tagged = chunk_pdf_extraction(doc.pdf_extraction)
        chunks = [pt.chunk for pt in page_tagged]
    else:
        chunks = chunk_markdown(text)
    chunks_written = 0
    emb = embedder if embedder is not None else default_embedding_provider()

    meta = dict(doc.metadata)
    meta.update({
        "source_url": doc.source_url,
        "final_url": doc.final_url,
        "content_type": doc.content_type,
        "paywalled": doc.paywalled,
        "ocr_required": doc.ocr_required,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    })

    # Stash raw bytes in the content-addressed store and capture the
    # path for insert_document. Skip when no bytes were captured (e.g.,
    # pasted-text formats) or when the format produced empty body.
    raw_bytes_path: Optional[str] = None
    if doc.raw_bytes:
        from services.library.raw_bytes_store import store_bytes
        try:
            raw_bytes_path, _sha = store_bytes(
                doc.raw_bytes,
                ext=doc.raw_bytes_ext or "bin",
            )
            meta["raw_bytes_sha256"] = _sha
        except Exception as exc:  # noqa: BLE001
            # Bytes store failure (disk full, permission, etc.) must
            # not block the ingest — the rest of the substrate write
            # still succeeds with raw_bytes_path = None, and a future
            # backfill can re-store.
            meta["raw_bytes_store_error"] = str(exc)

    with connect_write(resolved_db_path, purpose=f"ingestion/{doc.content_type}") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type=doc.document_type,
            source_uri=doc.final_url,
            title=doc.title,
            author=doc.author,
            published_at=doc.published_at,
            investigation_id=investigation_id,
            raw_text=text,
            metadata=meta,
            on_conflict="ignore",
            raw_bytes_path=raw_bytes_path,
        )
        for i, chunk in enumerate(chunks):
            # When we routed through chunk_pdf_extraction above, the
            # per-chunk geometry rides alongside in ``page_tagged``.
            page: Optional[int] = None
            bbox: Optional[dict] = None
            if page_tagged:
                pt = page_tagged[i]
                page = pt.page
                bbox = pt.bbox
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
                page=page,
                bbox=bbox,
            )
            chunks_written += 1
            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > 160:
                label = label[:159] + "…"
            if not label:
                label = f"{document_id}#{i}"
            insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": doc.content_type,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )

    return (event_id or "", chunks_written)


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------


# Source tier defaults per content type. Tiers: 1 peer-reviewed
# primary → 5 uncited social. arXiv preprints = 3; PDFs and EPUBs we
# trust by default (operator-imported, user-owned) → 2; HTML articles
# default to 4 (general web).
_DEFAULT_TIERS = {
    ct.ARXIV: 3,
    ct.PDF: 2,
    ct.EPUB: 2,
    ct.HTML_ARTICLE: 4,
}


# Default source-tier-by-class for the spec's "low word count" gate.
MIN_INGEST_WORD_COUNT = 50


def ingest(
    *,
    url: str,
    user_id: str,
    investigation_id: str = "__operator__",
    job_id: Optional[str] = None,
    db_path: Optional[str] = None,
    source_tier_override: Optional[int] = None,
    client: Optional[httpx.Client] = None,
    embedder: object = None,
    source_metadata: Optional[dict] = None,
    sidecar_bytes: Optional[bytes] = None,
    sidecar_url: Optional[str] = None,
) -> IngestResult:
    """Run the full pipeline for one URL.

    The API and the CLI both call this. The job_id is optional: when
    set, status updates write back to that row; when None, a fresh
    job is created and the row is returned via the result.

    Returns IngestResult — never raises for normal ingestion failures
    (they go into the job's error column). Configuration errors
    (missing DB, bad params) still raise; those mean the caller is
    holding it wrong.
    """
    # 1. Job book-keeping
    resolved_job_id: str
    if job_id is None:
        job = jobs_mod.create_job(
            url=url, user_id=user_id,
            investigation_id=investigation_id,
            metadata=source_metadata,
            db_path=db_path,
        )
        resolved_job_id = job.job_id
    else:
        resolved_job_id = job_id

    jobs_mod.update_status(
        resolved_job_id, status="running",
        bump_attempts=True, db_path=db_path,
    )

    # 2. Content-type detection
    try:
        detection = ct.detect(url, client=client)
        jobs_mod.update_status(
            resolved_job_id, status="running",
            content_type=detection.content_type, db_path=db_path,
            metadata_patch={"detection_via": detection.via},
        )
    except Exception as exc:  # noqa: BLE001
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error="content_type_detection_failed",
            error_detail=repr(exc), db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error="content_type_detection_failed",
        )

    # 3. Extraction (per content type)
    try:
        if detection.content_type == ct.ARXIV:
            doc = _extract_arxiv(url, client=client, db_path=db_path)
            canonical_key = doc.metadata.get("arxiv_id") or doc.final_url
            via_cache = False
        else:
            fetched = fetcher_mod.fetch(
                url, client=client, db_path=db_path,
            )
            via_cache = fetched.via_cache
            if detection.content_type == ct.PDF:
                doc = _extract_pdf(url, fetched=fetched)
            elif detection.content_type == ct.EPUB:
                doc = _extract_epub(url, fetched=fetched)
            else:  # HTML_ARTICLE / UNKNOWN → html path
                doc = _extract_html(url, fetched=fetched)
            canonical_key = doc.final_url
    except fetcher_mod.DomainBanned as exc:
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error="domain_banned",
            error_detail=str(exc),
            metadata_patch={"banned_until": exc.banned_until.isoformat()},
            db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error="domain_banned",
            content_type=detection.content_type,
        )
    except fetcher_mod.RobotsDisallowed as exc:
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error="robots_disallowed", error_detail=str(exc),
            db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error="robots_disallowed",
            content_type=detection.content_type,
        )
    except httpx.HTTPStatusError as exc:
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error=f"http_{exc.response.status_code}",
            error_detail=str(exc), db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error=f"http_{exc.response.status_code}",
            content_type=detection.content_type,
        )
    except Exception as exc:  # noqa: BLE001
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error="extraction_failed",
            error_detail=f"{exc!r}\n{traceback.format_exc()}",
            db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error="extraction_failed",
            content_type=detection.content_type,
        )

    # 4. Word-count gate (avoid graph rows for misextracted content).
    if doc.metadata.get("word_count") is not None:
        word_count_ok = doc.metadata["word_count"] >= MIN_INGEST_WORD_COUNT
    else:
        word_count_ok = len(doc.text.split()) >= MIN_INGEST_WORD_COUNT

    if not word_count_ok and not doc.paywalled:
        # Skip graph writes when extraction looks empty AND we can't
        # blame the paywall. Paywalled docs are partial-success: we
        # still write what we got + the paywalled flag.
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error="low_word_count",
            error_detail=(
                f"Extracted only {doc.metadata.get('word_count', '?')} words; "
                f"below the {MIN_INGEST_WORD_COUNT}-word ingest threshold."
            ),
            db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error="low_word_count",
            content_type=detection.content_type,
        )

    # 5. Substrate write (transactional, idempotent)
    document_id = _doc_id_for(detection.content_type, canonical_key)
    try:
        source_tier = (
            source_tier_override
            if source_tier_override is not None
            else _DEFAULT_TIERS.get(detection.content_type, 4)
        )
        _write_to_substrate(
            doc=doc,
            document_id=document_id,
            investigation_id=investigation_id,
            user_id=user_id,
            source_tier=source_tier,
            db_path=db_path,
            embedder=embedder,
        )
    except Exception as exc:  # noqa: BLE001
        jobs_mod.update_status(
            resolved_job_id, status="failed",
            error="substrate_write_failed",
            error_detail=f"{exc!r}\n{traceback.format_exc()}",
            db_path=db_path,
        )
        return IngestResult(
            job_id=resolved_job_id, document_id=None,
            status="failed", error="substrate_write_failed",
            content_type=detection.content_type,
        )

    # 5b. Sidecar apply (SPR-10 / M4). MUST run after step 5 so anchors
    # can resolve against the just-built chunks (rigor #4: anchors are
    # resolved against chunks, so the pipeline-step ordering invariant
    # is anchor-apply AFTER chunk-write). We only attempt this for PDFs;
    # other content types can't carry a meaningful sidecar today.
    sidecar_outcome = None
    if (sidecar_bytes or sidecar_url) and detection.content_type == ct.PDF:
        try:
            from services.ingestion.sidecar_detector import (
                SidecarApplyOutcome,
                apply_sidecar_for_pdf_after_ingest,
                fetch_sidecar_from_url,
            )
            resolved_sidecar = sidecar_bytes
            sidecar_source_label = "zip"
            if resolved_sidecar is None and sidecar_url:
                resolved_sidecar = fetch_sidecar_from_url(sidecar_url)
                sidecar_source_label = "url"
            if resolved_sidecar is not None:
                # PDF bytes for hash check. We captured the body in step 3
                # (fetched.body for PDF path). The variable is in scope
                # via the local ``fetched`` from the elif branch.
                pdf_bytes_for_hash = fetched.body if "fetched" in locals() else b""
                from substrate.graph import default_db_path as _graph_default_db_path
                resolved_db_path = db_path or _graph_default_db_path()
                sidecar_outcome = apply_sidecar_for_pdf_after_ingest(
                    sidecar_bytes=resolved_sidecar,
                    pdf_bytes=pdf_bytes_for_hash,
                    document_id=document_id,
                    user_id=user_id,
                    db_path=resolved_db_path,
                    sidecar_source=sidecar_source_label,
                )
            else:
                sidecar_outcome = SidecarApplyOutcome(
                    detected=False,
                    error="sidecar_url_fetch_failed",
                    ui_message="Could not fetch the sidecar URL; PDF imported without annotations.",
                )
        except Exception as exc:  # noqa: BLE001
            # Sidecar apply failures must NOT fail the ingest — the PDF
            # is already in the substrate. We attach the outcome to the
            # job's metadata so the UI can show what went wrong, but
            # the ingest itself is "succeeded" because the PDF did.
            import traceback
            from services.ingestion.sidecar_detector import SidecarApplyOutcome
            sidecar_outcome = SidecarApplyOutcome(
                detected=True, applied=False,
                error=f"sidecar_apply_crashed: {exc!r}",
                ui_message="Sidecar apply crashed; PDF imported, annotations not restored.",
                warnings=[traceback.format_exc()],
            )

    # 6. Terminal success
    sidecar_metadata = sidecar_outcome.to_dict() if sidecar_outcome is not None else None
    jobs_mod.update_status(
        resolved_job_id, status="succeeded",
        document_id=document_id,
        metadata_patch={
            "title": doc.title,
            "paywalled": doc.paywalled,
            "via_cache": via_cache,
            "sidecar": sidecar_metadata,
        },
        db_path=db_path,
    )
    return IngestResult(
        job_id=resolved_job_id, document_id=document_id,
        status="succeeded", content_type=detection.content_type,
        paywalled=doc.paywalled, via_cache=via_cache,
    )

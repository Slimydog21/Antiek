"""PDF → Antiek substrate adapter.

Reads a PDF (from bytes or path), emits ``document.loaded``, writes
to ``substrate.graph``. Mirrors the ``acquisition.urls.adapter``
contract — same return shape, same idempotency guarantees.

Stable doc id: ``doc-book-<sha256-of-bytes[:16]>`` for byte inputs;
``doc-book-<sha256-of-resolved-path[:16]>`` for path inputs. Both
keep ids bounded + DuckDB-safe. Re-ingesting the same PDF dedups
on the doc id.

Default source tier: 2 (books are higher signal than general web).
Caller can override per-call.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Union

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
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

from .reader import ReadResult, read_pdf

DEFAULT_BOOK_SOURCE_TIER = 2
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 100  # books that extract to fewer words are usually scans

PdfSource = Union[bytes, str]


# ---------------------------------------------------------------------------
# Stable document id
# ---------------------------------------------------------------------------


def book_doc_id(source: PdfSource) -> str:
    """Stable Antiek doc id. For bytes, hash the content; for paths,
    hash the absolute path (so the same file at the same location
    keeps the same id even if you ingest it twice)."""
    if isinstance(source, bytes):
        if not source:
            raise ValueError("empty pdf bytes")
        h = hashlib.sha256(source).hexdigest()[:16]
    elif isinstance(source, str):
        if not source.strip():
            raise ValueError("empty path")
        abs_path = os.path.abspath(source)
        h = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:16]
    else:
        raise TypeError(f"unsupported pdf source type: {type(source).__name__}")
    return f"doc-book-{h}"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestBookResult:
    """What ``ingest_pdf`` returns."""

    document_id: str
    chunk_ids: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    page_count: int = 0
    word_count: int = 0
    skipped_reason: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    # Flattened bookmark outline from the PDF (Read SPR-01). Carried on
    # the result so the servable-book orchestrator doesn't re-read the PDF
    # just to recover the TOC.
    toc: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _load_bytes(source: PdfSource) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        with open(source, "rb") as f:
            return f.read()
    raise TypeError(f"unsupported pdf source type: {type(source).__name__}")


def ingest_pdf(
    source: PdfSource,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_BOOK_SOURCE_TIER,
    source_uri: Optional[str] = None,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
    promote_headings: bool = True,
) -> IngestBookResult:
    """Read ``source`` (bytes or path), ingest into the substrate.

    ``source_uri`` is the public URL or stable identifier callers
    want stamped onto the document row (e.g. an arXiv pdf URL when
    ingesting a fetched copy). Defaults to the absolute path for
    file-source inputs, ``None`` for byte inputs.
    """
    pdf_bytes = _load_bytes(source)
    result: ReadResult = read_pdf(pdf_bytes, promote_headings=promote_headings)
    document_id = book_doc_id(source)

    if source_uri is None and isinstance(source, str):
        source_uri = os.path.abspath(source)

    text = result.markdown
    chash = "sha256:" + content_hash(text) if text else "sha256:" + content_hash("")

    payload = DocumentLoadedPayload(
        media_type="pdf",
        content_hash=chash,
        size_bytes=len(pdf_bytes),
        title=result.title,
        page_count=result.page_count,
        source_uri=source_uri,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/books",
    )

    if result.word_count < min_word_count:
        return IngestBookResult(
            document_id=document_id,
            document_loaded_event_id=event_id,
            page_count=result.page_count,
            word_count=result.word_count,
            skipped_reason="low_word_count",
            title=result.title,
            author=result.author,
            toc=list(result.toc),
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: List[Chunk] = chunk_markdown(text)
    chunk_ids: List[str] = []
    node_ids: List[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/books") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="book",
            source_uri=source_uri,
            title=result.title,
            author=result.author,
            published_at=None,
            investigation_id=investigation_id,
            raw_text=text,
            metadata={
                "page_count": result.page_count,
                "word_count": result.word_count,
                "source_kind": (
                    "bytes" if isinstance(source, bytes) else "path"
                ),
            },
            on_conflict="ignore",
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
                label = f"{document_id}#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "book",
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestBookResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        page_count=result.page_count,
        word_count=result.word_count,
        title=result.title,
        author=result.author,
        toc=list(result.toc),
    )


# ---------------------------------------------------------------------------
# Servable-book orchestrator (Read SPR-01)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestServableBookResult:
    """What ``ingest_servable_book`` returns: the underlying ingest result
    plus the resolved servability. ``servable_full_text`` is the derived
    answer to "may we serve this book's full text" — deny-by-default, so a
    book ingested with no explicit license comes back False."""

    ingest: IngestBookResult
    document_id: str
    servability: str
    servable_full_text: bool


def ingest_servable_book(
    source: PdfSource,
    *,
    investigation_id: str,
    content_class: Optional[str] = None,
    rights_holder_name: Optional[str] = None,
    ip_holder_id: Optional[str] = None,
    provenance: Optional[str] = None,
    license_basis: Optional[str] = None,
    source_tier: int = DEFAULT_BOOK_SOURCE_TIER,
    source_uri: Optional[str] = None,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
) -> IngestServableBookResult:
    """Read a PDF, ingest it as a document, and register it as a
    Read-workflow book under the servable-corpus gate.

    This is the one-call "drop a book in" path. It lives in the
    acquisition layer (not substrate) because it reads PDFs and inserts
    documents; the legal-gate registration is delegated to
    ``substrate.books.ingest.register_book`` so the deny-by-default
    classification has exactly one home.

    Pass ``content_class`` only when a license is established
    (``public_domain``, ``source_declared_open``, ``opt_in_licensed``,
    ``user_owned``). Omit it for anything aggregated with unknown rights — it
    lands gated.
    """
    # substrate is a lower layer than acquisition; importing it here keeps
    # the dependency arrow pointing the right way (acquisition → substrate).
    from runtime.db_lock import connect_write
    from substrate.books.ingest import register_book
    from substrate.books.model import TocItem
    from substrate.graph import default_db_path, ensure_initialized

    ingest_result = ingest_pdf(
        source,
        investigation_id=investigation_id,
        source_tier=source_tier,
        source_uri=source_uri,
        db_path=db_path,
        embedder=embedder,
    )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    toc_items = [
        TocItem(title=t.title, page_index=t.page_index, level=t.level)
        for t in ingest_result.toc
    ]
    with connect_write(resolved_db_path, purpose="read/books/ingest") as con:
        asset = register_book(
            con,
            document_id=ingest_result.document_id,
            content_class=content_class,
            rights_holder_name=rights_holder_name,
            ip_holder_id=ip_holder_id,
            toc=toc_items,
            page_count=ingest_result.page_count,
            cover_uri=None,
            provenance=provenance or (source_uri if isinstance(source, str) else "bytes"),
            license_basis=license_basis,
        )

    return IngestServableBookResult(
        ingest=ingest_result,
        document_id=asset.document_id,
        servability=asset.servability.value,
        servable_full_text=asset.servable_full_text,
    )

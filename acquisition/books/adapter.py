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
import json
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

# Repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
from substrate.books.servability import servability_of  # noqa: E402
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

from .reader import ReadResult, TocEntry, read_pdf  # noqa: E402

DEFAULT_BOOK_SOURCE_TIER = 2
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 100  # books that extract to fewer words are usually scans

PdfSource = bytes | str


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
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    page_count: int = 0
    word_count: int = 0
    skipped_reason: str | None = None
    title: str | None = None
    author: str | None = None
    reader_snapshot_path: str | None = None
    # Flattened bookmark outline from the PDF (Read SPR-01). Carried on
    # the result so the servable-book orchestrator doesn't re-read the PDF
    # just to recover the TOC.
    toc: list[TocEntry] = field(default_factory=list)


def _write_book_projection(
    *,
    document_id: str,
    source_uri: str | None,
    markdown: str,
    canonical_content_hash: str,
    source_event_id: str,
    title: str | None,
    author: str | None,
    ip_holder_id: str | None = None,
    content_class: str | None = None,
    servability: str = "gated_metadata_only",
    owner_scope: str = "__operator__",
    viewable: bool,
    non_viewable_reason: str | None = None,
) -> str:
    from acquisition.snapshot.reader_html import (
        build_reader_snapshot,
        markdown_to_safe_html,
        reader_snapshot_path_for,
        write_reader_snapshot,
    )

    path = reader_snapshot_path_for(document_id)
    rendered = build_reader_snapshot(
        source_url=source_uri or f"book:{document_id}",
        document_id=document_id,
        ip_holder_id=ip_holder_id,
        main_html=markdown_to_safe_html(markdown),
        ingested_at=datetime.now(UTC).isoformat(),
        title=title,
        author=author,
        source_kind="book",
        canonical_content_hash=canonical_content_hash,
        source_event_id=source_event_id,
        content_class=content_class,
        servability=servability,
        owner_scope=owner_scope,
        viewable=viewable,
        non_viewable_reason=non_viewable_reason,
    )
    write_reader_snapshot(path, rendered)
    return str(path)


def _mark_book_projection_ready(*, db_path: str, document_id: str, snapshot_path: str) -> None:
    from runtime.db_lock import connect_write

    projection_hash = "sha256:" + hashlib.sha256(Path(snapshot_path).read_bytes()).hexdigest()
    with connect_write(db_path, purpose="acquisition/books/projection-ready") as con:
        row = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
        if row is None:
            return
        metadata = json.loads(row[0]) if row[0] else {}
        metadata["reader_projection_state"] = "ready"
        metadata["reader_projection_hash"] = projection_hash
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [json.dumps(metadata), document_id],
        )


def _resolve_existing_book(
    *, document_id: str, db_path: str, attempted_hash: str
) -> IngestBookResult | None:
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            """SELECT d.raw_text, d.source_uri, d.title, d.author, d.metadata,
                      d.content_class, d.ip_holder_id, d.owner_user_id,
                      coalesce(b.taken_down, false), coalesce(b.page_count, 0),
                      b.toc_json
               FROM documents d
               LEFT JOIN book_assets b ON b.document_id = d.document_id
               WHERE d.document_id = ?""",
            [document_id],
        ).fetchone()
        if row is None:
            return None
        chunk_ids = [
            str(item[0])
            for item in con.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                [document_id],
            ).fetchall()
        ]
    finally:
        con.close()
    (
        markdown,
        source_uri,
        title,
        author,
        raw_metadata,
        content_class,
        ip_holder_id,
        owner_scope,
        taken_down,
        page_count,
        raw_toc,
    ) = row
    metadata = json.loads(raw_metadata) if raw_metadata else {}
    stored_hash = str(
        metadata.get("canonical_content_hash") or "sha256:" + content_hash(str(markdown or ""))
    )
    status = servability_of(content_class, taken_down=bool(taken_down)).value
    viewable = status not in {"gated_metadata_only", "taken_down"}
    snapshot_path = _write_book_projection(
        document_id=document_id,
        source_uri=str(source_uri) if source_uri else None,
        markdown=str(markdown or ""),
        canonical_content_hash=stored_hash,
        source_event_id=str(metadata.get("source_event_id") or "legacy:book-projection-repair"),
        title=str(title) if title else None,
        author=str(author) if author else None,
        ip_holder_id=str(ip_holder_id) if ip_holder_id else None,
        content_class=str(content_class) if content_class else None,
        servability=status,
        owner_scope=str(owner_scope),
        viewable=viewable,
        non_viewable_reason=None if viewable else f"servability:{status}",
    )
    _mark_book_projection_ready(
        db_path=db_path, document_id=document_id, snapshot_path=snapshot_path
    )
    return IngestBookResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        chunks_written=0,
        page_count=int(page_count),
        word_count=int(metadata.get("word_count") or 0),
        skipped_reason=(
            None if stored_hash == attempted_hash else "changed_content_requires_replace"
        ),
        title=str(title) if title else None,
        author=str(author) if author else None,
        reader_snapshot_path=snapshot_path,
        toc=[
            TocEntry(
                title=str(item.get("title") or ""),
                page_index=item.get("page_index"),
                level=int(item.get("level") or 0),
            )
            for item in (json.loads(raw_toc) if raw_toc else [])
        ],
    )


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
    source_uri: str | None = None,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
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
    assert event_id is not None

    if result.word_count < min_word_count:
        reader_snapshot_path = _write_book_projection(
            document_id=document_id,
            source_uri=source_uri,
            markdown=text,
            canonical_content_hash=chash,
            source_event_id=event_id,
            title=result.title,
            author=result.author,
            viewable=False,
            non_viewable_reason="low_word_count",
        )
        return IngestBookResult(
            document_id=document_id,
            document_loaded_event_id=event_id,
            page_count=result.page_count,
            word_count=result.word_count,
            skipped_reason="low_word_count",
            title=result.title,
            author=result.author,
            reader_snapshot_path=reader_snapshot_path,
            toc=list(result.toc),
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)
    existing = _resolve_existing_book(
        document_id=document_id,
        db_path=resolved_db_path,
        attempted_hash=chash,
    )
    if existing is not None:
        return replace(existing, document_loaded_event_id=event_id)

    chunks: list[Chunk] = chunk_markdown(text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
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
                "canonical_content_hash": chash,
                "source_event_id": event_id,
                "projection_version": "reader-html-allowlist-v1",
                "reader_projection_state": "pending",
                "reader_projection_hash": None,
                "source_kind": ("bytes" if isinstance(source, bytes) else "path"),
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

    reader_snapshot_path = _write_book_projection(
        document_id=document_id,
        source_uri=source_uri,
        markdown=text,
        canonical_content_hash=chash,
        source_event_id=event_id,
        title=result.title,
        author=result.author,
        viewable=False,
        non_viewable_reason="rights_unresolved",
    )
    _mark_book_projection_ready(
        db_path=resolved_db_path,
        document_id=document_id,
        snapshot_path=reader_snapshot_path,
    )

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
        reader_snapshot_path=reader_snapshot_path,
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
    content_class: str | None = None,
    rights_holder_name: str | None = None,
    ip_holder_id: str | None = None,
    provenance: str | None = None,
    license_basis: str | None = None,
    source_tier: int = DEFAULT_BOOK_SOURCE_TIER,
    source_uri: str | None = None,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
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

    ``min_word_count`` is the floor below which ``ingest_pdf`` treats the
    document as a failed extraction (a scanned/empty book) and returns early
    WITHOUT writing a documents row. The default (100) is the full-book scan
    heuristic; the gated metadata-only paper path passes a low floor because a
    gated record's body is deliberately just its abstract — a short body there
    is correct, not a failed extraction. If ``ingest_pdf`` skips on this floor,
    no documents row exists and ``register_book`` would raise; we surface that
    as an explicit skipped result instead of crashing the batch.
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
        min_word_count=min_word_count,
    )

    # If ingest_pdf skipped (e.g. word_count below the floor), no documents row
    # was written and register_book would raise. Return the skipped result with
    # a derived deny-by-default servability rather than crashing — the caller
    # (per-item-isolated in the batch) sees a clean skip.
    if ingest_result.skipped_reason in {
        "low_word_count",
        "changed_content_requires_replace",
    }:
        from substrate.books.servability import is_servable_full_text, servability_of

        skipped_status = servability_of(content_class, taken_down=False)
        return IngestServableBookResult(
            ingest=ingest_result,
            document_id=ingest_result.document_id,
            servability=skipped_status.value,
            servable_full_text=is_servable_full_text(skipped_status),
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    toc_items = [
        TocItem(title=t.title, page_index=t.page_index, level=t.level) for t in ingest_result.toc
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
        document_row = con.execute(
            """SELECT raw_text, source_uri, owner_user_id, metadata
               FROM documents WHERE document_id = ?""",
            [ingest_result.document_id],
        ).fetchone()
        assert document_row is not None
        rights_metadata = json.loads(document_row[3]) if document_row[3] else {}
        rights_metadata["reader_projection_state"] = "pending"
        rights_metadata["reader_projection_hash"] = None
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [json.dumps(rights_metadata), ingest_result.document_id],
        )

    assert document_row is not None
    markdown, stored_source_uri, owner_scope, _ = document_row
    canonical_content_hash = "sha256:" + content_hash(str(markdown or ""))
    status = asset.servability.value
    viewable = status not in {"gated_metadata_only", "taken_down"}
    snapshot_path = _write_book_projection(
        document_id=asset.document_id,
        source_uri=str(stored_source_uri) if stored_source_uri else source_uri,
        markdown=str(markdown or ""),
        canonical_content_hash=canonical_content_hash,
        source_event_id=ingest_result.document_loaded_event_id or "unknown",
        title=asset.title,
        author=asset.author,
        ip_holder_id=asset.ip_holder_id,
        content_class=asset.content_class,
        servability=status,
        owner_scope=str(owner_scope),
        viewable=viewable,
        non_viewable_reason=None if viewable else f"servability:{status}",
    )
    _mark_book_projection_ready(
        db_path=resolved_db_path,
        document_id=asset.document_id,
        snapshot_path=snapshot_path,
    )
    ingest_result = replace(ingest_result, reader_snapshot_path=snapshot_path)

    return IngestServableBookResult(
        ingest=ingest_result,
        document_id=asset.document_id,
        servability=asset.servability.value,
        servable_full_text=asset.servable_full_text,
    )

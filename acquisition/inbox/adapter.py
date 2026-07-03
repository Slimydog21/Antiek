"""Inbox ingestion adapter — dated local articles to documents + chunks + nodes.

This is deliberately a thin adapter over ``acquisition.substack.adapter``'s
``ingest_post`` path: content hash → deterministic document id, typed
``document.loaded`` event, schema initialization, markdown chunking, default
embedding provider, one ``connect_write`` single-writer block, document-presence
dedup probe, ``insert_document(on_conflict="ignore")``, then chunk/node writes
only for newly inserted documents.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Literal

# Repo root on path for direct invocation (mirrors podcasts/urls/substack).
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import Chunk, chunk_markdown, content_hash  # noqa: E402
from processing.embedding.embed import EmbeddingProvider, default_embedding_provider  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.ops import _exists, insert_chunk, insert_document, insert_node  # noqa: E402
from substrate.rights.register import SourceKind, register_source_document  # noqa: E402
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

DEFAULT_INBOX_SOURCE_TIER = 4
_NODE_LABEL_MAX = 160
_SUPPORTED_EXTENSIONS = {".txt", ".md"}


@dataclass(frozen=True)
class IngestResult:
    """Outcome of ingesting a single inbox file."""

    document_id: str
    guid: str
    status: str  # "ingested" | "skipped"
    chunk_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    title: str | None = None
    source_path: str | None = None
    already_present: bool = False


@dataclass(frozen=True)
class SkipRecord:
    """One skipped inbox entry with a machine-readable reason."""

    path: str
    reason: str


@dataclass(frozen=True)
class InboxIngestSummary:
    """Aggregate outcome of ingesting an inbox directory."""

    folders_scanned: int
    files_considered: int
    files_ingested: int
    duplicates_skipped: int
    files_skipped: int
    chunks_written: int
    skipped: list[SkipRecord] = field(default_factory=list)
    results: list[IngestResult] = field(default_factory=list)

    @property
    def skipped_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.skipped:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return counts


def _media_type(path: Path) -> Literal["markdown", "pasted_text"]:
    # DocumentLoadedPayload.media_type is a Literal[...] (schema does not admit
    # "text/plain"). Return the exact Literal so mypy --strict accepts it as the
    # payload arg. "pasted_text" is the existing plain-text event lane; the raw
    # source extension is preserved in document metadata.
    return "markdown" if path.suffix.lower() == ".md" else "pasted_text"


def ingest_inbox_file(
    path: Path,
    *,
    folder_date: date,
    investigation_id: str,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> IngestResult:
    """Ingest one dated inbox article into documents + chunks + nodes."""

    resolved_db_path = db_path or default_db_path()
    # Encoding (glm-cc SPR-05 finding 3): prefer strict UTF-8; on a non-UTF-8
    # file fall back to latin-1, which is byte-lossless and never raises — rather
    # than errors="replace", which silently mangles bytes into U+FFFD. Record
    # which decode was used in document metadata so degradation is never silent.
    raw_bytes = path.read_bytes()
    try:
        full_text = raw_bytes.decode("utf-8")
        encoding_used = "utf-8"
    except UnicodeDecodeError:
        full_text = raw_bytes.decode("latin-1")
        encoding_used = "latin-1-fallback"
    body_hash = content_hash(full_text)
    document_id = f"inbox:{body_hash}"
    title = path.stem
    published_at = datetime.combine(folder_date, time.min, tzinfo=UTC)

    # Empty / whitespace-only file (glm-cc SPR-05 finding 4): chunk_markdown
    # yields zero chunks, so a document row would be structurally present but
    # unsearchable. Skip it explicitly (counted upstream) rather than depositing
    # a chunk-less ghost document.
    if not full_text.strip():
        return IngestResult(
            document_id=document_id,
            guid=document_id,
            status="empty",
            title=title,
            source_path=str(path),
            already_present=False,
        )

    chash = "sha256:" + body_hash
    ensure_initialized(resolved_db_path)
    chunks: list[Chunk] = chunk_markdown(full_text)
    chunk_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    with connect_write(resolved_db_path, purpose="acquisition/inbox") as con:
        already_present = _exists(con, "documents", "document_id", document_id)
        if already_present:
            # Idempotent re-run: nothing to write, and NO document.loaded event —
            # emitting one per file per run would grow the event log unboundedly
            # on a daily cron (glm-cc SPR-05 finding 1). The event fires only when
            # a genuinely new document is loaded, below.
            return IngestResult(
                document_id=document_id,
                guid=document_id,
                status="skipped",
                document_loaded_event_id=None,
                title=title,
                source_path=str(path),
                already_present=True,
            )
        payload = DocumentLoadedPayload(
            media_type=_media_type(path),
            content_hash=chash,
            size_bytes=len(full_text.encode("utf-8")),
            title=title,
            page_count=None,
            source_uri=path.as_uri() if path.is_absolute() else str(path),
        )
        event_id = emit_typed(
            investigation_id,
            payload,
            document_id=document_id,
            role="acquisition",
            policy_id="acquisition/inbox",
        )
        insert_document(
            con,
            document_id=document_id,
            source_tier=DEFAULT_INBOX_SOURCE_TIER,
            document_type="web_article",
            source_uri=str(path),
            title=title,
            author=None,
            published_at=published_at,
            investigation_id=investigation_id,
            raw_text=full_text,
            metadata={
                "source": "inbox",
                "path": str(path),
                "folder_date": folder_date.isoformat(),
                "extension": path.suffix.lower(),
                "encoding": encoding_used,
            },
            content_class=PERSONAL_READING_CONTENT_CLASS,
            on_conflict="ignore",
        )
        register_source_document(
            con,
            document_id=document_id,
            source_kind=SourceKind.WEB,
            content_class=PERSONAL_READING_CONTENT_CLASS,
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
                label = label[: _NODE_LABEL_MAX - 1] + "..."
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
                    "source": "inbox",
                    "path": str(path),
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )

    return IngestResult(
        document_id=document_id,
        guid=document_id,
        status="ingested",
        chunk_ids=chunk_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=title,
        source_path=str(path),
        already_present=False,
    )


def _parse_folder_date(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.name)
    except ValueError:
        return None


def ingest_inbox_dir(
    inbox_root: Path,
    *,
    since: date | None = None,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    investigation_id: str = "inbox-ingest",
) -> InboxIngestSummary:
    """Walk ``inbox_root/YYYY-MM-DD`` folders and ingest ``.txt``/``.md`` files."""

    skipped: list[SkipRecord] = []
    results: list[IngestResult] = []
    folders_scanned = 0
    files_considered = 0
    files_ingested = 0
    duplicates_skipped = 0
    chunks_written = 0

    for entry in sorted(inbox_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            skipped.append(SkipRecord(str(entry), "non_directory_entry"))
            continue
        folder_date = _parse_folder_date(entry)
        if folder_date is None:
            skipped.append(SkipRecord(str(entry), "unparseable_folder_name"))
            continue
        if since is not None and folder_date < since:
            continue

        folders_scanned += 1
        for article in sorted(entry.iterdir(), key=lambda p: p.name):
            if article.is_dir():
                skipped.append(SkipRecord(str(article), "directory_in_date_folder"))
                continue
            if article.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                skipped.append(SkipRecord(str(article), "unsupported_extension"))
                continue

            files_considered += 1
            try:
                result = ingest_inbox_file(
                    article,
                    folder_date=folder_date,
                    investigation_id=investigation_id,
                    db_path=db_path,
                    embedder=embedder,
                )
            except OSError:
                skipped.append(SkipRecord(str(article), "unreadable"))
                continue
            results.append(result)
            chunks_written += result.chunks_written
            if result.status == "empty":
                # A chunk-less file — counted as a skip with a reason, never a
                # silent ghost document (glm-cc SPR-05 finding 4).
                skipped.append(SkipRecord(str(article), "empty_file"))
            elif result.already_present:
                duplicates_skipped += 1
            else:
                files_ingested += 1

    return InboxIngestSummary(
        folders_scanned=folders_scanned,
        files_considered=files_considered,
        files_ingested=files_ingested,
        duplicates_skipped=duplicates_skipped,
        files_skipped=len(skipped),
        chunks_written=chunks_written,
        skipped=skipped,
        results=results,
    )

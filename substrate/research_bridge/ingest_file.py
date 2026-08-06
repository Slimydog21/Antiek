"""DRW SPR-08 M1+M3+M4+M5 — universal file ingest into the project graph.

Extends the research bridge from "pasted deep research" to *any* file. The
flow: extract text (``extractors``) → recognize an external deep research
(``detect_external``) → write a provenance-carrying document → (M3) hand the
text to SPR-03's document note pass so it immediately becomes insight/question
nodes. Reuses ``graph.ops.insert_document`` + the ``ingest`` chunking helpers
and the ``external_deep_research`` document type; it writes the ``documents``
table, never ``research_pastes``, so ``ingest_paste``'s single-call-site
invariant is untouched.

Provenance + legal gate (M4): every ingested document carries
``ip_holder_id`` (the operator) and a ``content_class`` so retrieval-time
gating (gate G1) treats it like any source; an external report's own
citations are flagged ``external_citations_unverified`` so the graph never
treats them as Antiek-verified sources.

Dedup (M5): the document_id is the content hash of the extracted text (plus
converter version when one is stamped) — a re-ingest of the same file is a
no-op (``on_conflict='ignore'``), and the notes dedup via SPR-01's hash. A minor
edit is a new content hash → a new document (versioning, see ``versioning.py``,
links it to the original).
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from typing import Any

try:
    from processing.chunking.chunker import chunk_markdown
    from runtime.db_lock import LockedConnection, connect_write
    from substrate.graph.insight_question import graph_db_path
    from substrate.graph.ops import content_addressed_id, insert_chunk, insert_document
    from substrate.research_bridge.detect_external import detect_external_research
    from substrate.research_bridge.extractors import ExtractionResult, extract_text
    from substrate.research_bridge.ingest import (
        CHUNK_TARGET_CHARS,
        _chunk_paragraphs,
        _split_paragraphs,
    )
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from processing.chunking.chunker import chunk_markdown
    from runtime.db_lock import LockedConnection, connect_write
    from substrate.graph.insight_question import graph_db_path
    from substrate.graph.ops import content_addressed_id, insert_chunk, insert_document
    from substrate.research_bridge.detect_external import detect_external_research
    from substrate.research_bridge.extractors import ExtractionResult, extract_text
    from substrate.research_bridge.ingest import (
        CHUNK_TARGET_CHARS,
        _chunk_paragraphs,
        _split_paragraphs,
    )


OPERATOR_IP_HOLDER = "__operator__"
# Ingested personal material is private to the operator until G2 (external
# sharing) — gated like user-owned content by retrieval-time gating.
DEFAULT_CONTENT_CLASS = "user_owned"


class UnsupportedFileError(ValueError):
    """Raised when a file type cannot be extracted — caller surfaces the
    reason to the user; nothing is written."""


@dataclass(frozen=True)
class FileIngestResult:
    document_id: str
    document_type: str
    source: str
    is_external: bool
    vendor: str
    extractor: str
    degraded: bool
    chunk_ids: tuple[str, ...]
    text: str
    was_new: bool


def ingest_file(
    con: LockedConnection,
    *,
    data: str | bytes | bytearray,
    filename: str | None = None,
    content_type: str | None = None,
    investigation_id: str | None = None,
    operator_label: str | None = None,
    ip_holder_id: str = OPERATOR_IP_HOLDER,
    content_class: str = DEFAULT_CONTENT_CLASS,
    do_chunk: bool = True,
) -> FileIngestResult:
    """Ingest one uploaded/pasted file as a provenance-carrying document.
    Raises ``UnsupportedFileError`` on an unparseable type (graceful, no
    write). Idempotent on identical content."""
    if not isinstance(con, LockedConnection):
        raise TypeError("ingest_file requires a LockedConnection")
    extraction: ExtractionResult = extract_text(data, filename=filename, content_type=content_type)
    if not extraction.ok:
        raise UnsupportedFileError(extraction.reason)
    text = extraction.text
    if not text.strip():
        raise UnsupportedFileError("extracted text was empty")

    ext_det = detect_external_research(text)
    if ext_det.is_external:
        document_type = "external_deep_research"
        source = ext_det.vendor
    else:
        document_type = f"uploaded_{extraction.kind or 'file'}"
        source = "upload"

    raw_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document_identity = f"file|{raw_sha}|{source}"
    if extraction.converter_version:
        document_identity += f"|converter={extraction.converter_version}"
    document_id = content_addressed_id("doc", document_identity)
    was_new = con.execute(
        "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
    ).fetchone() is None

    insert_document(
        con,
        document_id=document_id,
        source_tier=4,                       # uploaded/external is low-trust by default
        document_type=document_type,
        source_uri=f"file://{source}/{raw_sha[:16]}",
        title=(filename or _first_line(text))[:200],
        raw_text=text,
        investigation_id=investigation_id,
        ip_holder_id=ip_holder_id,
        content_class=content_class,
        metadata={
            "research_bridge": {
                "source": source, "is_external": ext_det.is_external,
                "vendor": ext_det.vendor, "vendor_label": ext_det.vendor_label,
                "external_confidence": ext_det.confidence,
                "extractor": extraction.extractor, "degraded": extraction.degraded,
                "converter_version": extraction.converter_version or None,
                "operator_label": operator_label, "raw_sha256": raw_sha,
                # The external report's own citations are NOT Antiek-verified.
                "external_citations_unverified": ext_det.is_external,
                "version": 1,
            }
        },
        on_conflict="ignore",
    )

    chunk_ids: list[str] = []
    if do_chunk and was_new:
        chunk_payloads: list[tuple[str, str | None, int]]
        if extraction.kind == "markdown":
            chunk_payloads = [
                (chunk.text, chunk.section or None, chunk.token_count)
                for chunk in chunk_markdown(text)
            ]
        else:
            chunk_payloads = [
                (chunk, None, 0)
                for chunk in _chunk_paragraphs(_split_paragraphs(text), CHUNK_TARGET_CHARS)
            ]
        for index, (chunk_text, section_path, token_count) in enumerate(chunk_payloads):
            chunk_ids.append(
                insert_chunk(
                    con,
                    document_id=document_id,
                    chunk_index=index,
                    text=chunk_text,
                    section_path=section_path,
                    token_count=token_count,
                )
            )

    return FileIngestResult(
        document_id=document_id, document_type=document_type, source=source,
        is_external=ext_det.is_external, vendor=ext_det.vendor,
        extractor=extraction.extractor, degraded=extraction.degraded,
        chunk_ids=tuple(chunk_ids), text=text, was_new=was_new,
    )


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()
    return "Uploaded file"


async def distill_ingested_document(
    result: FileIngestResult,
    *,
    investigation_id: str,
    distiller: Any,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> Any:
    """M3 — run SPR-03's document note pass over an ingested file so it
    immediately yields insight/question nodes. A coroutine, so ingest itself
    returns without blocking on distillation; the caller schedules this."""
    from roles.note_taker.document_pass import run_document_pass
    con = connect_write(db_path or graph_db_path(), purpose="ingest_distill")
    try:
        return await run_document_pass(
            result.document_id, result.text, investigation_id=investigation_id,
            distiller=distiller, chunk_ids=result.chunk_ids, events_dir=events_dir, con=con,
        )
    finally:
        con.close()

"""Single-writer ingest path for pasted deep-research outputs.

``ingest_paste`` is the ONE function that turns a paste into substrate
rows. Every UI surface (HTTP API, CLI, future imports) must call it.

Invariants:

1. Single call site. Grepping for the SQL string literal that targets
   ``research_pastes`` must return exactly one match: the body of
   this function. The grep test in
   ``tests/research_bridge/test_ingest.py`` enforces it.
2. Atomic ingest within the LockedConnection.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import (
        content_addressed_id,
        insert_chunk,
        insert_document,
        new_random_id,
    )
    from .paste_log import log_paste_event
    from .source_detection import (
        KNOWN_SOURCES,
        SourceDetectionResult,
        detect_source,
    )
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import (  # type: ignore[no-redef]
        content_addressed_id, insert_chunk, insert_document, new_random_id,
    )
    from substrate.research_bridge.paste_log import log_paste_event  # type: ignore[no-redef]
    from substrate.research_bridge.source_detection import (  # type: ignore[no-redef]
        KNOWN_SOURCES, SourceDetectionResult, detect_source,
    )


PASTE_DOCUMENT_TYPE: str = "external_deep_research"
DEFAULT_PASTE_TIER: int = 4
MAX_PASTE_BYTES: int = int(os.environ.get("ANTIEK_MAX_PASTE_BYTES", "2097152"))
CHUNK_TARGET_CHARS: int = 2000


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    source: str
    source_confidence: float
    raw_sha256: str
    paste_byte_length: int
    parser_version: int
    chunk_ids: tuple[str, ...]
    detection: SourceDetectionResult


class PasteTooLargeError(ValueError):
    """Raised when a paste exceeds MAX_PASTE_BYTES."""


class PasteEmptyError(ValueError):
    """Raised when a paste is empty after stripping whitespace."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_paragraphs(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.strip() == "":
            if buf:
                out.append("".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        out.append("".join(buf))
    return [p for p in out if p.strip()]


def _chunk_paragraphs(paragraphs: list[str], target: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paragraphs:
        plen = len(p)
        if plen >= target:
            if cur:
                chunks.append("\n\n".join(cur))
                cur = []
                cur_len = 0
            chunks.append(p)
            continue
        if cur and cur_len + plen + 2 > target:
            chunks.append("\n\n".join(cur))
            cur = [p]
            cur_len = plen
        else:
            cur.append(p)
            cur_len += plen + (2 if cur_len else 0)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def ingest_paste(
    con: LockedConnection,
    *,
    raw_text: str,
    operator_label: Optional[str] = None,
    session_id: Optional[str] = None,
    source_override: Optional[str] = None,
    source_tier: int = DEFAULT_PASTE_TIER,
    call_site: str = "unknown",
    investigation_id: Optional[str] = None,
    do_chunk: bool = True,
) -> IngestResult:
    """Ingest one pasted deep-research output. Returns IngestResult."""
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "ingest_paste requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write."
        )
    if raw_text is None or not raw_text.strip():
        raise PasteEmptyError("raw_text is empty or whitespace-only")
    raw_bytes = raw_text.encode("utf-8")
    byte_len = len(raw_bytes)
    if byte_len > MAX_PASTE_BYTES:
        raise PasteTooLargeError(
            f"paste of {byte_len} bytes exceeds MAX_PASTE_BYTES={MAX_PASTE_BYTES}. "
            "Override via ANTIEK_MAX_PASTE_BYTES env var if intentional."
        )
    if source_override is not None and source_override not in KNOWN_SOURCES:
        raise ValueError(
            f"source_override={source_override!r} not in KNOWN_SOURCES={KNOWN_SOURCES}"
        )
    if not 1 <= source_tier <= 5:
        raise ValueError(f"source_tier must be 1..5, got {source_tier}")

    detection = detect_source(raw_text)
    source = source_override if source_override else detection.source
    source_confidence = detection.confidence

    raw_sha256 = _sha256_bytes(raw_bytes)
    document_id = content_addressed_id("doc", f"paste|{raw_sha256}|{source}")

    first_line = ""
    for ln in raw_text.splitlines():
        if ln.strip():
            first_line = ln.strip()
            break
    title = first_line[:200] if first_line else f"Pasted research ({source})"

    insert_document(
        con,
        document_id=document_id,
        source_tier=source_tier,
        document_type=PASTE_DOCUMENT_TYPE,
        source_uri=f"paste://{source}/{raw_sha256[:16]}",
        title=title,
        raw_text=raw_text,
        investigation_id=investigation_id,
        metadata={
            "research_bridge": {
                "source": source,
                "source_confidence": source_confidence,
                "parser_version": detection.parser_version,
                "paste_byte_length": byte_len,
                "raw_sha256": raw_sha256,
                "session_id": session_id,
                "operator_label": operator_label,
                "per_source_scores": detection.per_source,
            }
        },
        on_conflict="ignore",
    )

    existing = con.execute(
        "SELECT 1 FROM research_pastes WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if existing is None:
        con.execute(
            "INSERT INTO research_pastes "
            "(document_id, source, source_confidence, raw_sha256, "
            " paste_byte_length, parser_version, operator_label, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                document_id, source, float(source_confidence),
                raw_sha256, int(byte_len), int(detection.parser_version),
                operator_label, session_id,
            ],
        )

    chunk_ids: list[str] = []
    if do_chunk:
        paragraphs = _split_paragraphs(raw_text)
        for idx, chunk_text in enumerate(_chunk_paragraphs(paragraphs, CHUNK_TARGET_CHARS)):
            cid = insert_chunk(
                con, document_id=document_id, chunk_index=idx,
                text=chunk_text, section_path=None, embedding=None, token_count=0,
            )
            chunk_ids.append(cid)

    log_paste_event(
        con,
        event_id=new_random_id("rpaste-evt"),
        document_id=document_id,
        paste_byte_length=byte_len,
        raw_sha256=raw_sha256,
        source=source,
        call_site=call_site,
    )

    return IngestResult(
        document_id=document_id,
        source=source,
        source_confidence=float(source_confidence),
        raw_sha256=raw_sha256,
        paste_byte_length=byte_len,
        parser_version=detection.parser_version,
        chunk_ids=tuple(chunk_ids),
        detection=detection,
    )

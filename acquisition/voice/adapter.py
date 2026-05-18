"""Voice note → Antiek substrate adapter.

Takes an operator's recorded audio (whisper-transcribed) and writes
the transcript into the substrate the same way an article or YouTube
transcript would land — but with ``document_type='voice_note'`` so
the note_taker role can apply the operator-self-talk-style prompt
when it runs.

Stable doc id: ``doc-vn-<sha256[:16]>`` keyed on the
``(operator_id, recorded_at_iso)`` pair so re-ingesting the same
audio is idempotent.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

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

from .client import Transcriber, Transcript, transcribe_audio

DEFAULT_VOICE_SOURCE_TIER = 2  # operator-originated → tier 2 (primary)
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 8  # voice notes are short; lower threshold


@dataclass(frozen=True)
class IngestVoiceNoteResult:
    document_id: str
    chunk_ids: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    skipped_reason: Optional[str] = None
    title: Optional[str] = None
    transcript_text: Optional[str] = None
    duration_seconds: float = 0.0


def voice_note_doc_id(
    operator_id: str, recorded_at: datetime,
) -> str:
    """Stable doc id keyed on ``(operator, recorded_at)``."""
    if not operator_id:
        raise ValueError("empty operator_id")
    seed = f"{operator_id}|{recorded_at.isoformat()}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"doc-vn-{h}"


def _format_voice_note_markdown(
    *,
    title: str,
    transcript: str,
    recorded_at: datetime,
    duration_seconds: float,
    language: Optional[str],
) -> str:
    """Render the voice note as chunker-friendly markdown."""
    lines = [
        f"# {title}",
        "",
        f"**Recorded:** {recorded_at.isoformat()}",
    ]
    if duration_seconds:
        m, s = divmod(int(round(duration_seconds)), 60)
        lines.append(f"**Duration:** {m:02d}:{s:02d}")
    if language:
        lines.append(f"**Language:** {language}")
    lines.append("")
    lines.append("## Transcript")
    lines.append("")
    lines.append(transcript.strip())
    return "\n".join(lines)


def ingest_voice_note(
    transcript: str,
    *,
    investigation_id: str,
    title: Optional[str] = None,
    recorded_at: Optional[datetime] = None,
    duration_seconds: float = 0.0,
    language: Optional[str] = None,
    operator_id: str = "__operator__",
    source_tier: int = DEFAULT_VOICE_SOURCE_TIER,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
) -> IngestVoiceNoteResult:
    """Write a transcribed voice note into the substrate graph.

    The transcript is the text-only output of whisper (or a stub for
    tests). This adapter does not perform transcription itself; pair
    with ``transcribe_and_ingest`` to chain the two.
    """
    when = recorded_at or datetime.now(timezone.utc)
    document_id = voice_note_doc_id(operator_id, when)
    auto_title = title or f"Voice note {when.strftime('%Y-%m-%d %H:%M')}"
    full_text = _format_voice_note_markdown(
        title=auto_title,
        transcript=transcript,
        recorded_at=when,
        duration_seconds=duration_seconds,
        language=language,
    )
    chash = "sha256:" + content_hash(full_text)
    word_count = len(transcript.split())

    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(full_text.encode("utf-8")),
        title=auto_title,
        page_count=None,
        source_uri=None,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/voice",
    )

    if word_count < min_word_count:
        return IngestVoiceNoteResult(
            document_id=document_id,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=auto_title,
            transcript_text=transcript,
            duration_seconds=duration_seconds,
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: List[Chunk] = chunk_markdown(full_text)
    chunk_ids: List[str] = []
    node_ids: List[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/voice") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="voice_note",
            source_uri=None,
            title=auto_title,
            author=operator_id,
            published_at=when,
            investigation_id=investigation_id,
            raw_text=full_text,
            metadata={
                "operator_id": operator_id,
                "duration_seconds": duration_seconds,
                "language": language,
                "transcription_source": "whisper",
                "recorded_at": when.isoformat(),
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
                label = f"voice-note#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "voice_note",
                    "operator_id": operator_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestVoiceNoteResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=auto_title,
        transcript_text=transcript,
        duration_seconds=duration_seconds,
    )


def transcribe_and_ingest(
    audio_bytes: bytes,
    *,
    filename: str,
    investigation_id: str,
    operator_id: str = "__operator__",
    title: Optional[str] = None,
    language: Optional[str] = None,
    transcriber: Optional[Transcriber] = None,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
) -> IngestVoiceNoteResult:
    """End-to-end: transcribe audio via whisper, then write into the
    substrate graph. Pass a stub ``transcriber`` in tests."""
    tx: Transcript = transcribe_audio(
        audio_bytes, filename=filename, language=language,
        transcriber=transcriber,
    )
    return ingest_voice_note(
        tx.text,
        investigation_id=investigation_id,
        title=title,
        recorded_at=datetime.now(timezone.utc),
        duration_seconds=tx.duration_seconds,
        language=tx.language or language,
        operator_id=operator_id,
        db_path=db_path,
        embedder=embedder,
    )

"""YouTube → Antiek substrate adapter.

Converts a fetched ``YouTubeVideo`` into the substrate's standard
ingestion shape: emit ``document.loaded``, write a documents row +
chunks + per-chunk nodes. Mirrors ``acquisition.arxiv.adapter`` and
``acquisition.urls.adapter`` contract.

Section paths encode timestamp ranges (e.g. ``Timestamp: 00:00:42 -
00:01:12``) so the eventual cross-mode deep-link can jump to the
right moment in the video. Today the substrate's web app's "Open in
document" handler only knows about ``Page N`` PDF anchors; YouTube
timestamps fall back to opening the watch URL.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
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
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
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

from .client import TranscriptSegment, YouTubeVideo, fetch

DEFAULT_YOUTUBE_SOURCE_TIER = 4
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 50

# Group transcript segments into ~250-word chunks (≈ 90-120 seconds of
# normal speech). Strikes a balance: fine enough that an insight can
# be anchored to a span shorter than the whole video; coarse enough
# that we don't fragment one sentence across chunks.
DEFAULT_CHUNK_TARGET_WORDS = 250


@dataclass(frozen=True)
class IngestYouTubeResult:
    document_id: str
    video_id: str
    chunk_ids: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    skipped_reason: Optional[str] = None
    title: Optional[str] = None
    transcript_source: str = "missing"


def youtube_doc_id(video_id: str) -> str:
    """Stable Antiek doc id for a YouTube video. The video_id is
    already a stable 11-char string; prefix to namespace it."""
    if not video_id:
        raise ValueError("empty video_id")
    return f"doc-yt-{video_id}"


# ── Transcript segmentation into timestamped chunks ──────────────────


def _format_timestamp(seconds: float) -> str:
    """HH:MM:SS for transcript anchors."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _group_transcript_into_chunks(
    segments: List[TranscriptSegment],
    target_words: int,
) -> List[Chunk]:
    """Walk transcript segments, accumulate ~target_words of text per
    chunk, emit Chunk objects with timestamp-range section_path."""
    chunks: List[Chunk] = []
    cur_words: List[str] = []
    cur_start: Optional[float] = None
    cur_end: float = 0.0
    cur_text_lines: List[str] = []

    def flush() -> None:
        if not cur_words:
            return
        text = "\n".join(cur_text_lines).strip()
        section = (
            f"Timestamp: {_format_timestamp(cur_start or 0.0)} - "
            f"{_format_timestamp(cur_end)}"
        )
        chunks.append(
            Chunk(text=text, section=section, token_count=len(cur_words))
        )

    for seg in segments:
        if cur_start is None:
            cur_start = seg.start_seconds
        cur_end = seg.start_seconds + seg.duration_seconds
        words = seg.text.split()
        cur_words.extend(words)
        cur_text_lines.append(seg.text)
        if len(cur_words) >= target_words:
            flush()
            cur_words = []
            cur_text_lines = []
            cur_start = None
            cur_end = 0.0
    flush()
    return chunks


def _format_video_markdown(video: YouTubeVideo) -> str:
    """Render a chunker-friendly markdown of the video's full text
    (used as the documents.raw_text column + the chunker fallback when
    no transcript exists)."""
    lines = [
        f"# {video.title}",
        "",
        f"_{video.channel} · {video.watch_url}_",
        "",
    ]
    if video.upload_date:
        lines.append(f"**Uploaded:** {video.upload_date.date().isoformat()}")
        lines.append("")
    if video.duration_seconds:
        lines.append(
            f"**Duration:** {_format_timestamp(video.duration_seconds)}"
        )
        lines.append("")
    if video.description:
        lines.append("## Description")
        lines.append("")
        lines.append(video.description)
        lines.append("")
    if video.transcript:
        lines.append("## Transcript")
        lines.append("")
        for seg in video.transcript:
            lines.append(seg.text)
    return "\n".join(lines)


# ── Adapter entry point ──────────────────────────────────────────────


def ingest_youtube(
    url_or_id: str,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_YOUTUBE_SOURCE_TIER,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
    chunk_target_words: int = DEFAULT_CHUNK_TARGET_WORDS,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
    video: Optional[YouTubeVideo] = None,
) -> IngestYouTubeResult:
    """Fetch + ingest a YouTube video. Pass ``video=`` to reuse an
    already-fetched record (e.g. a batch ingester that fetches in
    parallel)."""
    v = video or fetch(url_or_id)
    document_id = youtube_doc_id(v.video_id)
    full_text = _format_video_markdown(v)
    chash = "sha256:" + content_hash(full_text)
    word_count = len(full_text.split())

    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(full_text.encode("utf-8")),
        title=v.title,
        page_count=None,
        source_uri=v.watch_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/youtube",
    )

    if word_count < min_word_count:
        return IngestYouTubeResult(
            document_id=document_id,
            video_id=v.video_id,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=v.title,
            transcript_source=v.transcript_source,
        )
    if not v.transcript and word_count < min_word_count * 4:
        # No captions AND only description-level content — not enough
        # signal to ingest. Caller may want to fall back to whisper on
        # the audio (out of scope for Sprint 12 substrate-only path).
        return IngestYouTubeResult(
            document_id=document_id,
            video_id=v.video_id,
            document_loaded_event_id=event_id,
            skipped_reason="no_transcript",
            title=v.title,
            transcript_source=v.transcript_source,
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    # If a transcript is present, chunk by timestamp range. Otherwise
    # fall back to markdown chunking on the description-only body.
    if v.transcript:
        chunks: List[Chunk] = _group_transcript_into_chunks(
            v.transcript, chunk_target_words,
        )
    else:
        chunks = chunk_markdown(full_text)

    chunk_ids: List[str] = []
    node_ids: List[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/youtube") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="video_transcript",
            # Personal-Reading Lane (SPR-02): a third-party YouTube transcript
            # the owner fetched for their own reading lands personal_reading —
            # full body readable by the owner, NEVER served publicly / ad-
            # attributed / trained on (§9.0). The IMPORTED CONSTANT is passed,
            # never the "personal_reading" literal (corpus_audit's scanner
            # flags content_class string literals to keep classify() the one
            # chokepoint). SPR-07 later refines the YouTube-specific posture
            # (rate cap, ToS flag, CC-BY servable exception); this only sets
            # the default lane. Belt-and-suspenders with the SPR-01 fallback.
            content_class=PERSONAL_READING_CONTENT_CLASS,
            source_uri=v.watch_url,
            title=v.title,
            author=v.channel,
            published_at=v.upload_date,
            investigation_id=investigation_id,
            raw_text=full_text,
            metadata={
                "video_id": v.video_id,
                "duration_seconds": v.duration_seconds,
                "channel": v.channel,
                "transcript_source": v.transcript_source,
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
                label = f"{v.video_id}#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "youtube",
                    "video_id": v.video_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestYouTubeResult(
        document_id=document_id,
        video_id=v.video_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=v.title,
        transcript_source=v.transcript_source,
    )

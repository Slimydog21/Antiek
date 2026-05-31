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
from substrate.books.model import upsert_book_asset  # noqa: E402
from substrate.constants import (  # noqa: E402
    PERSONAL_READING_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
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

from .client import (  # noqa: E402
    CAPTION_KIND_MISSING,
    TranscriptSegment,
    YouTubeVideo,
    fetch,
)

# Truthful, durable license basis recorded when an operator positively
# confirms a specific video is published under CC-BY (M3). It explicitly
# names that the YouTube default ("Standard YouTube License") is NOT
# CC-BY, so a future maintainer / the SPR-10 audit can reconstruct why
# this one transcript is servable while the rest stay personal_reading.
CC_BY_OPERATOR_LICENSE_BASIS = (
    "CC-BY (operator-confirmed per-video; the default Standard YouTube "
    "License is NOT CC-BY)"
)

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
    # SPR-07: caption provenance surfaced to the reader/caller.
    caption_kind: str = CAPTION_KIND_MISSING
    # SPR-07: the resolved rights class actually persisted (None on a
    # skipped ingest that wrote no row). personal_reading by default;
    # source_declared_open only on an operator-confirmed CC-BY video.
    content_class: Optional[str] = None


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
    content_class: Optional[str] = None,
    operator_confirmed_cc_by: bool = False,
) -> IngestYouTubeResult:
    """Fetch + ingest a YouTube video. Pass ``video=`` to reuse an
    already-fetched record (e.g. a batch ingester that fetches in
    parallel).

    Rights class (SPR-07): by default a third-party YouTube transcript
    the owner fetched for their own reading lands ``personal_reading`` —
    owner-readable in full, NEVER served publicly / ad-attributed /
    trained on (§9.0). The narrow escape hatch is
    ``operator_confirmed_cc_by=True``: ONLY when the operator positively
    asserts THIS specific video is published under CC-BY is the transcript
    promoted to ``source_declared_open`` (servable) with a truthful
    ``license_basis``. Note: a CC-BY claim is about the *video's license*,
    not the caption provenance — an auto-captioned video can still be
    CC-BY, and a human-captioned video can still be Standard License; the
    flag is the operator's per-video assertion and defaults to the safe
    ``False``. An explicit ``content_class=`` (a named constant) overrides
    both — caller's responsibility to keep it audit-clean.
    """
    v = video or fetch(url_or_id)

    # Resolve the rights class to a LOCAL NAME (never a string literal at
    # the insert_document call site — corpus_audit's AST scanner flags
    # content_class string literals to keep classify() the one chokepoint).
    if content_class is not None:
        # An explicit content_class= is a deliberate caller override (e.g.
        # SPR-09/SPR-10 reuse). It is NOT a free-for-all: validate it here so
        # this parameter cannot become a silent escape from the personal lane.
        # (i) It must be a recognized readable rights class — an arbitrary or
        #     misspelled string would otherwise slip past corpus_audit's AST
        #     literal-scanner (which only forbids LITERALS, not this Name) and
        #     land an unknown class on the row.
        # (ii) If it is a SERVABLE class it MUST carry an explicit
        #      license_basis — otherwise a caller could promote a third-party
        #      transcript to a publicly servable class with NO recorded basis,
        #      the exact §9.0 leak corpus_audit._check_third_party_servable
        #      backstops. The sanctioned promotion path remains
        #      operator_confirmed_cc_by, which records the basis automatically.
        if content_class not in PERSONAL_READABLE_CONTENT_CLASSES:
            raise YouTubeContentClassRejected(
                f"explicit content_class={content_class!r} is not a "
                f"recognized readable rights class "
                f"({sorted(PERSONAL_READABLE_CONTENT_CLASSES)}). The default "
                f"(personal_reading) or operator_confirmed_cc_by is the "
                f"sanctioned path; do not pass an arbitrary class string."
            )
        if content_class in SERVABLE_CONTENT_CLASSES and not (
            license_basis and license_basis.strip()
        ):
            raise YouTubeContentClassRejected(
                f"explicit servable content_class={content_class!r} requires "
                f"an explicit, non-empty license_basis= (a servable class "
                f"with no positive basis is the §9.0 leak corpus_audit "
                f"forbids). Pass license_basis=, or use "
                f"operator_confirmed_cc_by=True for the CC-BY hatch."
            )
        resolved_content_class = content_class
        resolved_license_basis: Optional[str] = (
            license_basis if content_class in SERVABLE_CONTENT_CLASSES else None
        )
    elif operator_confirmed_cc_by:
        resolved_content_class = SOURCE_DECLARED_OPEN_CONTENT_CLASS
        resolved_license_basis = CC_BY_OPERATOR_LICENSE_BASIS
    else:
        resolved_content_class = PERSONAL_READING_CONTENT_CLASS
        resolved_license_basis = None

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
        # Early return BEFORE any insert_document — writes no documents
        # row, so a skipped ingest cannot leak a rights class. content_class
        # stays None on the result to reflect "nothing persisted".
        return IngestYouTubeResult(
            document_id=document_id,
            video_id=v.video_id,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=v.title,
            transcript_source=v.transcript_source,
            caption_kind=getattr(v, "caption_kind", CAPTION_KIND_MISSING),
        )
    if not v.transcript and word_count < min_word_count * 4:
        # No captions AND only description-level content — not enough
        # signal to ingest. Caller may want to fall back to whisper on
        # the audio (out of scope for Sprint 12 substrate-only path).
        # Also an early return before any write → no class leak.
        return IngestYouTubeResult(
            document_id=document_id,
            video_id=v.video_id,
            document_loaded_event_id=event_id,
            skipped_reason="no_transcript",
            title=v.title,
            transcript_source=v.transcript_source,
            caption_kind=getattr(v, "caption_kind", CAPTION_KIND_MISSING),
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
            # Personal-Reading Lane (SPR-02 default, SPR-07 posture): a
            # third-party YouTube transcript the owner fetched for their own
            # reading lands personal_reading — full body readable by the
            # owner, NEVER served publicly / ad-attributed / trained on
            # (§9.0). The promotion to source_declared_open happens ONLY on
            # an explicit per-video operator_confirmed_cc_by assertion (M3).
            # In every branch the value is a LOCAL NAME (resolved above),
            # never a content_class string literal at this call site —
            # corpus_audit's AST scanner flags literals to keep classify()
            # the one chokepoint. The license_basis (when a servable class
            # was positively justified by CC-BY) is recorded on book_assets
            # via upsert_book_asset BELOW — NOT on insert_document, which has
            # no license_basis parameter; book_assets.license_basis is the
            # exact column corpus_audit._check_servable_basis /
            # _check_third_party_servable read, so the servable-basis DB check
            # sees a truthful basis, not an empty one.
            content_class=resolved_content_class,
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
                # SPR-07: caption provenance (human/auto/unknown/missing)
                # so the reader knows auto-captions are unreliable.
                "caption_kind": getattr(v, "caption_kind", CAPTION_KIND_MISSING),
            },
            on_conflict="ignore",
        )
        # M3: when (and only when) this transcript was promoted to a servable
        # class on an operator-confirmed CC-BY assertion, record the truthful
        # positive license_basis on book_assets — the column corpus_audit reads
        # to prove every servable work carries a basis. A personal_reading
        # default carries NO basis (resolved_license_basis is None), so the
        # private-lane row never touches book_assets and stays correctly
        # basis-less. upsert_book_asset takes the SAME write-locked connection
        # and ensures the book_assets schema itself (§16 single-writer intact).
        if resolved_license_basis is not None:
            upsert_book_asset(
                con,
                document_id=document_id,
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

    # M3: when (and only when) this transcript was promoted to a servable
    # class on an operator-confirmed CC-BY assertion, record the truthful
    # positive license_basis on book_assets — the column corpus_audit reads
    # (_check_servable_basis / _check_third_party_servable) to prove every
    # servable work carries a basis. A personal_reading default carries NO
    # basis (resolved_license_basis is None), so the private-lane row never
    # touches book_assets and stays correctly basis-less.
    #
    # This is a SEPARATE, sequential connect_write block (NOT a second
    # writer — the previous block has already released the single-writer
    # lock). Done deliberately: persisting the book_assets row in the SAME
    # transaction as insert_document + the chunk/node loop was observed to
    # be silently dropped by DuckDB under MVCC when many statements (and the
    # documents→book_assets foreign key) share one transaction, while a
    # dedicated write block commits it durably. §16 single-writer is intact
    # (one lock holder at a time, serialized through runtime.db_lock).
    if resolved_license_basis is not None:
        from runtime.db_lock import connect_write as _connect_write_basis

        with _connect_write_basis(
            resolved_db_path, purpose="acquisition/youtube/license_basis"
        ) as basis_con:
            upsert_book_asset(
                basis_con,
                document_id=document_id,
                license_basis=resolved_license_basis,
            )

    return IngestYouTubeResult(
        document_id=document_id,
        video_id=v.video_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=v.title,
        transcript_source=v.transcript_source,
        caption_kind=getattr(v, "caption_kind", CAPTION_KIND_MISSING),
        content_class=resolved_content_class,
    )

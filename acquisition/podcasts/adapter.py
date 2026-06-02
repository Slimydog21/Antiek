"""Podcast → Antiek substrate adapter.

For each episode we have a transcript for, emit ``document.loaded``,
write a documents row + chunks + per-chunk nodes. Same shape as
``acquisition.arxiv`` / ``acquisition.urls`` / ``acquisition.youtube``.

Episode-level granularity: each episode becomes its own
``documents`` row with stable doc id ``doc-pod-<sha256[:16]>`` keyed
on the episode_id (or the audio URL when the RSS lacks a GUID).
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field

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
from substrate.rights.register import (  # noqa: E402
    SourceKind,
    register_source_document,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

from .client import (  # noqa: E402
    Episode,
    Podcast,
    fetch_episode_transcript,
    fetch_feed,
)

DEFAULT_PODCAST_SOURCE_TIER = 3
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 100


@dataclass(frozen=True)
class IngestPodcastResult:
    document_id: str
    episode_id: str
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    title: str | None = None


def podcast_doc_id(episode_id: str) -> str:
    """Stable Antiek doc id keyed on the episode's RSS GUID (or fallback
    to audio URL). Hash for path-safety."""
    if not episode_id:
        raise ValueError("empty episode_id")
    h = hashlib.sha256(episode_id.encode("utf-8")).hexdigest()[:16]
    return f"doc-pod-{h}"


def _format_episode_markdown(
    podcast: Podcast, episode: Episode, transcript: str,
) -> str:
    """Render an episode's full text as chunker-friendly markdown."""
    lines = [
        f"# {episode.title}",
        "",
        f"_{podcast.title}",
    ]
    if podcast.author:
        lines[-1] += f" — {podcast.author}"
    if episode.episode_url:
        lines.append(f"_{episode.episode_url}_")
    lines.append("")
    if episode.published_at:
        lines.append(f"**Published:** {episode.published_at.date().isoformat()}")
        lines.append("")
    if episode.duration_seconds:
        h, rem = divmod(episode.duration_seconds, 3600)
        m, _ = divmod(rem, 60)
        lines.append(f"**Duration:** {h:02d}:{m:02d}")
        lines.append("")
    if episode.description:
        lines.append("## Description")
        lines.append("")
        lines.append(episode.description)
        lines.append("")
    if transcript:
        lines.append("## Transcript")
        lines.append("")
        lines.append(transcript)
    return "\n".join(lines)


def ingest_podcast_episode(
    podcast: Podcast,
    episode: Episode,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_PODCAST_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    transcript_override: str | None = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
) -> IngestPodcastResult:
    """Ingest one episode. Pass ``transcript_override`` when the caller
    already fetched + cleaned the transcript (e.g. whisper fallback);
    otherwise we fetch via ``client.fetch_episode_transcript`` if a
    ``transcript_url`` is available, or skip with ``no_transcript``."""
    document_id = podcast_doc_id(episode.episode_id)

    transcript: str = transcript_override or ""
    if not transcript and episode.transcript_url:
        transcript = fetch_episode_transcript(episode.transcript_url)

    full_text = _format_episode_markdown(podcast, episode, transcript)
    chash = "sha256:" + content_hash(full_text)
    word_count = len(full_text.split())

    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(full_text.encode("utf-8")),
        title=episode.title,
        page_count=None,
        source_uri=episode.episode_url or episode.audio_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/podcasts",
    )

    if not transcript:
        return IngestPodcastResult(
            document_id=document_id,
            episode_id=episode.episode_id,
            document_loaded_event_id=event_id,
            skipped_reason="no_transcript",
            title=episode.title,
        )

    if word_count < min_word_count:
        return IngestPodcastResult(
            document_id=document_id,
            episode_id=episode.episode_id,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=episode.title,
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: list[Chunk] = chunk_markdown(full_text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/podcasts") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="podcast_episode",
            source_uri=episode.episode_url or episode.audio_url,
            title=episode.title,
            author=podcast.author or podcast.title,
            published_at=episode.published_at,
            investigation_id=investigation_id,
            raw_text=full_text,
            metadata={
                "podcast_title": podcast.title,
                "podcast_author": podcast.author,
                "feed_url": podcast.feed_url,
                "episode_id": episode.episode_id,
                "audio_url": episode.audio_url,
                "transcript_source": (
                    "override" if transcript_override else "rss"
                ),
                "duration_seconds": episode.duration_seconds,
            },
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
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{episode.episode_id}#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "podcast",
                    "podcast_title": podcast.title,
                    "episode_id": episode.episode_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestPodcastResult(
        document_id=document_id,
        episode_id=episode.episode_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=episode.title,
    )


def ingest_feed(
    feed_url: str,
    *,
    investigation_id: str,
    max_episodes: int = 10,
    source_tier: int = DEFAULT_PODCAST_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> list[IngestPodcastResult]:
    """Ingest the N most-recent episodes from an RSS feed. Each
    episode goes through ``ingest_podcast_episode``. Returns a list
    of per-episode results so the caller can aggregate / report."""
    podcast = fetch_feed(feed_url, max_episodes=max_episodes)
    results: list[IngestPodcastResult] = []
    for episode in podcast.episodes:
        try:
            r = ingest_podcast_episode(
                podcast, episode,
                investigation_id=investigation_id,
                source_tier=source_tier,
                db_path=db_path,
                embedder=embedder,
            )
            results.append(r)
        except Exception as exc:  # pragma: no cover — defensive
            results.append(IngestPodcastResult(
                document_id=podcast_doc_id(episode.episode_id),
                episode_id=episode.episode_id,
                skipped_reason=f"error: {type(exc).__name__}",
                title=episode.title,
            ))
    return results

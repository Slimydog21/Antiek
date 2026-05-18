"""Podcast acquisition path — Sprint 12.

Requires the ``[rss]`` extra: ``pip install -e '.[rss]'`` to pick up
``feedparser``.

Surface:

- ``client.fetch_feed(rss_url, max_episodes=N)`` — parses the RSS feed,
  returns a ``Podcast`` with episode list (each episode carries audio
  URL + transcript URL when advertised).
- ``client.fetch_episode_transcript(transcript_url)`` — fetches a
  transcript file (VTT/SRT/TXT) and normalizes to plain text.
- ``adapter.ingest_podcast_episode(podcast, episode, *, investigation_id, ...)``
  — emits ``document.loaded`` + writes documents/chunks/nodes for one
  episode. Skipped with ``no_transcript`` when neither the RSS nor an
  override transcript is available.
- ``adapter.ingest_feed(rss_url, *, investigation_id, max_episodes=N)``
  — convenience wrapper that walks the N most-recent episodes through
  ``ingest_podcast_episode``.
"""

from .adapter import (
    IngestPodcastResult,
    ingest_feed,
    ingest_podcast_episode,
    podcast_doc_id,
)
from .client import (
    Episode,
    Podcast,
    fetch_episode_transcript,
    fetch_feed,
)

__all__ = [
    "Episode",
    "IngestPodcastResult",
    "Podcast",
    "fetch_episode_transcript",
    "fetch_feed",
    "ingest_feed",
    "ingest_podcast_episode",
    "podcast_doc_id",
]

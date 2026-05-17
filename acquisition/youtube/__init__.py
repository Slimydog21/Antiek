"""YouTube acquisition path — Sprint 12.

Requires the ``[youtube]`` extra:
``pip install -e '.[youtube]'`` to pick up ``yt-dlp`` +
``youtube-transcript-api``.
"""

from .adapter import IngestYouTubeResult, ingest_youtube, youtube_doc_id
from .client import (
    TranscriptSegment,
    YouTubeVideo,
    fetch,
    parse_video_id,
)

__all__ = [
    "IngestYouTubeResult",
    "TranscriptSegment",
    "YouTubeVideo",
    "fetch",
    "ingest_youtube",
    "parse_video_id",
    "youtube_doc_id",
]

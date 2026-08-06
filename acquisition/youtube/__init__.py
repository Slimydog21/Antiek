"""YouTube acquisition path — Sprint 12.

Requires the ``[youtube]`` extra:
``pip install -e '.[youtube]'`` to pick up ``yt-dlp`` +
``youtube-transcript-api``.
"""

from .adapter import (
    IngestYouTubeResult,
    YouTubeContentClassRejected,
    ingest_youtube,
    youtube_doc_id,
)
from .client import (
    CAPTION_KIND_AUTO,
    CAPTION_KIND_HUMAN,
    CAPTION_KIND_MISSING,
    CAPTION_KIND_UNKNOWN,
    YOUTUBE_MAX_FETCHES_PER_RUN,
    TranscriptSegment,
    YouTubeRateCapExceeded,
    YouTubeVideo,
    fetch,
    note_youtube_fetch,
    parse_video_id,
    reset_youtube_fetch_counter,
)
from .data_api import (
    YouTubeApiError,
    YouTubeConnector,
    YouTubeKeyRequired,
    YouTubeQuotaExhausted,
    YouTubeSearchResult,
    parse_search_response,
)

__all__ = [
    "CAPTION_KIND_AUTO",
    "CAPTION_KIND_HUMAN",
    "CAPTION_KIND_MISSING",
    "CAPTION_KIND_UNKNOWN",
    "IngestYouTubeResult",
    "TranscriptSegment",
    "YOUTUBE_MAX_FETCHES_PER_RUN",
    "YouTubeApiError",
    "YouTubeConnector",
    "YouTubeContentClassRejected",
    "YouTubeKeyRequired",
    "YouTubeQuotaExhausted",
    "YouTubeRateCapExceeded",
    "YouTubeSearchResult",
    "YouTubeVideo",
    "fetch",
    "ingest_youtube",
    "note_youtube_fetch",
    "parse_search_response",
    "parse_video_id",
    "reset_youtube_fetch_counter",
    "youtube_doc_id",
]
